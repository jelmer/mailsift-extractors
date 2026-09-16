#!/usr/bin/env python3
"""KLM e-ticket delivery mails (2016-2019).

Sent from `noreply@ticket.klm.com` with the subject `Ticket for
<name>` (or `Ticket voor <name>` in Dutch), these carry the ticket
itself as a PDF attachment and summarise the itinerary in the body:

    Booking code: AAAAAA
    Alphaville (AAA)
    -
    Springfield (BBB)
    Friday 12 May 2017 at 08:40

Each leg is four lines: origin, a bare `-`, destination, then the
departure date and time. Dutch mail uses `Boekingscode:` and `om`
instead of `at`, but keeps English month and day names.

We emit a FlightReservation per leg plus the attached PDF as a
`.ticket.pdf`, so the ticket itself is preserved rather than dropped.
These mails carry no flight number, so the reservation has none; the
iCal summary falls back to the route.

This is a separate extractor from `klm`: that one handles the modern
`Confirmation: ...` mails from `klm.com`, which have a different
layout and no attachment. Note these are relayed by a third party, so
the DKIM signature is not KLM's and the manifest can't require one.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

BOOKING_RE = re.compile(r"(?:Booking code|Boekingscode):\s*([A-Z0-9]{5,7})")
# `London (LHR)` - the IATA code is what we key the airport on. City
# names are localised (`Londen`), the code is not.
AIRPORT_RE = re.compile(r"^(.+?)\s*\(([A-Z]{3})\)$")
# `Friday 19 August 2016 at 08:40` / `... om 08:40`.
WHEN_RE = re.compile(
    r"^[A-Za-z]+\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+(?:at|om)\s+(\d{1,2}):(\d{2})$",
    re.IGNORECASE,
)

# Dutch mail is inconsistent: some of it keeps English month and day
# names, some localises both. Accept either.
MONTHS = {
    m.lower(): i
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
        ],
        start=1,
    )
}
MONTHS.update(
    {
        m: i
        for i, m in enumerate(
            [
                "januari",
                "februari",
                "maart",
                "april",
                "mei",
                "juni",
                "juli",
                "augustus",
                "september",
                "oktober",
                "november",
                "december",
            ],
            start=1,
        )
    }
)


def parse_legs(lines: list[str]) -> list[dict]:
    """Walk the body for `origin / - / destination / when` runs."""
    legs = []
    for i, line in enumerate(lines):
        if line != "-" or i == 0 or i + 2 >= len(lines):
            continue
        origin = AIRPORT_RE.match(lines[i - 1])
        dest = AIRPORT_RE.match(lines[i + 1])
        when = WHEN_RE.match(lines[i + 2])
        if not (origin and dest and when):
            continue
        day, month_name, year, hour, minute = when.groups()
        month = MONTHS.get(month_name.lower())
        if month is None:
            continue
        try:
            departs = datetime(int(year), month, int(day), int(hour), int(minute))
        except ValueError:
            continue
        legs.append(
            {
                "origin_name": origin.group(1).strip(),
                "origin": origin.group(2),
                "dest_name": dest.group(1).strip(),
                "dest": dest.group(2),
                "departs": departs,
            }
        )
    return legs


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]

    booking_match = BOOKING_RE.search("\n".join(lines))
    if not booking_match:
        return 0
    booking = booking_match.group(1)

    legs = parse_legs(lines)
    if not legs:
        return 0

    for index, leg in enumerate(legs, start=1):
        reservation = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": {
                "@type": "Flight",
                "airline": {"@type": "Airline", "name": "KLM", "iataCode": "KL"},
                "departureAirport": {
                    "@type": "Airport",
                    "name": leg["origin_name"],
                    "iataCode": leg["origin"],
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": leg["dest_name"],
                    "iataCode": leg["dest"],
                },
                "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        # Suffix the slug per leg so the outbound doesn't overwrite the
        # return; a single-leg booking keeps the bare reference.
        suffix = f"-{index}" if len(legs) > 1 else ""
        name = f"klm-{booking.lower()}{suffix}"
        Path(f"{name}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    pdf = mail.find_pdf_attachment()
    if pdf is not None:
        Path(f"klm-{booking.lower()}.ticket.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
