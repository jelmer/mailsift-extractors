#!/usr/bin/env python3
"""Eventbrite order confirmations and cancellations.

Sent from `noreply@order.eventbrite.com`. Two subject shapes we care
about:

    Order Confirmation for <event title>
    Order CANCELED for <event title>

The plain-text body carries the event name, datetime, venue and
order number in a predictable layout, and a Google Maps "q=" URL
(after eventbrite's click-tracker wrapper) with the full address.
We emit an `EventReservation` in both cases; the cancel variant sets
`reservationStatus` so the Rust side can pass a `METHOD:CANCEL` on
to the calendar.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_CONFIRM_RE = re.compile(
    r"^Order Confirmation for\s+(?P<event>.+?)\s*$", re.IGNORECASE
)
SUBJECT_CANCEL_RE = re.compile(
    r"^Order CANCELED for\s+(?P<event>.+?)\s*$", re.IGNORECASE
)

ORDER_ID_BODY_RE = re.compile(r"Order\s*#?\s*(\d{6,})", re.IGNORECASE)

# Order confirmation date-time line:
#   "Thursday, June 29, 2023 from 7:00 PM to 9:00 PM (United Kingdom Time)"
CONFIRM_DT_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]+),\s+"
    r"(?P<mon>[A-Z][a-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\s+"
    r"from\s+(?P<start>\d{1,2}:\d{2}\s*[AP]M)\s+"
    r"to\s+(?P<end>\d{1,2}:\d{2}\s*[AP]M)"
    r"(?:\s*\((?P<tz>[^)]+)\))?",
    re.MULTILINE,
)

# Cancellation date-time line:
#   "Thu, Jun 29, 2023 7:00 PM - 9:00 PM (BST)"
CANCEL_DT_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]{2,3}),\s+"
    r"(?P<mon>[A-Z][a-z]{2,})\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\s+"
    r"(?P<start>\d{1,2}:\d{2}\s*[AP]M)\s*-\s*"
    r"(?P<end>\d{1,2}:\d{2}\s*[AP]M)"
    r"(?:\s*\((?P<tz>[^)]+)\))?",
    re.MULTILINE,
)

# Eventbrite wraps every URL in a click-tracker whose fragment carries
# the real URL as a base64-encoded slice - we recognise the encoded
# `http(s)://` prefix (`aHR0c...`) and hunt back through candidate
# lengths until we recover a valid URL.
CLICK_URL_RE = re.compile(
    r"clicks\.eventbrite\.com/f/a/[^/]+/[^/]+/(RgR[A-Za-z0-9_-]+)"
)
ENCODED_URL_RE = re.compile(r"aHR0cHM?[A-Za-z0-9_-]+")

MONTHS = {
    "Jan": 1,
    "January": 1,
    "Feb": 2,
    "February": 2,
    "Mar": 3,
    "March": 3,
    "Apr": 4,
    "April": 4,
    "May": 5,
    "Jun": 6,
    "June": 6,
    "Jul": 7,
    "July": 7,
    "Aug": 8,
    "August": 8,
    "Sep": 9,
    "Sept": 9,
    "September": 9,
    "Oct": 10,
    "October": 10,
    "Nov": 11,
    "November": 11,
    "Dec": 12,
    "December": 12,
}


def parse_time(value: str) -> tuple[int, int]:
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)$", value.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(value)
    hour = int(m.group(1))
    minute = int(m.group(2))
    if m.group(3).upper() == "PM" and hour < 12:
        hour += 12
    elif m.group(3).upper() == "AM" and hour == 12:
        hour = 0
    return hour, minute


def parse_datetime(match: re.Match[str]) -> tuple[datetime, datetime] | None:
    month = MONTHS.get(match.group("mon"))
    if month is None:
        return None
    try:
        day = int(match.group("day"))
        year = int(match.group("year"))
        start_h, start_m = parse_time(match.group("start"))
        end_h, end_m = parse_time(match.group("end"))
        start = datetime(year, month, day, start_h, start_m)
        end = datetime(year, month, day, end_h, end_m)
    except ValueError:
        return None
    return start, end


def decode_click_target(fragment: str) -> str | None:
    """Peel eventbrite's click-tracker to get the real URL.

    The fragment carries the URL as a base64-encoded substring; the
    encoded form always starts with `aHR0c` (b64 of "http"). We try
    decreasing prefix lengths until we get a well-formed URL back.
    """
    match = ENCODED_URL_RE.search(fragment)
    if not match:
        return None
    encoded = match.group()
    for length in range(len(encoded), 8, -1):
        candidate = encoded[:length]
        pad = (-len(candidate)) % 4
        try:
            decoded = base64.urlsafe_b64decode(candidate + "=" * pad)
        except ValueError:
            continue
        try:
            text = decoded.decode("utf-8")
        except UnicodeDecodeError:
            # Trailing metadata bytes bleed past the URL; strip them.
            for terminator in (b"\x03", b"\x00"):
                idx = decoded.find(terminator)
                if idx > 0:
                    try:
                        text = decoded[:idx].decode("utf-8")
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                continue
        text = text.split("\x03", 1)[0].split("\x00", 1)[0]
        if not text.startswith(("http://", "https://")):
            continue
        # Trailing base64-boundary chars sometimes leave a stray letter
        # after the URL when the terminator byte lands mid-quartet.
        # Trim any trailing single alpha that would otherwise corrupt a
        # `q=` parameter's last token.
        parsed = urllib.parse.urlparse(text)
        if parsed.query:
            trimmed_query = re.sub(r"[A-Z]$", "", parsed.query)
            if trimmed_query != parsed.query:
                text = urllib.parse.urlunparse(parsed._replace(query=trimmed_query))
        return text
    return None


def extract_map_address(text: str) -> str | None:
    """Return the `q=<address>` from an eventbrite-wrapped maps URL, if any.

    Eventbrite links to Google Maps with the venue's full postal
    address in the `q=` parameter. That's the most reliable venue
    address the mail carries.
    """
    for match in CLICK_URL_RE.finditer(text):
        decoded = decode_click_target(match.group(1))
        if not decoded or "maps.google" not in decoded:
            continue
        parsed = urllib.parse.urlparse(decoded)
        query = urllib.parse.parse_qs(parsed.query)
        if "q" in query:
            return query["q"][0].strip()
    return None


def event_name(mail_subject: str | None, body: str) -> tuple[str | None, str]:
    """Return (event_name, kind) where kind is 'confirm' or 'cancel'."""
    if not mail_subject:
        return None, "confirm"
    m = SUBJECT_CONFIRM_RE.match(mail_subject.strip())
    if m:
        return m.group("event").strip(), "confirm"
    m = SUBJECT_CANCEL_RE.match(mail_subject.strip())
    if m:
        return m.group("event").strip(), "cancel"
    return None, "confirm"


def find_venue_line(text: str, start_line: str) -> str | None:
    """Return the venue name line that immediately precedes an
    eventbrite-wrapped Google Maps URL.

    The confirmation body puts the venue on its own line, followed by
    a click-tracker URL that decodes to a google maps `q=` link.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if start_line in line:
            for prior in range(index - 1, max(-1, index - 8), -1):
                candidate = lines[prior].strip()
                if candidate:
                    return candidate
    return None


def slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]+", "-", value).strip("-")
    return cleaned or fallback


def main() -> int:
    mail = read_message()
    if not mail.text:
        return 0

    name, kind = event_name(mail.subject, mail.text)
    if not name:
        return 0

    order_id = None
    if (m := ORDER_ID_BODY_RE.search(mail.text)) is not None:
        order_id = m.group(1)
    if not order_id:
        return 0

    dates = None
    if kind == "cancel":
        m = CANCEL_DT_RE.search(mail.text)
        if m is not None:
            dates = parse_datetime(m)
    else:
        m = CONFIRM_DT_RE.search(mail.text)
        if m is not None:
            dates = parse_datetime(m)
    if dates is None:
        return 0
    start, end = dates

    address = extract_map_address(mail.text)
    venue_line = None
    if address:
        # First maps URL sits right after the venue-name line.
        for click_match in CLICK_URL_RE.finditer(mail.text):
            decoded = decode_click_target(click_match.group(1))
            if decoded and "maps.google" in decoded:
                marker = click_match.group(0)
                venue_line = find_venue_line(mail.text, marker)
                break

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": f"eventbrite-{order_id}",
        "reservationStatus": (
            "https://schema.org/ReservationCancelled"
            if kind == "cancel"
            else "https://schema.org/ReservationConfirmed"
        ),
        "reservationFor": {
            "@type": "Event",
            "name": name,
            "startDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "provider": {"@type": "Organization", "name": "Eventbrite"},
    }
    if venue_line or address:
        location: dict = {"@type": "Place"}
        if venue_line:
            location["name"] = venue_line
        if address:
            location["address"] = address
        reservation["reservationFor"]["location"] = location

    slug = slugify(order_id, fallback="eventbrite")
    Path(f"eventbrite-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
