#!/usr/bin/env python3
"""Expedia.co.uk hotel confirmations from 2011.

Once the tags are stripped, each hotel reads:

    Hotel summary
    Sun 22-May-2039 (1 night)
    Example Luton Hotel
    1 Example Road
    Luton, Bedfordshire LU2 9AA
    United Kingdom
    Check in: Sun 22-May-2039
    Check out: Mon 23-May-2039
    ...
    Tel: 44 (01) 582000001

The itinerary number follows "Expedia.co.uk itinerary number:" and
the guest "Reserved for:".
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

ITINERARY_RE = re.compile(r"^Expedia\.co\.uk itinerary number: (\d+)$")
CHECK_RE = re.compile(r"^Check (in|out): \w{3} (\d{1,2}-\w{3}-\d{4})$")
TOWN_RE = re.compile(r"^(.+?), (.+?) ([A-Z0-9]{2,4} [A-Z0-9]{3})$")


def day(value: str) -> str:
    return datetime.strptime(value, "%d-%b-%Y").strftime("%Y-%m-%d")


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    itinerary = next(
        (m.group(1) for line in lines if (m := ITINERARY_RE.match(line))), None
    )
    if itinerary is None:
        return 0
    guest = None
    if "Reserved for:" in lines:
        guest = lines[lines.index("Reserved for:") + 1]

    summaries = [i for i, line in enumerate(lines) if line == "Hotel summary"]
    if not summaries:
        raise ValueError(f"itinerary {itinerary} has no hotel summary")
    for index, start in enumerate(summaries):
        checks: dict[str, str] = {}
        end = next(
            (i for i in range(start + 1, len(lines)) if CHECK_RE.match(lines[i])), None
        )
        if end is None:
            raise ValueError(f"itinerary {itinerary}: no check-in date")
        for line in lines[end : end + 2]:
            m = CHECK_RE.match(line)
            if m:
                checks[m.group(1)] = day(m.group(2))
        if set(checks) != {"in", "out"}:
            raise ValueError(f"itinerary {itinerary}: missing check-in or check-out")

        name, *street, town, country = lines[start + 2 : end]
        address: dict = {
            "@type": "PostalAddress",
            "streetAddress": ", ".join(street),
            "addressCountry": country,
        }
        m = TOWN_RE.match(town)
        if m:
            address["addressLocality"] = m.group(1)
            address["addressRegion"] = m.group(2)
            address["postalCode"] = m.group(3)
        else:
            address["addressLocality"] = town
        hotel: dict = {"@type": "Hotel", "name": name, "address": address}
        phone = next(
            (line[5:] for line in lines[end:] if line.startswith("Tel: ")), None
        )
        if phone:
            hotel["telephone"] = phone

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": f"expedia-{itinerary}",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "Expedia"},
            "checkinTime": checks["in"],
            "checkoutTime": checks["out"],
            "reservationFor": hotel,
        }
        if guest:
            reservation["underName"] = {"@type": "Person", "name": guest}
        suffix = f"-{index + 1}" if len(summaries) > 1 else ""
        Path(f"expedia-hotel-{itinerary}{suffix}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
