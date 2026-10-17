#!/usr/bin/env python3
"""
Copenhell-vagt: tjekker copenhell.dk/billetter for en-dagsbilletter (onsdag)
og sender en mail, når de dukker op.

Konfiguration via miljøvariabler (GitHub Secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM (valgfri), MAIL_TO
Valgfri:
  TEST_MAIL=1   -> send en testmail og stop
"""
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import unescape
from pathlib import Path

URL = "https://www.copenhell.dk/billetter"
BUY_URL = "https://www.ticketmaster.dk/event/1010238744?language=da-dk&brand=copenhelldk"
STATE_FILE = Path(__file__).with_name("state.json")
FAIL_ALERT_AFTER = 24  # ca. 6 timers fejl i træk -> advarselsmail

# Mønstre der tyder på en-dags-/onsdagsbilletter.
# "4-DAGSBILLET" (den nuværende billet) filtreres fra.
PATTERNS = [
    r"\b\w*dags?billet",  # dagsbillet, endagsbillet, 1-dagsbillet, onsdagsbillet (4-dags filtreres i find_hits)
    r"\b(?:1|en|én)[\s-]?dags\b",                                            # 1-dags, en-dags
    r"\bonsdag\b",
    r"\bday[\s-]*ticket",
    r"\bwednesday\b",
    r"\bdagbillet",
]


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text))


def find_hits(text: str) -> list[str]:
    hits = []
    for pat in PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            word = m.group(0)
            # Spring over den kendte 4-dagsbillet i alle stavemåder
            before = text[max(0, m.start() - 6):m.start()].lower()
            if re.search(r"[2-5]\s*-?\s*$", before) or before.endswith("fire-") or before.endswith("fire "):
                continue
            if re.match(r"(?i)(fire|tre|to|[2-5])-?dags?billet", word):
                continue
            snippet = text[max(0, m.start() - 70):m.end() + 70].strip()
            hits.append(snippet)
    # fjern dubletter, bevar rækkefølge
    return list(dict.fromkeys(hits))


