#!/usr/bin/env python3
"""NS International train booking confirmations.

NS International sends booking confirmations from
`no-reply@confirmation.nsinternational.nl`. The HTML has no schema.org
markup and no .ics attachment, but after stripping tags the body has a
stable layout:

    Bookingcode: HHHHHHH
    Total price: EUR 60,60
    Outward
    <Origin> - <Destination>
    Departure: Mon 02 Feb 2026 om 18:27
    Arrival:   Mon 02 Feb 2026 om 21:14
    Class:     Standard Class

(and optionally a `Return` block in the same shape).

We emit one `TrainReservation` per direction. Subject line carries the
canonical booking reference, which we use as the reservationNumber so
follow-up mails (e.g. delay notifications) can update the same UID.
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


SUBJECT_REF_RE = re.compile(r"booking reference:\s*([A-Z0-9]{5,12})", re.I)
ROUTE_RE = re.compile(
    r"(?P<dir>Outward|Return)\s*\n+\s*(?P<origin>[^\n]+?)\s+-\s+(?P<dest>[^\n]+?)\s*\n",
    re.I,
)
DEP_RE = re.compile(
    r"Departure:\s*\n?\s*"
    r"[A-Z][a-z]{2}\s+(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+(?:om|at)\s+(\d{1,2}:\d{2})"
)
ARR_RE = re.compile(
    r"Arrival:\s*\n?\s*"
    r"[A-Z][a-z]{2}\s+(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+(?:om|at)\s+(\d{1,2}:\d{2})"
)
CLASS_RE = re.compile(r"Class:\s*\n?\s*([A-Za-z][A-Za-z ]+?)\s*(?:\n|$)")
# The total is rendered in two fonts in the source HTML, which collapses
# to either "EUR 60,60" or "EUR 6060" after stripping tags. Accept both:
# capture the integer-euro part then the two-digit cents in either form.
TOTAL_RE = re.compile(r"Total price:\s*\n?\s*€\s*(\d+?)(?:[,.](\d{2})|(\d{2}))(?!\d)")


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


def parse_naive_dt(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    ref_match = SUBJECT_REF_RE.search(mail.subject)
    if not ref_match:
        return 0
    booking = ref_match.group(1)

    text = strip_html(mail.html)

    total_price = None
    if (m := TOTAL_RE.search(text)) is not None:
        euros = m.group(1)
        cents = m.group(2) or m.group(3) or "00"
        try:
            total_price = float(f"{euros}.{cents}")
        except ValueError:
            total_price = None

    # Split the text into per-direction blocks. Each ROUTE_RE match
    # marks the start of a new block; the block runs to the next match
    # or end-of-text.
    matches = list(ROUTE_RE.finditer(text))
    if not matches:
        return 0

    for index, match in enumerate(matches):
        direction = match.group("dir").lower()
        origin = match.group("origin").strip()
        destination = match.group("dest").strip()
        block_start = match.end()
        block_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(text)
        )
        block = text[block_start:block_end]

        dep_match = DEP_RE.search(block)
        arr_match = ARR_RE.search(block)
        if not dep_match or not arr_match:
            continue
        dep_dt = parse_naive_dt(dep_match.group(1), dep_match.group(2))
        arr_dt = parse_naive_dt(arr_match.group(1), arr_match.group(2))
        if dep_dt is None or arr_dt is None:
            continue

        train_class = None
        if (m := CLASS_RE.search(block)) is not None:
            train_class = m.group(1).strip()

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": f"{booking}-{direction}",
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {
                    "@type": "Organization",
                    "name": "NS International",
                },
                "departureStation": {
                    "@type": "TrainStation",
                    "name": origin,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": destination,
                },
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if train_class:
            reservation["reservationFor"]["trainName"] = train_class
        # Total price is for the whole booking; attach it to the
        # outward leg only so we don't double-count.
        if total_price is not None and direction == "outward":
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": total_price,
                "priceCurrency": "EUR",
            }
        Path(f"ns-intl-{booking}-{direction}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
