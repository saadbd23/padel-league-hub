# ⚡ Replit Quick Start

Run Padel League Hub on Replit (Pro) directly from GitHub.

---

## 1) Import the Repo
- In Replit, click "+ Create Repl" → "Import from GitHub"
- Paste your GitHub repo URL
- Click "Import"

Replit will detect `.replit` and `replit.nix` and prepare the environment.

---

## 2) Add Secrets (Environment Variables)
In Replit → Tools → Secrets, add:

Required:
- SECRET_KEY = generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- ADMIN_PASSWORD = choose a strong password
- VERIFY_TOKEN = any random string (for webhook security)
- APP_BASE_URL = https://<your-repl-name>.<your-username>.repl.co

Optional (Notifications):
- WHATSAPP_API_KEY, WHATSAPP_PHONE_ID
- EMAIL_SENDER, EMAIL_PASSWORD, SMTP_SERVER=smtp.gmail.com, SMTP_PORT=587

Database (default is SQLite, no secret needed):
- DATABASE_URI = sqlite:///instance/league.db

---

## 3) Run
Click the green Run button.

The first run will:
- Install dependencies
- Ensure `instance/` exists for SQLite
- Start the server with Gunicorn on `$PORT`

Your app will be accessible at the Replit URL shown in the top-right.

---

## 4) First-Time Setup
The app auto-initializes the database on startup. Then:
- Visit `/admin`
- Login using the `ADMIN_PASSWORD` secret

---

## 5) Notes
- Replit assigns `$PORT` automatically; the app binds to it
- SQLite DB lives under `instance/league.db` and persists between runs
- For production-grade DB, use an external Postgres and set `DATABASE_URL`

---

## 6) Troubleshooting
- If dependencies fail, open the Shell and run: `pip install -r requirements.txt`
- If you see secret errors, verify Secrets are set
- If DB errors persist, delete `instance/league.db` (data loss!) and re-run
