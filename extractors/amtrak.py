#!/usr/bin/env python3
"""Amtrak eTicket + sales receipt mails.

`etickets@amtrak.com` sends one HTML mail per purchase that doubles as
receipt and ticket, with the paper ticket as a PDF attachment. The HTML
carries the reservation number, each train's number + route, departure
date/time, class of service and fare. We emit a `TrainReservation` per
train segment (so a round-trip becomes two artifacts) and a receipt for
the overall purchase; the attached PDF is filed as a ticket.

The departure time is explicit in the body; Amtrak does not list an
arrival time in the confirmation, so we leave `arrivalTime` off.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

RESERVATION_RE = re.compile(r"Reservation Number\s*-\s*([A-Z0-9]{6})")
TICKET_NUMBER_RE = re.compile(r"Ticket Number\s*([0-9]{10,16})")
TOTAL_RE = re.compile(r"Total\s*\$?\s*([0-9]+(?:\.[0-9]{2})?)")
TRAIN_RE = re.compile(
    r"TRAIN\s+(?P<num>\d+):\s*(?P<from>[^-]+?)\s*-\s*(?P<to>[^\n]+?)\s*"
    r"Depart\s+(?P<time>\d{1,2}:\d{2}\s*[AP]M),\s*"
    r"(?P<weekday>[A-Za-z]+),\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})",
    re.IGNORECASE,
)


def parse_station(phrase: str) -> tuple[str, str | None]:
    """Split "BOSTON (SOUTH STATION), MA" into (name, state)."""
    m = re.match(r"^\s*(.+?)\s*,\s*([A-Z]{2})\s*$", phrase)
    if m:
        return m.group(1).strip(), m.group(2)
    return phrase.strip(), None


def parse_depart(time_str: str, month: str, day: str, year: str) -> datetime | None:
    try:
        return datetime.strptime(
            f"{day} {month} {year} {time_str}".replace("  ", " "),
            "%d %B %Y %I:%M %p",
        )
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)
    text = re.sub(r"[ \t]+", " ", text)

    res_match = RESERVATION_RE.search(text)
    if not res_match:
        return 0
    reservation_number = res_match.group(1)

    ticket_match = TICKET_NUMBER_RE.search(text)
    ticket_number = ticket_match.group(1) if ticket_match else None

    segments = list(TRAIN_RE.finditer(text))
    if not segments:
        return 0

    for seg in segments:
        dep_dt = parse_depart(
            seg.group("time"), seg.group("month"), seg.group("day"), seg.group("year")
        )
        if dep_dt is None:
            continue
        dep_name, dep_state = parse_station(seg.group("from"))
        arr_name, arr_state = parse_station(seg.group("to"))
        dep_station: dict = {"@type": "TrainStation", "name": dep_name}
        if dep_state:
            dep_station["address"] = dep_state
        arr_station: dict = {"@type": "TrainStation", "name": arr_name}
        if arr_state:
            arr_station["address"] = arr_state

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": reservation_number,
            "reservationFor": {
                "@type": "TrainTrip",
                "trainNumber": seg.group("num"),
                "provider": {"@type": "Organization", "name": "Amtrak"},
                "departureStation": dep_station,
                "arrivalStation": arr_station,
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        slug = f"amtrak-{reservation_number}-{seg.group('num')}"
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False)
        )

    # Receipt covering the whole purchase
    total_match = TOTAL_RE.search(text)
    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Amtrak",
        "orderNumber": ticket_number or reservation_number,
    }
    if total_match:
        receipt["price"] = total_match.group(1)
        receipt["priceCurrency"] = "USD"
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    slug = f"amtrak-{ticket_number or reservation_number}"
    Path(f"{slug}.receipt.json").write_text(json.dumps(receipt, ensure_ascii=False))

    # File the PDF eTicket if present.
    pdf = mail.find_pdf_attachment("ticket") or mail.find_pdf_attachment("")
    if pdf is not None and pdf.bytes:
        ticket_path = Path(f"amtrak-{reservation_number}.ticket.pdf")
        ticket_path.write_bytes(pdf.bytes)
        meta = {
            "@context": "https://schema.org",
            "@type": "Ticket",
            "ticketNumber": ticket_number or reservation_number,
            "issuedBy": {"@type": "Organization", "name": "Amtrak"},
        }
        Path(f"amtrak-{reservation_number}.ticket.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