def send_mail(subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    to = os.environ["MAIL_TO"].strip().replace("mailto:", "").strip(" \t\r\n\"'<>")
    sender = os.environ.get("MAIL_FROM") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.send_message(msg)
    print(f"Mail sendt til {to}: {subject}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    if os.environ.get("TEST_MAIL") == "1":
        send_mail("Copenhell-vagt: testmail ✅",
                  "Det virker! Du får en mail her, når der kommer en-dagsbilletter "
                  f"til onsdag på Copenhell.\n\nOvervåger: {URL}")
        return 0

    state = load_state()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    try:
        text = fetch_text(URL)
    except Exception as e:
        fails = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = fails
        print(f"Kunne ikke hente siden ({fails} gang(e) i træk): {e}")
        if fails == FAIL_ALERT_AFTER:
            try:
                send_mail("Copenhell-vagt: kan ikke nå copenhell.dk ⚠️",
                          f"Overvågningen har ikke kunnet hente {URL} {fails} gange i træk.\n"
                          f"Sidste fejl: {e}\n\nTjek siden manuelt, og kig evt. i GitHub Actions-loggen.")
            except Exception as me:
                print(f"Kunne heller ikke sende advarselsmail: {me}")
        save_state(state)
        return 0

    state["consecutive_failures"] = 0
    state["last_ok_check_day"] = today  # skrives max én gang i døgnet -> holder repoet "aktivt"

    if "4-dagsbillet" not in text.lower() and "dagsbillet" not in text.lower():
        print("Advarsel: siden ser anderledes ud end forventet (ingen 'dagsbillet' fundet).")

    hits = find_hits(text)
    if hits:
        print("FUNDET mulige en-dagsbilletter:")
        for h in hits:
            print("  -", h)
        key = "|".join(sorted(hits))
        if state.get("alerted_key") != key:
            body = (
                "Der ser ud til at være kommet en-dagsbilletter (onsdag) til Copenhell!\n\n"
                f"Billetsiden: {URL}\n"
                f"Ticketmaster: {BUY_URL}\n\n"
                "Det fandt overvågningen på siden:\n\n"
                + "\n\n".join(f"• …{h}…" for h in hits[:10])
                + "\n\nSkynd dig! 🤘"
            )
            send_mail("🤘 COPENHELL: Onsdagsbilletter er måske på salg NU!", body)
            state["alerted_key"] = key
            state["alerted_at"] = now.isoformat(timespec="seconds")
        else:
            print("Allerede sendt mail om præcis disse fund – sender ikke igen.")
    else:
        print("Ingen en-dagsbilletter endnu.")
        state.pop("alerted_key", None)

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Copenhell-vagt: tjekker copenhell.dk/billetter for en-dagsbilletter (onsdag)
og sender en mail, når de dukker op.

Konfiguration via miljøvariabler (GitHub Secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM (valgfri), MAIL_TO
Valgfri:
  TEST_MAIL=1   -> send en testmail og stop
"""
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import unescape
from pathlib import Path

URL = "https://www.copenhell.dk/billetter"
BUY_URL = "https://www.ticketmaster.dk/event/1010238744?language=da-dk&brand=copenhelldk"
STATE_FILE = Path(__file__).with_name("state.json")
FAIL_ALERT_AFTER = 24  # ca. 6 timers fejl i træk -> advarselsmail

# Mønstre der tyder på en-dags-/onsdagsbilletter.
# "4-DAGSBILLET" (den nuværende billet) filtreres fra.
PATTERNS = [
    r"\b\w*dags?billet",  # dagsbillet, endagsbillet, 1-dagsbillet, onsdagsbillet (4-dags filtreres i find_hits)
    r"\b(?:1|en|én)[\s-]?dags\b",                                            # 1-dags, en-dags
    r"\bonsdag\b",
    r"\bday[\s-]*ticket",
    r"\bwednesday\b",
    r"\bdagbillet",
]


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text))


def find_hits(text: str) -> list[str]:
    hits = []
    for pat in PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            word = m.group(0)
            # Spring over den kendte 4-dagsbillet i alle stavemåder
            before = text[max(0, m.start() - 6):m.start()].lower()
            if re.search(r"[2-5]\s*-?\s*$", before) or before.endswith("fire-") or before.endswith("fire "):
                continue
            if re.match(r"(?i)(fire|tre|to|[2-5])-?dags?billet", word):
                continue
            snippet = text[max(0, m.start() - 70):m.end() + 70].strip()
            hits.append(snippet)
    # fjern dubletter, bevar rækkefølge
    return list(dict.fromkeys(hits))


def send_mail(subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    to = os.environ["MAIL_TO"]
    sender = os.environ.get("MAIL_FROM") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.send_message(msg)
    print(f"Mail sendt til {to}: {subject}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    if os.environ.get("TEST_MAIL") == "1":
        send_mail("Copenhell-vagt: testmail ✅",
                  "Det virker! Du får en mail her, når der kommer en-dagsbilletter "
                  f"til onsdag på Copenhell.\n\nOvervåger: {URL}")
        return 0

    state = load_state()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    try:
        text = fetch_text(URL)
    except Exception as e:
        fails = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = fails
        print(f"Kunne ikke hente siden ({fails} gang(e) i træk): {e}")
        if fails == FAIL_ALERT_AFTER:
            try:
                send_mail("Copenhell-vagt: kan ikke nå copenhell.dk ⚠️",
                          f"Overvågningen har ikke kunnet hente {URL} {fails} gange i træk.\n"
                          f"Sidste fejl: {e}\n\nTjek siden manuelt, og kig evt. i GitHub Actions-loggen.")
            except Exception as me:
                print(f"Kunne heller ikke sende advarselsmail: {me}")
        save_state(state)
        return 0

    state["consecutive_failures"] = 0
    state["last_ok_check_day"] = today  # skrives max én gang i døgnet -> holder repoet "aktivt"

    if "4-dagsbillet" not in text.lower() and "dagsbillet" not in text.lower():
        print("Advarsel: siden ser anderledes ud end forventet (ingen 'dagsbillet' fundet).")

    hits = find_hits(text)
    if hits:
        print("FUNDET mulige en-dagsbilletter:")
        for h in hits:
            print("  -", h)
        key = "|".join(sorted(hits))
        if state.get("alerted_key") != key:
            body = (
                "Der ser ud til at være kommet en-dagsbilletter (onsdag) til Copenhell!\n\n"
                f"Billetsiden: {URL}\n"
                f"Ticketmaster: {BUY_URL}\n\n"
                "Det fandt overvågningen på siden:\n\n"
                + "\n\n".join(f"• …{h}…" for h in hits[:10])
                + "\n\nSkynd dig! 🤘"
            )
            send_mail("🤘 COPENHELL: Onsdagsbilletter er måske på salg NU!", body)
            state["alerted_key"] = key
            state["alerted_at"] = now.isoformat(timespec="seconds")
        else:
            print("Allerede sendt mail om præcis disse fund – sender ikke igen.")
    else:
        print("Ingen en-dagsbilletter endnu.")
        state.pop("alerted_key", None)

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
