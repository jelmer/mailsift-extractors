#!/usr/bin/env python3
"""SEE Tickets event booking confirmations.

Sent from `donotreply@seetickets.com`, either as an "E-Ticket Order
<ref>" (with a PDF ticket attached, filename `<ref>.pdf`) or a
"<Artist> - Ticket Order Confirmation <ref>" (collect-at-venue orders
with no attachment). Both share the same HTML body layout - the
booking reference is called out on its own row and the "Order summary"
section holds the event title, date/time and venue.

We always emit an `EventReservation`. If a PDF is attached, we also
pass it through as a `.ticket.pdf` blob so the mailsift pipeline
files it into `tickets_dir`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

BOOKING_REF_RE = re.compile(r"BOOKING REFERENCE\s+(\d{4,})")
SUBJECT_REF_RE = re.compile(r"(\d{5,})\s*$")
SUBJECT_ARTIST_RE = re.compile(
    r"^(?P<artist>.+?)\s+-\s+Ticket Order Confirmation\s+\d+", re.IGNORECASE
)
SUMMARY_BLOCK_RE = re.compile(
    r"Order summary\s*(.+?)Total\s", re.DOTALL | re.IGNORECASE
)
# The venue name is embedded in the subject: "Booking confirmation for
# <artist> at <venue>". Falls back to the venue line in the body if
# the subject shape is the E-Ticket variant which doesn't name the
# venue up front.
SUBJECT_VENUE_RE = re.compile(
    r"^Booking confirmation for\s+(?P<artist>.+?)\s+at\s+(?P<venue>.+?)\s*$",
    re.IGNORECASE,
)

DATE_LINE_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]+),\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<mon>[A-Z][a-z]{2,})\s+"
    r"(?P<year>\d{4})\s+at\s+"
    r"(?P<hour>\d{1,2})[.:](?P<minute>\d{2})\s*$"
)
DOORS_RE = re.compile(r"Doors open:\s*(\d{1,2})[.:](\d{2})")

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


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(body: str) -> str:
    p = _Strip()
    p.feed(body)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_start(line: str) -> datetime | None:
    m = DATE_LINE_RE.match(line.strip())
    if not m:
        return None
    month = MONTHS.get(m.group("mon"))
    if month is None:
        return None
    try:
        return datetime(
            int(m.group("year")),
            month,
            int(m.group("day")),
            int(m.group("hour")),
            int(m.group("minute")),
        )
    except ValueError:
        return None


def artist_and_venue(subject: str | None) -> tuple[str | None, str | None]:
    if not subject:
        return None, None
    m = SUBJECT_VENUE_RE.match(subject.strip())
    if m:
        return m.group("artist").strip(), m.group("venue").strip()
    m = SUBJECT_ARTIST_RE.match(subject.strip())
    if m:
        return m.group("artist").strip(), None
    return None, None


def find_pdf_attachment(mail, booking_ref: str | None):
    """Return the (filename, bytes) of an attached PDF ticket, or None.

    SEE Tickets names the attachment `<ref>.pdf`, but some
    forwarded/legacy variants send it as `application/octet-stream`
    with no clean MIME type. We accept anything ending in `.pdf` or a
    PDF magic-number payload.
    """
    for attachment in mail.attachments:
        name = (attachment.filename or "").lower()
        looks_pdf = name.endswith(".pdf") or attachment.bytes.startswith(b"%PDF")
        if not looks_pdf:
            continue
        if booking_ref and booking_ref in name:
            return attachment
    # Fall back to the first PDF we find - the reference-name check is
    # a soundness sanity, not a hard requirement.
    for attachment in mail.attachments:
        name = (attachment.filename or "").lower()
        if name.endswith(".pdf") or attachment.bytes.startswith(b"%PDF"):
            return attachment
    return None


def slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]+", "-", value).strip("-")
    return cleaned or fallback


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    booking = None
    if (
        (m := BOOKING_REF_RE.search(text)) is not None
        or mail.subject
        and (m := SUBJECT_REF_RE.search(mail.subject)) is not None
    ):
        booking = m.group(1)
    if not booking:
        return 0

    artist_subject, venue_subject = artist_and_venue(mail.subject)

    summary_block = None
    if (m := SUMMARY_BLOCK_RE.search(text)) is not None:
        summary_block = m.group(1)

    summary_lines = (
        [ln.strip() for ln in summary_block.split("\n") if ln.strip()]
        if summary_block
        else []
    )

    start_dt = None
    for line in summary_lines:
        start_dt = parse_start(line)
        if start_dt is not None:
            break
    if start_dt is None:
        return 0

    # Body venue: the line following the date within the summary block.
    body_venue = None
    for index, line in enumerate(summary_lines):
        if parse_start(line) is not None:
            for candidate in summary_lines[index + 1 :]:
                # Skip any "Doors open:" annotation between date and venue.
                if candidate.lower().startswith("doors open"):
                    continue
                body_venue = candidate
                break
            break

    venue = venue_subject or body_venue or "Venue"

    # Event name from body's "Order summary" first line, else subject.
    event_name = summary_lines[0] if summary_lines else artist_subject
    if not event_name:
        event_name = artist_subject or venue

    doors_dt = None
    if (m := DOORS_RE.search(text)) is not None:
        doors_dt = start_dt.replace(hour=int(m.group(1)), minute=int(m.group(2)))

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": f"see-tickets-{booking}",
        "reservationFor": {
            "@type": "Event",
            "name": event_name,
            "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "location": {
                "@type": "Place",
                "name": venue,
            },
        },
        "provider": {"@type": "Organization", "name": "See Tickets"},
    }
    if doors_dt is not None:
        reservation["reservationFor"]["doorTime"] = doors_dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    slug = slugify(booking, fallback="see-tickets")
    Path(f"see-tickets-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )

    pdf = find_pdf_attachment(mail, booking)
    if pdf is not None:
        Path(f"see-tickets-{slug}.ticket.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
