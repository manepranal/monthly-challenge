"""Pull a REAL inbox into the Deal Organizer — Gmail (or any IMAP) edition.

The fixtures demo and this fetcher meet at the same contract: a folder holding
`inbox.json` + `attachments/`. This script logs into a real mailbox over IMAP,
downloads recent messages *and their attachment files*, and materializes that
folder under `live-inbox-gmail/` (gitignored — real mail never lands in git).
Everything downstream — classify, dates, organize, even watch mode — runs on it
unchanged:

    export GMAIL_USER=you@gmail.com
    export GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx     # Google App Password, see below
    ./run.sh gmail                        # fetch recent inbox -> organize it
    ./run.sh gmail 123 Maple              # only mail matching a search
    DEAL_PROPERTY="123 Maple Ave, Rye, NY" ./run.sh gmail 123 Maple

Gmail needs an App Password (Google Account -> Security -> 2-Step Verification
-> App passwords); the account password itself will not work. Any other IMAP
provider works too: set IMAP_HOST (and optionally IMAP_FOLDER).

Safety: the mailbox is opened READ-ONLY (nothing is marked read, moved, or
deleted), credentials come from env vars only, and all output stays inside the
project's gitignored `live-inbox-gmail/` folder.

Tunables (env): GMAIL_DAYS=14  GMAIL_MAX=25  IMAP_HOST=imap.gmail.com
                IMAP_FOLDER=INBOX  DEAL_PROPERTY="<label for the deal folder>"

Progress prints to stderr; stdout emits exactly one line — the materialized
folder path — so `./run.sh gmail` can pipe it straight into main.py.

`python3 fetch_gmail.py selftest` exercises the whole materialize path on
synthetic MIME messages (no network, no credentials) — proof the real-email
plumbing works before anyone types an app password.
"""

import email
import email.policy
import html.parser
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
DEST_ROOT = ROOT / "live-inbox-gmail"

MAX_BODY_CHARS = 6000            # keep Claude's context focused on recent mail
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- HTML -> text

class _TextExtractor(html.parser.HTMLParser):
    _SKIP = {"script", "style", "head"}

    def __init__(self):
        super().__init__()
        self.chunks, self._skip_depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.chunks.append(data.strip())


def html_to_text(markup: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(markup)
    except Exception:
        return markup
    return "\n".join(p.chunks)


# ------------------------------------------------------------- MIME -> record

def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^\w.\- ]+", "_", name)
    return name or "attachment.bin"


def parse_message(msg, mid: str, attach_dir: Path) -> dict:
    """One parsed email -> the inbox.json record shape, attachments saved."""
    body_plain, body_html = "", ""
    saved = []
    for part in msg.walk():
        if part.get_content_type().startswith("multipart/"):
            continue
        fname = part.get_filename()
        if fname or part.get_content_disposition() == "attachment":
            payload = part.get_payload(decode=True) or b""
            if not payload:
                continue
            if len(payload) > MAX_ATTACHMENT_BYTES:
                log(f"      (skipping oversized attachment {fname}, "
                    f"{len(payload) // (1024 * 1024)}MB)")
                continue
            name = _safe_filename(fname)
            if (attach_dir / name).exists():          # collide across emails
                name = f"{mid}-{name}"
            attach_dir.mkdir(parents=True, exist_ok=True)
            (attach_dir / name).write_bytes(payload)
            saved.append(name)
        elif part.get_content_type() == "text/plain" and not body_plain:
            body_plain = part.get_payload(decode=True).decode(
                part.get_content_charset() or "utf-8", errors="replace")
        elif part.get_content_type() == "text/html" and not body_html:
            body_html = part.get_payload(decode=True).decode(
                part.get_content_charset() or "utf-8", errors="replace")

    body = (body_plain or html_to_text(body_html)).strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n[... truncated ...]"

    try:
        date = parsedate_to_datetime(msg.get("Date", "")).isoformat()
    except Exception:
        date = msg.get("Date", "")

    return {
        "id": mid,
        "from": str(msg.get("From", "")),
        "to": str(msg.get("To", "")),
        "date": date,
        "subject": str(msg.get("Subject", "")),
        "body": body,
        "attachments": saved,
    }


# ------------------------------------------------------------------ the fetch

