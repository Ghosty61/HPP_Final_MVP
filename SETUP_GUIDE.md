# HPP Gmail Monitor — Setup Guide

This guide walks you through every step: Google Cloud project, Gmail API, OAuth2 credentials, first run, and hourly cron scheduling.

---

## Prerequisites

- Python 3.11 or later
- A terminal (macOS/Linux) or WSL on Windows
- A Google account that owns the Gmail inbox you want to monitor

---

## Step 1 — Create a Google Cloud Project

1. Go to **https://console.cloud.google.com/**
2. Click the project drop-down at the top → **New Project**
3. Name it something like `hpp-gmail-monitor` → click **Create**
4. Make sure the new project is selected in the top drop-down before continuing

---

## Step 2 — Enable the Gmail API

1. In the left sidebar go to **APIs & Services → Library**
2. Search for **Gmail API** → click it → click **Enable**

---

## Step 3 — Configure the OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External** → click **Create**
3. Fill in the required fields:
   - App name: `HPP Gmail Monitor`
   - User support email: your Gmail address
   - Developer contact email: your Gmail address
4. Click **Save and Continue** through Scopes and Test Users (no changes needed)
5. Back on the summary page click **Publish App** → **Confirm**
   > Alternatively, leave it in "Testing" and add your Gmail address as a test user under **Test users → Add Users**

---

## Step 4 — Create OAuth2 Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: `HPP Monitor Desktop Client`
5. Click **Create**
6. Click **Download JSON** on the confirmation dialog
7. Rename the downloaded file to exactly `credentials.json`
8. Move it into the same directory as `gmail_monitor.py`

Your directory should look like:

```
HPP_Final_MVP/
├── gmail_monitor.py
├── requirements.txt
├── credentials.json      ← just added (never commit this)
└── SETUP_GUIDE.md
```

---

## Step 5 — Install Python Dependencies

```bash
# (Recommended) create a virtual environment first
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## Step 6 — Authenticate (First Run)

Run the auth flow once. A browser window will open asking you to sign in with Google and grant the requested permissions (read mail + send mail).

```bash
python gmail_monitor.py --auth
```

What happens:
1. Browser opens at accounts.google.com
2. You log in and click **Allow**
3. The script saves `token.pickle` next to itself — this token is reused on every subsequent run and auto-refreshed when it expires

> If you see a "Google hasn't verified this app" warning, click **Advanced → Go to HPP Gmail Monitor (unsafe)**. This is expected for personal/internal OAuth apps.

---

## Step 7 — Test Run

Do a dry run to confirm emails are found without actually sending an alert:

```bash
python gmail_monitor.py --dry-run
```

If matches exist they will be printed to stdout. Check `hpp_monitor.log` for the full run log.

Run for real (sends the alert email if matches are found):

```bash
python gmail_monitor.py
```

---

## Step 8 — Schedule with Cron (runs every hour)

```bash
crontab -e
```

Add this line (adjust the paths to match your system):

```cron
0 * * * * /path/to/HPP_Final_MVP/.venv/bin/python /path/to/HPP_Final_MVP/gmail_monitor.py >> /path/to/HPP_Final_MVP/hpp_monitor.log 2>&1
```

**How to find your paths:**

```bash
# Full path to python inside the venv
which python   # run after 'source .venv/bin/activate'

# Full path to script directory
pwd            # run from inside HPP_Final_MVP/
```

**Example with real paths:**

```cron
0 * * * * /home/andrew/HPP_Final_MVP/.venv/bin/python /home/andrew/HPP_Final_MVP/gmail_monitor.py >> /home/andrew/HPP_Final_MVP/hpp_monitor.log 2>&1
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano). Verify with:

```bash
crontab -l
```

---

## How It Works

| File | Purpose |
|------|---------|
| `credentials.json` | OAuth2 client secret downloaded from Google Cloud (**never commit**) |
| `token.pickle` | Saved OAuth2 access + refresh token (**never commit**) |
| `.last_run_timestamp` | Epoch seconds of last successful run — prevents duplicate alerts |
| `hpp_monitor.log` | Full activity log for every run |

### Email search query

The script searches Gmail using:

```
("HPP" OR "high pressure processing" OR "high-pressure processing" OR "pascalisation" OR "pascalization" OR "Hiperbaric" OR "Quintus") after:YYYY/MM/DD
```

The `after:` filter is set to the date of the last run so only genuinely new emails are reported.

### Alert email

When matches are found, a digest is sent to `andrew@daijyov.com` from your own Gmail address containing:

- Sender
- Subject
- Date
- A plain-text snippet (up to 300 characters)

---

## Command Reference

```
python gmail_monitor.py              Run normally (check → alert → save timestamp)
python gmail_monitor.py --auth       Re-authenticate only (refresh token.pickle)
python gmail_monitor.py --dry-run    Check & print matches, skip send & timestamp
python gmail_monitor.py --since 0    Check ALL mail (ignore saved timestamp)
python gmail_monitor.py --since 1700000000   Check mail since a specific epoch
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `credentials.json not found` | Place the downloaded OAuth JSON file next to the script and name it exactly `credentials.json` |
| Browser doesn't open during auth | Run `python gmail_monitor.py --auth` on a machine with a desktop browser; copy `token.pickle` to the server afterwards |
| `Token has been expired or revoked` | Delete `token.pickle` and re-run `--auth` |
| Alert email not received | Check spam folder; confirm the sending Gmail address is the same one that owns the inbox being monitored |
| No emails found (but you expect some) | Run with `--since 0` to scan all mail; add `--dry-run` to avoid sending |
| Cron not running | Confirm full absolute paths in crontab; check `/var/log/syslog` or `journalctl -u cron` for cron errors |

---

## Security Notes

- `credentials.json` and `token.pickle` are in `.gitignore` — **do not commit them**
- The OAuth scope is `gmail.readonly` + `gmail.send` — the script cannot delete or modify any mail
- The token auto-refreshes; you only need to re-authenticate if you revoke access in your Google Account settings
