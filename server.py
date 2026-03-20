#!/usr/bin/env python3
"""
IT Helpdesk Search — Flask Backend
Uses Anthropic Claude AI with web_search tool to find and synthesise IT solutions.
"""

import os
import json
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-haiku-4-5-20251001"

TIER_KEYWORDS = {
    1: ["windows","printer","password","email","outlook","office","vpn",
        "wifi","browser","antivirus","backup","reboot","screen","sound","keyboard","mouse"],
    2: ["active-directory","group-policy","exchange","dns","dhcp","vmware",
        "hyper-v","sql","powershell","linux","firewall","ldap","server","domain"],
    3: ["kubernetes","terraform","aws","azure","gcp","docker","security",
        "sso","siem","devops","ci-cd","nginx","apache","cloud"],
}

QUICK_FIXES = {
    "internet|wifi|network|no connection|cant browse|offline|ethernet": [
        "Restart your router/modem (unplug 30 sec)",
        "Restart your computer",
        "Forget WiFi network and reconnect",
        "Check Ethernet cable is firmly plugged in",
        "Make sure Airplane mode is OFF",
        "Try opening a different website",
        "Try a different WiFi network",
        "Call your ISP if none of the above work",
    ],
    "printer|print|paper jam": [
        "Turn printer OFF and ON again",
        "Unplug USB/power, wait 10 sec, plug back in",
        "Check for and clear any paper jam",
        "Remove printer in Windows Settings and re-add",
        "Restart Print Spooler: services.msc -> Print Spooler -> Restart",
        "Check ink/toner levels",
        "Run Windows printer troubleshooter",
        "Reinstall printer driver from manufacturer website",
    ],
    "password|locked out|cant login|forgot password|credentials": [
        "Check Caps Lock is OFF",
        "Type password in Notepad first to verify it",
        "Use Forgot Password / Reset Password link",
        "Contact IT helpdesk to reset your account",
        "Wait 15 minutes if too many failed attempts",
        "Try logging in from a different device or browser",
        "Clear browser saved passwords and try again",
    ],
    "slow|sluggish|frozen|freezing|hanging|performance": [
        "Restart the computer first",
        "Close all unused programs and browser tabs",
        "Open Task Manager (Ctrl+Shift+Esc) - check CPU/RAM",
        "Run Disk Cleanup (search in Start menu)",
        "Run a full antivirus scan",
        "Check free disk space - need at least 10% free",
        "Install all pending Windows Updates",
    ],
    "email|outlook|mail|not receiving|not sending": [
        "Completely close and reopen Outlook",
        "Confirm internet connection is working",
        "Check your Junk/Spam folder",
        "Try re-entering your email password",
        "Check mailbox storage quota is not full",
        "Remove and re-add the email account",
        "Start Outlook in Safe Mode: Win+R -> outlook /safe",
    ],
    "vpn|remote|tunnel|remote desktop|rdp": [
        "Disconnect VPN and reconnect",
        "Restart your internet connection first",
        "Restart the VPN client application",
        "Check username, password and server address",
        "Try from a different network (mobile hotspot)",
        "Temporarily disable firewall/antivirus and retry",
        "Reinstall the VPN client",
    ],
    "blue screen|bsod|crash|stop error|kernel": [
        "Note the exact error code on the blue screen",
        "Restart and see if it happens again",
        "Unplug all external USB devices and retry",
        "Check Windows Update is fully current",
        "Run: sfc /scannow in CMD as Administrator",
        "Run: chkdsk /f /r in CMD as Administrator",
        "Contact IT with the exact error code",
    ],
    "sound|audio|no sound|speaker|headphone|microphone|mute": [
        "Check volume is not muted or at zero",
        "Check speaker/headphone is plugged in",
        "Right-click speaker icon -> Troubleshoot",
        "Check correct audio device is selected in Sound Settings",
        "Restart Windows Audio via services.msc",
        "Restart the computer",
        "Update audio driver via Device Manager",
    ],
}