def fetch(search_terms: str) -> Path:
    user = os.environ.get("GMAIL_USER") or os.environ.get("IMAP_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("IMAP_PASSWORD")
    if not user or not pw:
        sys.exit(
            "Set GMAIL_USER and GMAIL_APP_PASSWORD first (App Password: Google\n"
            "Account -> Security -> 2-Step Verification -> App passwords).\n"
            "Non-Gmail IMAP: set IMAP_USER / IMAP_PASSWORD / IMAP_HOST instead.")

    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    days = int(os.environ.get("GMAIL_DAYS", "14"))
    cap = int(os.environ.get("GMAIL_MAX", "25"))

    label = (os.environ.get("DEAL_PROPERTY")
             or search_terms
             or f"Live Inbox ({user})")
    dest = DEST_ROOT / re.sub(r"[^A-Za-z0-9]+", "-",
                              label.split(",")[0]).strip("-")[:60]
    attach_dir = dest / "attachments"

    log(f"Connecting to {host} as {user} (read-only) ...")
    conn = imaplib.IMAP4_SSL(host)
    try:
        conn.login(user, pw)
        conn.select(f'"{folder}"', readonly=True)   # never mutates the mailbox

        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        uids = None
        if search_terms and "gmail" in host:
            # Gmail exposes its full search syntax through X-GM-RAW.
            ok, data = conn.uid("SEARCH", "X-GM-RAW",
                                f'"{search_terms} newer_than:{days}d"')
            if ok == "OK":
                uids = data[0].split()
        if uids is None:
            crit = ["SINCE", since]
            if search_terms:
                crit += ["TEXT", f'"{search_terms}"']
            ok, data = conn.uid("SEARCH", None, *crit)
            if ok != "OK":
                sys.exit(f"IMAP search failed: {data}")
            uids = data[0].split()

        uids = uids[-cap:]           # newest N
        query = f' matching "{search_terms}"' if search_terms else ""
        log(f"Found {len(uids)} messages{query} from the last {days} days "
            f"(cap {cap}).")
        if not uids:
            sys.exit("Nothing to organize — widen GMAIL_DAYS or the search.")

        if dest.exists():
            import shutil
            shutil.rmtree(dest)      # our own gitignored folder — safe to rebuild
        dest.mkdir(parents=True)

        emails = []
        for i, uid in enumerate(uids, 1):
            ok, data = conn.uid("FETCH", uid, "(RFC822)")
            if ok != "OK" or not data or data[0] is None:
                log(f"  [{i}/{len(uids)}] fetch failed for uid "
                    f"{uid.decode()} — skipping")
                continue
            msg = email.message_from_bytes(data[0][1],
                                           policy=email.policy.default)
            rec = parse_message(msg, f"g{i}", attach_dir)
            emails.append(rec)
            att = f"  [{len(rec['attachments'])} att]" if rec["attachments"] else ""
            log(f"  [{i}/{len(uids)}] {rec['subject'][:60]}{att}")
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    inbox = {
        "deal": {"id": "live-gmail", "property": label, "buyers": ""},
        "emails": emails,
    }
    (dest / "inbox.json").write_text(json.dumps(inbox, indent=2))
    n_att = sum(len(e["attachments"]) for e in emails)
    log(f"\nMaterialized {len(emails)} emails, {n_att} attachments -> {dest}/")
    return dest


# ------------------------------------------------------------------- selftest

def selftest() -> Path:
    """Prove the materialize path on synthetic MIME — no network, no creds."""
    from email.message import EmailMessage

    dest = DEST_ROOT / "selftest"
    attach_dir = dest / "attachments"
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    m1 = EmailMessage()
    m1["From"] = "counsel@example.com"
    m1["To"] = "agent@example.com"
    m1["Subject"] = "Executed contract — 9 Test Lane"
    m1["Date"] = "Wed, 15 Jul 2026 09:00:00 -0400"
    m1.set_content("Attached is the executed contract. Closing is September 5, "
                   "2026; inspection contingency runs through July 18, 2026. "
                   "Please confirm receipt.")
    m1.add_attachment(
        b"PURCHASE AGREEMENT - 9 Test Lane\nClosing Date: September 5, 2026\n"
        b"Inspection contingency: July 18, 2026\n",
        maintype="text", subtype="plain", filename="Contract_9_Test_Lane.txt")

    m2 = EmailMessage()
    m2["From"] = "lender@example.com"
    m2["To"] = "agent@example.com"
    m2["Subject"] = "Rate lock reminder"
    m2["Date"] = "Thu, 16 Jul 2026 10:30:00 -0400"
    m2.set_content("<html><body><p>Rates move <b>Friday</b> — reply to lock "
                   "before then.</p><style>p{}</style></body></html>",
                   subtype="html")

    emails = [parse_message(m, f"g{i}", attach_dir)
              for i, m in enumerate((m1, m2), 1)]
    (dest / "inbox.json").write_text(json.dumps(
        {"deal": {"id": "selftest", "property": "9 Test Lane (selftest)",
                  "buyers": ""}, "emails": emails}, indent=2))

    # the contract must round-trip through fetch.load_inbox with its text intact
    import fetch
    box = fetch.load_inbox(str(dest))
    a = box["emails"][0]["attachments"][0]
    assert a["filename"] == "Contract_9_Test_Lane.txt", a
    assert "September 5, 2026" in a["text"], "attachment text lost"
    assert Path(a["path"]).exists(), "attachment binary missing"
    assert "lock" in box["emails"][1]["body"], "html body not converted"
    assert "<b>" not in box["emails"][1]["body"], "html tags leaked"
    log("selftest OK — synthetic MIME materialized, attachments + bodies "
        "round-trip through fetch.load_inbox")
    return dest


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        out = selftest()
    else:
        out = fetch(" ".join(args).strip())
    print(out)   # stdout contract: exactly one line, the folder path
