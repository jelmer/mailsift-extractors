#!/usr/bin/env python3
"""Restaurant booking confirmations from restaurant-information.com.

restaurant-information.com is TheFork's transactional infrastructure;
many TheFork restaurants send confirmations from this domain. The HTML
has a stable, table-driven layout where the venue name appears as a
single line followed by an address line, and the booking details
(Date/Hour/People) appear as label/value pairs.

The booking year is not printed in the body - only "Thursday, 19 Mar".
We fold it back in using the message's Date header: the booking is in
the future (or this calendar year) relative to send time, so we use the
mail's year and bump to next year if the resulting date is before the
mail was sent.

The cancellation URL in the body carries the reservation UUID; we use
that as the canonical reservation id.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


SUBJECT_VENUE_RE = re.compile(r"Confirmation of your booking at\s+(.+?)\s*$", re.I)
RES_ID_RE = re.compile(
    r"restaurant-information\.com/[^/\s]+/reservation/cancel/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
DATE_RE = re.compile(
    r"\bDate\s*\n\s*([A-Z][a-z]+,\s+\d{1,2}\s+[A-Z][a-z]+)",
)
HOUR_RE = re.compile(r"\bHour\s*\n\s*(\d{1,2}:\d{2})")
PEOPLE_RE = re.compile(r"\bPeople\s*\n\s*(\d+)\s+(?:people|person)")
SEATING_RE = re.compile(
    r"reserved\s+from\s+\d{1,2}:\d{2}\s+to\s+(\d{1,2}:\d{2})",
    re.I,
)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "p", "div", "tr", "td", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("p", "div", "tr", "td", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def resolve_year(date_str: str, mail_date: datetime | None) -> datetime | None:
    """Attach a year to a "Weekday, DD Mon" string using the mail's send date.

    Future bookings only - if the year-completed date falls before the
    mail's send date, bump to the next year.
    """
    if mail_date is None:
        return None
    base = mail_date.year
    cleaned = date_str.replace(",", "").strip()
    for year in (base, base + 1):
        try:
            d = datetime.strptime(f"{cleaned} {year}", "%A %d %b %Y")
        except ValueError:
            continue
        # Booking must be on or after send date.
        if d.date() >= mail_date.date():
            return d
    return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    venue = None
    if mail.subject:
        m = SUBJECT_VENUE_RE.search(mail.subject)
        if m:
            venue = m.group(1).strip()
    if not venue:
        return 0

    text = strip_html(mail.html)

    res_id_match = RES_ID_RE.search(text) or RES_ID_RE.search(mail.html)
    if not res_id_match:
        return 0
    res_id = res_id_match.group(1)

    date_match = DATE_RE.search(text)
    hour_match = HOUR_RE.search(text)
    if not date_match or not hour_match:
        return 0

    start_date = resolve_year(date_match.group(1), mail.date)
    if start_date is None:
        return 0
    hh, mm = (int(x) for x in hour_match.group(1).split(":"))
    start = start_date.replace(hour=hh, minute=mm)

    end = None
    seating_match = SEATING_RE.search(text)
    if seating_match:
        eh, em = (int(x) for x in seating_match.group(1).split(":"))
        end = start_date.replace(hour=eh, minute=em)

    party_size = None
    if (m := PEOPLE_RE.search(text)) is not None:
        party_size = int(m.group(1))

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "reservationNumber": f"restaurant-information-{res_id}",
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": venue,
        },
    }
    if end is not None:
        reservation["endTime"] = end.strftime("%Y-%m-%dT%H:%M:%S")
    if party_size is not None:
        reservation["partySize"] = party_size

    Path(f"restaurant-information-{res_id}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
