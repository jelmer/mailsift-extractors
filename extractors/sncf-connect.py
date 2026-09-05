#!/usr/bin/env python3
"""SNCF Connect trip confirmations.

SNCF Connect sends a `Your trip <Origin> - <Destination>, outbound
on <Weekday, D Month YYYY>` mail after every purchase. The English
plain-text body carries the booking reference (PNR) and the order
total, which we emit as a `.receipt.json` per trip.

The HTML body carries the per-leg departure timestamp and train
number too, laid out consistently enough that we can also emit a
`TrainReservation` per direction. Absent the HTML body we still
emit the receipt on its own so the trip is at least represented.

Subject on French-locale accounts (`Votre voyage ...`) isn't matched
by the manifest; adding French would need parallel parsing of the
"Total commande" / "Numero de reservation" body labels and there
are none of those in the corpus we've seen. Add when a real
French-locale mail turns up.
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

# `Reference number  TB425X / HP5290517200` - the first token is the
# PNR the user sees; the second is SNCF's internal order id. Two
# spaces after the label is intentional; SNCF's template pads it.
PNR_RE = re.compile(r"Reference number\s+(?P<pnr>[A-Z0-9]{6})\s*/\s*[A-Z0-9]{8,}")
# `Order total : €204.00` - space around the colon matches the wire
# template exactly.
TOTAL_RE = re.compile(
    r"Order total\s*:\s*(?P<symbol>[€£$])\s*(?P<amount>\d+(?:\.\d{2})?)"
)
# `Your trip <O> - <D>, outbound on <weekday>, <D Month YYYY>`
SUBJECT_TRIP_RE = re.compile(
    r"^Your trip\s+(?P<origin>.+?)\s+-\s+(?P<destination>.+?),\s*outbound on",
    re.IGNORECASE,
)

# HTML-body markers.
# `Outbound: Sunday, 16 August 2026 at 06:58` — one per direction;
# a return itinerary adds a matching `Inbound: ...` line.
DIRECTION_RE = re.compile(
    r"(?P<direction>Outbound|Inbound)\s*:\s*"
    r"[A-Z][a-z]+,\s+(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]+)\s+(?P<year>\d{4})"
    r"\s+at\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})",
    re.IGNORECASE,
)
# The leg header lives under an all-caps section title, e.g.
# `OUTBOUND TGV INOUI 8534 | TARIF FLEX PREMIERE`. The provider is
# free-form ("TGV INOUI", "OUIGO", "INTERCITES"); the number sits
# right before the pipe and is what we want on the reservation.
LEG_HEADER_RE = re.compile(
    r"(?P<direction>OUTBOUND|INBOUND)\s+"
    r"(?P<provider>[A-Z][A-Z ]+?)\s+"
    r"(?P<number>\d{2,5})\s*(?:\||$)",
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
}


def parse_direction_dt(m: re.Match[str]) -> datetime | None:
    month = _MONTHS.get(m.group("month"))
    if month is None:
        return None
    try:
        return datetime(
            int(m.group("year")),
            month,
            int(m.group("day")),
            int(m.group("hh")),
            int(m.group("mm")),
        )
    except ValueError:
        return None


def leg_headers(html_text: str) -> dict[str, str]:
    """Map direction ("outbound"/"inbound") -> train number."""
    out: dict[str, str] = {}
    for m in LEG_HEADER_RE.finditer(html_text):
        out[m.group("direction").lower()] = m.group("number")
    return out


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    text = mail.text or ""
    if not text:
        return 0

    pnr_match = PNR_RE.search(text)
    total_match = TOTAL_RE.search(text)
    subject_match = SUBJECT_TRIP_RE.match(subject)
    if not (pnr_match and total_match and subject_match):
        return 0

    pnr = pnr_match.group("pnr")
    origin = subject_match.group("origin").strip()
    destination = subject_match.group("destination").strip()

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "SNCF Connect",
        "orderNumber": pnr,
        "description": f"{origin} - {destination}",
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total_match.group("amount")),
            "priceCurrency": SYMBOL_TO_CURRENCY.get(total_match.group("symbol"), "EUR"),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    Path(f"sncf-connect-{pnr}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )

    if mail.html:
        html_text = strip_html(mail.html)
        numbers = leg_headers(html_text)
        for m in DIRECTION_RE.finditer(html_text):
            direction = m.group("direction").lower()
            dep = parse_direction_dt(m)
            if dep is None:
                continue
            # Origin/destination come from the subject; on an
            # inbound leg they swap.
            if direction == "inbound":
                dep_station, arr_station = destination, origin
            else:
                dep_station, arr_station = origin, destination
            trip: dict = {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "SNCF"},
                "departureStation": {
                    "@type": "TrainStation",
                    "name": dep_station,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": arr_station,
                },
                "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if direction in numbers:
                trip["trainNumber"] = numbers[direction]
            reservation = {
                "@context": "https://schema.org",
                "@type": "TrainReservation",
                "reservationNumber": f"sncf-connect-{pnr}-{direction}",
                "reservationFor": trip,
            }
            Path(f"sncf-connect-{pnr}-{direction}.reservation.json").write_text(
                json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
