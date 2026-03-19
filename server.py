#!/usr/bin/env python3
"""
IT Helpdesk Search — Flask API Backend
Run: python server.py
Then open: http://localhost:5000
"""

import time
import textwrap
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

# ── Constants ──────────────────────────────────────────────────────────────────
STACK_EXCHANGE_API = "https://api.stackexchange.com/2.3"
REDDIT_BASE        = "https://www.reddit.com"
USER_AGENT         = "IT-Helpdesk-Search/1.0 (python-requests)"

REDDIT_SUBREDDITS  = ["sysadmin", "techsupport", "networking", "it", "msp"]
STACK_SITES        = [
    ("stackoverflow", "Stack Overflow",  "SO"),
    ("serverfault",   "Server Fault",    "SF"),
    ("superuser",     "Super User",      "SU"),
]

TIER_TAGS = {
    1: ["windows","microsoft","printer","password","email","outlook",
        "office","vpn","wifi","browser","antivirus","backup","reboot"],
    2: ["active-directory","group-policy","exchange","dns","dhcp",
        "vmware","hyper-v","sql-server","powershell","linux","firewall","ldap"],
    3: ["kubernetes","terraform","aws","azure","gcp","docker",
        "networking","security","sso","siem","elk","ci-cd","devops"],
}

# ── Data model ─────────────────────────────────────────────────────────────────
@dataclass
class SearchResult:
    source:          str
    source_key:      str
    tier:            int
    title:           str
    url:             str
    score:           int           = 0
    answered:        bool          = False
    answer_count:    int           = 0
    accepted_answer: str           = ""
    tags:            list[str]     = field(default_factory=list)
    snippet:         str           = ""

    @property
    def relevance_score(self) -> int:
        base = self.score * 2
        if self.answered:        base += 50
        if self.accepted_answer: base += 100
        base += self.answer_count * 5
        return base

    def to_dict(self) -> dict:
        return {
            "source":          self.source,
            "source_key":      self.source_key,
            "tier":            self.tier,
            "title":           self.title,
            "url":             self.url,
            "score":           self.score,
            "relevance_score": self.relevance_score,
            "answered":        self.answered,
            "answer_count":    self.answer_count,
            "accepted_answer": self.accepted_answer,
            "tags":            self.tags,
            "snippet":         self.snippet,
        }

# ── Helpers ────────────────────────────────────────────────────────────────────
def clean_html(raw: str) -> str:
    if not raw: return ""
    return " ".join(BeautifulSoup(raw, "html.parser").get_text().split())

def detect_tier(tags: list[str], title: str) -> int:
    combined = " ".join(tags + [title.lower()])
    for tier in (3, 2, 1):
        if any(kw in combined for kw in TIER_TAGS[tier]):
            return tier
    return 1

def deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    seen, unique = set(), []
    for r in results:
        key = r.title.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