def detect_tier(query):
    q = query.lower()
    for tier in (3, 2, 1):
        if any(kw in q for kw in TIER_KEYWORDS[tier]):
            return tier
    return 1


def get_quick_fixes(query):
    q = query.lower()
    for keywords, steps in QUICK_FIXES.items():
        if any(kw in q for kw in keywords.split("|")):
            return steps
    return []


def clean_query(raw):
    FILLERS = [
        "i cant ", "i can't ", "i cannot ", "i am unable to ", "i'm unable to ",
        "i keep getting ", "i keep ", "i have a ", "i have an ", "i have ",
        "i am getting ", "i'm getting ", "i am having ", "i'm having ",
        "my ", "how to fix ", "how do i fix ", "how do i ", "how to ",
        "please help ", "help me ", "why is ", "why does ",
        "problem with ", "issue with ", "error with ", "not able to ",
        "unable to ", "wont ", "won't ", "doesn't ", "doesnt ",
        "isn't ", "isnt ", "keeps ", "keep ", "suddenly ",
    ]
    q = raw.lower().strip()
    for filler in FILLERS:
        if q.startswith(filler):
            q = q[len(filler):]
    return q.strip() or raw.strip()


def ask_claude(query, tier):
    tier_context = {
        1: "basic end-user IT support (Tier 1). Give simple step-by-step instructions a non-technical user can follow.",
        2: "infrastructure and sysadmin (Tier 2). Include technical commands and config steps.",
        3: "advanced DevOps and cloud (Tier 3). Include detailed technical solutions and code.",
    }.get(tier, "general IT support")

    system_prompt = f"""You are an expert IT helpdesk technician specialising in {tier_context}

Search the web for real solutions from Stack Overflow, Server Fault, Super User, Reddit sysadmin/techsupport, and Spiceworks community.

Respond ONLY with a raw JSON object (no markdown, no backticks):
{{
  "summary": "One sentence description of the problem",
  "solutions": [
    {{
      "rank": 1,
      "source": "Stack Overflow",
      "title": "Solution title",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "url": "https://real-url-if-found.com",
      "votes": 0
    }}
  ],
  "root_cause": "Why this problem occurs",
  "prevention": "How to prevent this in future"
}}

Provide 2-3 practical solutions. Be specific. Steps must be actionable."""

    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
        "anthropic-beta":    "web-search-2025-03-05",
    }

    payload = {
        "model":      MODEL,
        "max_tokens": 2000,
        "system":     system_prompt,
        "tools": [{
            "type":     "web_search_20250305",
            "name":     "web_search",
            "max_uses": 4,
        }],
        "messages": [{
            "role":    "user",
            "content": f"Find IT solutions for: {query}\nSearch Stack Overflow, Server Fault, Reddit r/sysadmin and r/techsupport, and Spiceworks for the best community-verified answers.",
        }],
    }

    resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            if p.startswith("json"):
                text = p[4:].strip()
                break
            elif "{" in p:
                text = p.strip()
                break

    start = text.find("{")
    end   = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    return json.loads(text)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/search")
def api_search():
    raw_query = request.args.get("q", "").strip()
    tier      = request.args.get("tier", 0, type=int)

    if not raw_query:
        return jsonify({"error": "Missing query"}), 400
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured on server."}), 500

    query       = clean_query(raw_query)
    auto_tier   = tier if tier else detect_tier(query)
    quick_fixes = get_quick_fixes(query)

    try:
        ai_result = ask_claude(query, auto_tier)
        return jsonify({
            "query":       raw_query,
            "clean_query": query,
            "tier":        auto_tier,
            "quick_fixes": quick_fixes,
            "ai_result":   ai_result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "api_key_set": bool(ANTHROPIC_API_KEY), "model": MODEL})


if __name__ == "__main__":
    print("\n  IT Helpdesk AI Search")
    print("  export ANTHROPIC_API_KEY=your-key-here")
    print("  Open http://localhost:5000\n")
    app.run(debug=True, port=5000)
