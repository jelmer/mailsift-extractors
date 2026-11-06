#!/usr/bin/env python3
"""Hotels.com travel confirmations.

`confirmation@mail.hotels.com` sends an HTML-only mail with subject
`Hotels.com travel confirmation - <Check-in date> - (Itinerary # <N>)`
once a reservation is paid. The visible body is sparse but carries:

- `Itinerary # <14-digit number>` - the reservation number.
- `<Hotel name>, <City>` on a line of its own, directly before
  the stay dates.
- `<DD MMM YYYY> - <DD MMM YYYY>` for check-in / check-out.

That is enough for a `LodgingReservation`. Hotels.com doesn't put a
JSON-LD block in these mails (unlike the airlines), so we parse the
text of the rendered body directly.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

ITINERARY_RE = re.compile(r"Itinerary\s*#?\s*(\d{10,16})", re.IGNORECASE)
DATE_RANGE_RE = re.compile(
    r"(?P<in>\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s*-\s*"
    r"(?P<out>\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})"
)


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)
    text = re.sub(r"[ \t]+", " ", text)

    itin_match = ITINERARY_RE.search(text)
    if not itin_match:
        return 0
    itinerary = itin_match.group(1)

    date_match = DATE_RANGE_RE.search(text)
    if not date_match:
        return 0

    def parse_date(s: str) -> datetime | None:
        try:
            return datetime.strptime(s.strip(), "%d %b %Y")
        except ValueError:
            return None

    check_in = parse_date(date_match.group("in"))
    check_out = parse_date(date_match.group("out"))
    if check_in is None or check_out is None:
        return 0

    # Hotel name appears on the line immediately before the date range.
    # We take the nearest preceding non-empty, non-UI-boilerplate line.
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    hotel_line = None
    for i, line in enumerate(lines):
        if DATE_RANGE_RE.search(line):
            # Walk backwards to find a hotel-shaped line
            for prev in reversed(lines[:i]):
                if re.fullmatch(r"[\s!-~]+", prev) and "," in prev and len(prev) < 120:
                    hotel_line = prev
                    break
            break

    hotel_name = None
    hotel_city = None
    if hotel_line and "," in hotel_line:
        name, _, city = hotel_line.rpartition(",")
        hotel_name = name.strip()
        hotel_city = city.strip()

    lodging: dict = {
        "@type": "LodgingBusiness",
    }
    if hotel_name:
        lodging["name"] = hotel_name
    if hotel_city:
        lodging["address"] = {"@type": "PostalAddress", "addressLocality": hotel_city}

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": itinerary,
        "checkinTime": check_in.strftime("%Y-%m-%d"),
        "checkoutTime": check_out.strftime("%Y-%m-%d"),
        "reservationFor": lodging,
        "bookingAgent": {"@type": "Organization", "name": "Hotels.com"},
    }
    slug = f"hotels-com-{itinerary}"
    Path(f"{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