# ── Stack Exchange ─────────────────────────────────────────────────────────────
def search_stack_exchange(query: str, max_per_site: int = 5) -> list[SearchResult]:
    results = []
    for site_key, site_name, abbr in STACK_SITES:
        try:
            params = dict(order="desc", sort="relevance", q=query,
                          site=site_key, filter="withbody",
                          pagesize=max_per_site, accepted="True")
            r = requests.get(f"{STACK_EXCHANGE_API}/search/advanced",
                             params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
            items = r.json().get("items", [])
            if not items:
                params.pop("accepted")
                items = requests.get(f"{STACK_EXCHANGE_API}/search/advanced",
                                     params=params, headers={"User-Agent": USER_AGENT},
                                     timeout=10).json().get("items", [])
            for item in items:
                tags  = item.get("tags", [])
                title = item.get("title", "")
                body  = ""
                aid   = item.get("accepted_answer_id")
                if aid:
                    try:
                        ar = requests.get(f"{STACK_EXCHANGE_API}/answers/{aid}",
                                          params={"site": site_key, "filter": "withbody"},
                                          headers={"User-Agent": USER_AGENT}, timeout=8)
                        ai = ar.json().get("items", [])
                        if ai: body = clean_html(ai[0].get("body",""))[:1000]
                    except Exception:
                        pass
                results.append(SearchResult(
                    source=site_name, source_key=abbr,
                    tier=detect_tier(tags, title), title=title,
                    url=item.get("link",""), score=item.get("score",0),
                    answered=item.get("is_answered",False),
                    answer_count=item.get("answer_count",0),
                    accepted_answer=body, tags=tags,
                    snippet=clean_html(item.get("body",""))[:300],
                ))
            time.sleep(0.4)
        except Exception as e:
            print(f"[SE:{site_name}] {e}")
    return results

# ── Reddit ─────────────────────────────────────────────────────────────────────
def search_reddit(query: str, max_per_sub: int = 3) -> list[SearchResult]:
    results = []
    headers = {"User-Agent": USER_AGENT}
    for sub in REDDIT_SUBREDDITS:
        try:
            r = requests.get(f"{REDDIT_BASE}/r/{sub}/search.json",
                             params=dict(q=query, restrict_sr="true",
                                         sort="relevance", t="all", limit=max_per_sub),
                             headers=headers, timeout=10)
            posts = r.json().get("data",{}).get("children",[])
            for post in posts:
                d     = post.get("data",{})
                title = d.get("title","")
                score = d.get("score",0)
                if d.get("removed_by_category") or score < 1: continue
                top = ""
                try:
                    cr = requests.get(f"{REDDIT_BASE}/r/{sub}/comments/{d.get('id','')}.json",
                                      params={"limit":5,"sort":"top"},
                                      headers=headers, timeout=8)
                    cd = cr.json()
                    if len(cd) > 1:
                        for c in cd[1].get("data",{}).get("children",[]):
                            b = c.get("data",{}).get("body","")
                            if b and b not in ("[deleted]","[removed]"):
                                top = b[:1000]; break
                except Exception:
                    pass
                results.append(SearchResult(
                    source=f"r/{sub}", source_key="RD",
                    tier=detect_tier([], title), title=title,
                    url=f"{REDDIT_BASE}{d.get('permalink','')}",
                    score=score, answered=bool(d.get("num_comments",0)>0),
                    answer_count=d.get("num_comments",0),
                    accepted_answer=top,
                    snippet=(d.get("selftext","") or "")[:300],
                ))
            time.sleep(1)
        except Exception as e:
            print(f"[Reddit:r/{sub}] {e}")
    return results

# ── Spiceworks ─────────────────────────────────────────────────────────────────
def search_spiceworks(query: str, max_results: int = 5) -> list[SearchResult]:
    results = []
    encoded = urllib.parse.quote_plus(query)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json",
                "Referer": "https://community.spiceworks.com/"}
    try:
        r = requests.get(f"https://community.spiceworks.com/api/search",
                         params={"q": query, "type": "topic", "page": "1"},
                         headers=headers, timeout=12)
        if r.status_code == 200 and "application/json" in r.headers.get("content-type",""):
            data   = r.json()
            topics = data.get("results", data.get("topics",[]))[:max_results]
            for t in topics:
                title = t.get("title", t.get("name",""))
                slug  = t.get("slug", t.get("id",""))
                results.append(SearchResult(
                    source="Spiceworks", source_key="SW",
                    tier=detect_tier([], title), title=title,
                    url=f"https://community.spiceworks.com/topic/{slug}",
                    score=t.get("reply_count", t.get("votes",0)),
                    answered=t.get("solved", t.get("has_accepted_answer",False)),
                    answer_count=t.get("reply_count",0),
                    snippet=clean_html(t.get("body", t.get("excerpt","")))[:300],
                ))
        else:
            # HTML scrape fallback
            r2 = requests.get(
                f"https://community.spiceworks.com/search#q={encoded}&t=topic",
                headers={"User-Agent": USER_AGENT}, timeout=12)
            soup  = BeautifulSoup(r2.text, "html.parser")
            cards = soup.select("li.search-result, div.search-result, article")[:max_results]
            for card in cards:
                a    = card.find("a", href=True)
                title = a.get_text(strip=True) if a else ""
                href  = a["href"] if a else ""
                if not title: continue
                if not href.startswith("http"):
                    href = "https://community.spiceworks.com" + href
                sp_el   = card.find("p") or card.find("span")
                snippet = sp_el.get_text(strip=True)[:300] if sp_el else ""
                results.append(SearchResult(
                    source="Spiceworks", source_key="SW",
                    tier=detect_tier([], title), title=title,
                    url=href, snippet=snippet,
                ))
    except Exception as e:
        print(f"[Spiceworks] {e}")
    return results

# ── Synthesis ──────────────────────────────────────────────────────────────────
def synthesise(results: list[SearchResult]) -> str:
    top = [r for r in results if r.accepted_answer][:5] or results[:5]
    if not top:
        return "No detailed solutions found. Try broadening your search query."
    parts = []
    for i, r in enumerate(top, 1):
        ans = r.accepted_answer or r.snippet or "No detailed answer available."
        parts.append({
            "index":  i,
            "source": r.source,
            "title":  r.title,
            "url":    r.url,
            "answer": ans,
            "tier":   r.tier,
        })
    return parts

# ── API Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/search")
def api_search():
    query          = request.args.get("q", "").strip()
    tier_filter    = request.args.get("tier", type=int)
    answered_only  = request.args.get("answered", "false").lower() == "true"
    max_stack      = request.args.get("max_stack",  5, type=int)
    max_reddit     = request.args.get("max_reddit", 3, type=int)
    max_sw         = request.args.get("max_sw",     5, type=int)

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400

    all_results = []
    all_results += search_stack_exchange(query, max_per_site=max_stack)
    all_results += search_reddit(query, max_per_sub=max_reddit)
    all_results += search_spiceworks(query, max_results=max_sw)

    all_results = deduplicate(all_results)
    if tier_filter:
        all_results = [r for r in all_results if r.tier == tier_filter]
    if answered_only:
        all_results = [r for r in all_results if r.answered or r.accepted_answer]

    all_results.sort(key=lambda r: r.relevance_score, reverse=True)

    tier_counts = {1: 0, 2: 0, 3: 0}
    for r in all_results:
        tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1

    return jsonify({
        "query":       query,
        "total":       len(all_results),
        "tier_counts": tier_counts,
        "results":     [r.to_dict() for r in all_results],
        "synthesis":   synthesise(all_results),
    })

if __name__ == "__main__":
    print("\n  🔍 IT Helpdesk Search — Web UI")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, port=5000)
