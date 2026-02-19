#!/usr/bin/env python3
"""
Gmail HPP Monitor
-----------------
Watches a Gmail inbox for emails related to High Pressure Processing and
sends a digest alert to andrew@daijyov.com whenever new matches arrive.

Usage:
    python gmail_monitor.py            # run once (intended for cron)
    python gmail_monitor.py --auth     # just re-authenticate (refresh token)
"""

import argparse
import base64
import email
import json
import logging
import os
import pickle
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()

# OAuth2 scopes needed (read mail + send mail)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Keywords to match (case-insensitive; checked in subject, body, sender)
HPP_KEYWORDS = [
    "HPP",
    "high pressure processing",
    "high-pressure processing",
    "pascalisation",
    "pascalization",
    "Hiperbaric",
    "Quintus",
]

# Build the Gmail query string (OR of all keywords in subject OR body)
# Gmail search supports quoted phrases and OR logic.
GMAIL_QUERY_TERMS = " OR ".join(
    f'"{kw}"' if " " in kw or "-" in kw else kw for kw in HPP_KEYWORDS
)
GMAIL_SEARCH_QUERY = f"({GMAIL_QUERY_TERMS})"

ALERT_RECIPIENT = "andrew@daijyov.com"
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
TOKEN_FILE = SCRIPT_DIR / "token.pickle"
LAST_RUN_FILE = SCRIPT_DIR / ".last_run_timestamp"
LOG_FILE = SCRIPT_DIR / "hpp_monitor.log"

# Max snippet length shown in digest
SNIPPET_MAX_LEN = 300

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Authenticate via OAuth2 and return an authorised Gmail API service."""
    creds = None

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as fh:
            creds = pickle.load(fh)

    # Refresh or re-authenticate when token is missing / expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing expired OAuth2 token …")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                log.error(
                    "credentials.json not found at %s\n"
                    "Download it from Google Cloud Console → APIs & Services → "
                    "Credentials and place it next to this script.",
                    CREDENTIALS_FILE,
                )
                sys.exit(1)
            log.info("Starting OAuth2 flow — a browser window will open …")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as fh:
            pickle.dump(creds, fh)
        log.info("Token saved to %s", TOKEN_FILE)

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Timestamp helpers (epoch seconds stored as plain text)
# ---------------------------------------------------------------------------

def load_last_run_timestamp() -> int:
    """Return the epoch-second timestamp of the last successful run, or 0."""
    if LAST_RUN_FILE.exists():
        try:
            ts = int(LAST_RUN_FILE.read_text().strip())
            log.info("Last run timestamp: %s", datetime.fromtimestamp(ts, tz=timezone.utc))
            return ts
        except ValueError:
            log.warning("Corrupt timestamp file — will check all mail.")
    return 0


def save_last_run_timestamp(ts: int) -> None:
    LAST_RUN_FILE.write_text(str(ts))
    log.info("Saved last-run timestamp: %d", ts)


# ---------------------------------------------------------------------------
# Email fetching & parsing
# ---------------------------------------------------------------------------

def epoch_to_gmail_date(epoch_secs: int) -> str:
    """Convert epoch seconds to a Gmail 'after:' date filter (YYYY/MM/DD)."""
    dt = datetime.fromtimestamp(epoch_secs, tz=timezone.utc)
    return dt.strftime("%Y/%m/%d")


def fetch_matching_messages(service, since_epoch: int) -> list[dict]:
    """
    Search Gmail for HPP-related messages received after *since_epoch*.
    Returns a list of parsed message dicts.
    """
    query = GMAIL_SEARCH_QUERY
    if since_epoch > 0:
        after_date = epoch_to_gmail_date(since_epoch)
        query = f"{query} after:{after_date}"

    log.info("Gmail query: %s", query)

    messages_found = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            result = service.users().messages().list(**kwargs).execute()
        except HttpError as exc:
            log.error("Gmail API error during message list: %s", exc)
            raise

        batch = result.get("messages", [])
        messages_found.extend(batch)
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    log.info("Found %d candidate message(s).", len(messages_found))

    parsed = []
    for msg_stub in messages_found:
        details = fetch_message_details(service, msg_stub["id"])
        if details:
            # Secondary filter: only messages strictly newer than last run
            if details["epoch"] > since_epoch:
                parsed.append(details)

    # Newest first
    parsed.sort(key=lambda m: m["epoch"], reverse=True)
    log.info("%d new message(s) after timestamp filter.", len(parsed))
    return parsed


def fetch_message_details(service, msg_id: str) -> dict | None:
    """Fetch and parse a single Gmail message. Returns None on error."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except HttpError as exc:
        log.error("Could not fetch message %s: %s", msg_id, exc)
        return None

    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("subject", "(no subject)")
    sender = headers.get("from", "(unknown sender)")
    date_str = headers.get("date", "")
    epoch = int(msg.get("internalDate", 0)) // 1000  # internalDate is milliseconds

    # Extract plain-text snippet from body
    snippet = extract_snippet(msg)

    return {
        "id": msg_id,
        "subject": subject,
        "sender": sender,
        "date": date_str,
        "epoch": epoch,
        "snippet": snippet,
    }


