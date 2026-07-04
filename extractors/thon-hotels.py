#!/usr/bin/env python3
"""Thon Hotels booking confirmations.

Thon's confirmation mails carry no schema.org markup, only a rendered
HTML page. After stripping tags the body has a stable layout:

    Thon Hotel <name>
    Ref. <digits>
    1 room, N nights, M adult(s)
    <DDD DD. MMM YYYY>      <- check-in date
    Check-in from HH:MM
    <DDD DD. MMM YYYY>      <- check-out date
    Check out before HH:MM
    ...
    EUR <amount>            <- total price (second EUR figure, after a
                               smaller per-night value)
    ...
    Address
    <street, city, CC>

We emit a single `LodgingReservation`. Cancellation, post-stay survey,
and other operational mails don't carry a Ref. and so produce nothing.
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


REF_RE = re.compile(r"Ref\.\s*(\d+)")
HOTEL_RE = re.compile(r"(Thon Hotel[^\n]+?)\s*$", re.M)
CHECKIN_RE = re.compile(
    r"([A-Z][a-z]{2})\s+(\d{1,2})\.\s+([A-Z][a-z]{2})\s+(\d{4})\s*\n\s*Check-in\s+from\s+(\d{1,2}:\d{2})",
)
CHECKOUT_RE = re.compile(
    r"([A-Z][a-z]{2})\s+(\d{1,2})\.\s+([A-Z][a-z]{2})\s+(\d{4})\s*\n\s*Check\s*out\s+before\s+(\d{1,2}:\d{2})",
)
PRICE_RE = re.compile(r"\bEUR\s+([0-9]+(?:[.,][0-9]{2})?)")
ADDRESS_RE = re.compile(r"\bAddress\s*\n\s*([^\n]+)")


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    text = "".join(p.parts)
    # Collapse runs of spaces/tabs but preserve newlines so block-anchored
    # regexes can find their boundaries.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_date(weekday: str, day: str, month: str, year: str) -> datetime | None:
    # Thon writes "30. Jan 2026" - try English (en-GB locale) first.
    try:
        return datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    ref_match = REF_RE.search(text)
    if not ref_match:
        return 0
    ref = ref_match.group(1)

    hotel_match = HOTEL_RE.search(text)
    if not hotel_match:
        return 0
    hotel = hotel_match.group(1).strip()

    ci_match = CHECKIN_RE.search(text)
    co_match = CHECKOUT_RE.search(text)
    if not ci_match or not co_match:
        return 0

    ci_date = parse_date(*ci_match.group(1, 2, 3, 4))
    co_date = parse_date(*co_match.group(1, 2, 3, 4))
    if ci_date is None or co_date is None:
        return 0

    ci_hh, ci_mm = (int(x) for x in ci_match.group(5).split(":"))
    co_hh, co_mm = (int(x) for x in co_match.group(5).split(":"))
    checkin = ci_date.replace(hour=ci_hh, minute=ci_mm)
    checkout = co_date.replace(hour=co_hh, minute=co_mm)

    address = None
    a_match = ADDRESS_RE.search(text)
    if a_match:
        address = a_match.group(1).strip().rstrip(",")

    # Total price is the last EUR figure on the page (per-night EUR
    # appears earlier in the city-tax notice and as a per-night rate).
    total_price = None
    matches = list(PRICE_RE.finditer(text))
    if matches:
        raw = matches[-1].group(1).replace(",", ".")
        try:
            total_price = float(raw)
        except ValueError:
            total_price = None

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"thon-{ref}",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": hotel,
        },
    }
    if address:
        reservation["reservationFor"]["address"] = address
    if total_price is not None:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": total_price,
            "priceCurrency": "EUR",
        }

    Path(f"thon-{ref}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
