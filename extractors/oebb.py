#!/usr/bin/env python3
"""OEBB (Austrian Federal Railways) booking confirmations.

`tickets@oebb.at` sends a plain-text mail with the subject `OEBB
Booking - <booking-code> - <Mon DD YYYY>` once a ticket is paid.
The body carries:

- `Booking code: <space-separated 16-digit code>`
- `Transaction number: <long numeric>`
- One or more `<from> > <to>` route lines, each followed by
  "One-way journey for <name>", any add-ons (e.g. `1 x bicycle`),
  and `valid: <Mon DD - DD YYYY>` giving the date range the ticket
  is valid for.

OEBB sells station-to-station tickets that cover a validity range
rather than a specific train, so each reservation has a
`reservationFor.departureTime` as midnight of the first valid day
and no arrival time. A VAT receipt PDF is also attached, which we
file as a bill.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

BOOKING_CODE_RE = re.compile(r"Booking code:\s*([0-9]{4}(?:\s+[0-9]{4}){2,4})")
TRANSACTION_RE = re.compile(r"Transaction number:\s*([0-9]+)")
ROUTE_RE = re.compile(r"^(?P<from>[^\n>]+?)\s+>\s+(?P<to>[^\n]+?)$", re.MULTILINE)
VALID_RE = re.compile(
    r"valid:\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<d1>\d{1,2})\s*-\s*"
    r"(?:(?P<mon2>[A-Z][a-z]{2})\s+)?(?P<d2>\d{1,2})\s+(?P<year>\d{4})"
)


def main() -> int:
    mail = read_message()
    if not mail.text:
        return 0
    text = mail.text

    code_match = BOOKING_CODE_RE.search(text)
    if not code_match:
        return 0
    booking_code = re.sub(r"\s+", "", code_match.group(1))
    booking_slug = booking_code

    routes = list(ROUTE_RE.finditer(text))
    valid_dates = list(VALID_RE.finditer(text))
    if not routes or not valid_dates:
        return 0

    # Pair each route with the valid-range that follows it in the text.
    # OEBB emits them in order, so the i-th route goes with the i-th
    # validity range. We cap at min(len(routes), len(valid_dates)) so a
    # mismatch doesn't error out.
    for idx, (route, valid) in enumerate(zip(routes, valid_dates)):
        from_station = route.group("from").strip()
        # Drop the platform ("Gl.5-10") tail that sometimes clings to
        # the destination station.
        to_raw = route.group("to").strip()
        to_station = re.sub(r"\s+Gl\.?\s*[0-9\-]+$", "", to_raw)

        month_name = valid.group("mon")
        day = valid.group("d1")
        year = valid.group("year")
        try:
            dt = datetime.strptime(f"{day} {month_name} {year}", "%d %b %Y")
        except ValueError:
            continue

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": booking_code,
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "ÖBB"},
                "departureStation": {
                    "@type": "TrainStation",
                    "name": from_station,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": to_station,
                },
                "departureDay": dt.strftime("%Y-%m-%d"),
            },
        }
        slug_tail = f"-{idx + 1}" if len(routes) > 1 else ""
        slug = f"oebb-{booking_slug}{slug_tail}"
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False)
        )

    # Attach the VAT/input-tax receipt PDF as a bill.
    pdf = mail.find_pdf_attachment("bescheinigung") or mail.find_pdf_attachment(
        "ticket"
    )
    tx_match = TRANSACTION_RE.search(text)
    if pdf is not None and pdf.bytes:
        bill_slug = f"oebb-{tx_match.group(1) if tx_match else booking_slug}"
        bill: dict = {
            "@context": "https://schema.org",
            "@type": "Invoice",
            "accountId": booking_code,
            "provider": {"@type": "Organization", "name": "ÖBB"},
        }
        if tx_match:
            bill["identifier"] = tx_match.group(1)
        if mail.date:
            bill["billingDate"] = mail.date.strftime("%Y-%m-%d")
        Path(f"{bill_slug}.bill.json").write_text(json.dumps(bill, ensure_ascii=False))
        Path(f"{bill_slug}.bill.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