def extract_snippet(msg: dict) -> str:
    """
    Walk the MIME tree to find the first plain-text part.
    Falls back to Gmail's built-in snippet.
    """
    def walk_parts(payload):
        mime_type = payload.get("mimeType", "")
        body = payload.get("body", {})
        data = body.get("data")

        if mime_type == "text/plain" and data:
            try:
                text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                return text.strip()
            except Exception:
                pass

        for part in payload.get("parts", []):
            result = walk_parts(part)
            if result:
                return result
        return ""

    full_text = walk_parts(msg.get("payload", {}))
    if not full_text:
        # Fall back to the API-provided snippet (always plain text, max ~200 chars)
        full_text = msg.get("snippet", "")

    # Truncate and clean whitespace
    cleaned = " ".join(full_text.split())
    return cleaned[:SNIPPET_MAX_LEN] + ("…" if len(cleaned) > SNIPPET_MAX_LEN else "")


# ---------------------------------------------------------------------------
# Alert email composition and sending
# ---------------------------------------------------------------------------

def build_alert_email(messages: list[dict]) -> tuple[str, str]:
    """Return (plain_text_body, html_body) for the digest email."""
    count = len(messages)
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ----- Plain text -----
    lines = [
        f"HPP Monitor — Digest ({now_str})",
        f"Found {count} new email(s) matching HPP keywords.\n",
        "=" * 60,
    ]
    for i, m in enumerate(messages, 1):
        lines += [
            f"\n[{i}] {m['subject']}",
            f"    From   : {m['sender']}",
            f"    Date   : {m['date']}",
            f"    Snippet: {m['snippet']}",
        ]
    lines.append("\n" + "=" * 60)
    lines.append("Sent by HPP Gmail Monitor — github.com/Ghosty61/HPP_Final_MVP")
    plain = "\n".join(lines)

    # ----- HTML -----
    rows = ""
    for i, m in enumerate(messages, 1):
        rows += f"""
        <tr style="background:{'#f9f9f9' if i % 2 else '#ffffff'}">
          <td style="padding:8px;border:1px solid #ddd;font-weight:bold">{i}</td>
          <td style="padding:8px;border:1px solid #ddd">{_esc(m['subject'])}</td>
          <td style="padding:8px;border:1px solid #ddd">{_esc(m['sender'])}</td>
          <td style="padding:8px;border:1px solid #ddd;white-space:nowrap">{_esc(m['date'])}</td>
          <td style="padding:8px;border:1px solid #ddd;color:#555;font-size:0.9em">{_esc(m['snippet'])}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;margin:20px">
  <h2 style="color:#1a73e8">HPP Monitor — Email Digest</h2>
  <p><strong>{count} new email(s)</strong> matching HPP keywords — {now_str}</p>
  <table style="border-collapse:collapse;width:100%">
    <thead>
      <tr style="background:#1a73e8;color:#fff">
        <th style="padding:8px;border:1px solid #ddd">#</th>
        <th style="padding:8px;border:1px solid #ddd">Subject</th>
        <th style="padding:8px;border:1px solid #ddd">From</th>
        <th style="padding:8px;border:1px solid #ddd">Date</th>
        <th style="padding:8px;border:1px solid #ddd">Snippet</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="font-size:0.8em;color:#aaa;margin-top:20px">
    Sent by HPP Gmail Monitor · github.com/Ghosty61/HPP_Final_MVP
  </p>
</body>
</html>"""
    return plain, html


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def send_alert(service, messages: list[dict]) -> bool:
    """Compose and send the digest email. Returns True on success."""
    plain, html = build_alert_email(messages)
    count = len(messages)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[HPP Monitor] {count} new HPP-related email(s) found"
    msg["To"] = ALERT_RECIPIENT
    msg["From"] = "me"  # Gmail API replaces this with the authenticated address

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        log.info("Alert digest sent to %s (%d message(s)).", ALERT_RECIPIENT, count)
        return True
    except HttpError as exc:
        log.error("Failed to send alert email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Gmail HPP Monitor")
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Re-run OAuth2 authentication flow and exit.",
    )
    parser.add_argument(
        "--since",
        type=int,
        default=None,
        metavar="EPOCH",
        help="Override the 'since' epoch timestamp (for testing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Find emails but do NOT send the alert or update timestamp.",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("HPP Gmail Monitor starting …")

    service = get_gmail_service()

    if args.auth:
        log.info("Authentication complete. Exiting.")
        return

    since = args.since if args.since is not None else load_last_run_timestamp()
    run_start_epoch = int(datetime.now(tz=timezone.utc).timestamp())

    try:
        messages = fetch_matching_messages(service, since)
    except HttpError as exc:
        log.error("Unrecoverable Gmail API error: %s", exc)
        sys.exit(1)

    if not messages:
        log.info("No new HPP-related emails since last run. Nothing to do.")
    else:
        log.info("Preparing digest for %d message(s) …", len(messages))
        if args.dry_run:
            log.info("[DRY RUN] Would send digest — printing to stdout instead.")
            plain, _ = build_alert_email(messages)
            print(plain)
        else:
            send_alert(service, messages)

    if not args.dry_run:
        save_last_run_timestamp(run_start_epoch)

    log.info("HPP Gmail Monitor finished.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
