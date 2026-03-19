# IT Helpdesk Search — PythonAnywhere Deployment Guide
# User: pilos → https://pilos.pythonanywhere.com

## YOUR FILE STRUCTURE ON PYTHONANYWHERE
```
/home/pilos/it-helpdesk-search/
  ├── server.py            ← Flask backend
  ├── requirements.txt     ← Python dependencies
  └── static/
       └── index.html      ← Web GUI frontend
```

---

## STEP 1 — Open a Bash Console on PythonAnywhere
- Dashboard → Consoles → Bash → New console

## STEP 2 — Create project folder & upload files
```bash
mkdir -p ~/it-helpdesk-search/static
```
Then upload files via PythonAnywhere Files tab:
- server.py          → /home/pilos/it-helpdesk-search/server.py
- requirements.txt   → /home/pilos/it-helpdesk-search/requirements.txt
- index.html         → /home/pilos/it-helpdesk-search/static/index.html

## STEP 3 — Create a virtual environment & install dependencies
In the Bash console run:
```bash
cd ~/it-helpdesk-search
mkvirtualenv --python=/usr/bin/python3.10 helpdesk-venv
pip install -r requirements.txt
```

## STEP 4 — Create the Web App
- Web tab → Add a new web app
- Choose: Manual Configuration
- Python version: 3.10
- Source code: /home/pilos/it-helpdesk-search
- Working directory: /home/pilos/it-helpdesk-search

## STEP 5 — Set the Virtualenv
- Web tab → Virtualenv section
- Enter: helpdesk-venv  (or full path: /home/pilos/.virtualenvs/helpdesk-venv)

## STEP 6 — Edit the WSGI File
- Web tab → click the WSGI configuration file link
- Delete ALL existing content
- Paste the contents of wsgi_pythonanywhere.py
- Save

## STEP 7 — Add Static Files mapping
- Web tab → Static Files section → Add:
  URL: /static/    Directory: /home/pilos/it-helpdesk-search/static

## STEP 8 — Reload
- Web tab → big green Reload button

## Your app is live at:
https://pilos.pythonanywhere.com
