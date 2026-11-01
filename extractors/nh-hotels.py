#!/usr/bin/env python3
"""NH Hotels reservation confirmations.

The subject names the hotel and the reservation number: "Your
reservation for NH Example Antwerp, February 3, 2040, AAAA000000001".
Once the tags are stripped, the body has the hotel's address on the
line before its phone number, and the stay on one line:

    1 Example Street. 2000 Antwerp (Belgium)
    Telephone. +32.30.000001 - Fax. +32.30.000002
    ...
    Arrival:
    03/02/2040 - Departure: 05/02/2040 - nights:

The guest follows "Main Guest (name used in the reservation)" in 2011
and "Reservation holder" from 2012 on.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_RE = re.compile(r"^Your reservation for (.+), \w+ \d{1,2}, \d{4}, ([A-Z0-9]+)$")
STAY_RE = re.compile(r"^(\d{2}/\d{2}/\d{4}) - Departure: (\d{2}/\d{2}/\d{4})\b")
PHONE_RE = re.compile(r"^Telephone\. (.+?)(?: - Fax\. .*)?$")
ADDRESS_RE = re.compile(r"^(.+) \(([^)]+)\)$")
GUEST_LABELS = ("Main Guest (name used in the reservation)", "Reservation holder")


def day(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    subject = SUBJECT_RE.match((mail.subject or "").strip())
    if not subject:
        return 0
    hotel_name, number = subject.groups()
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    stay = next((m for line in lines if (m := STAY_RE.match(line))), None)
    if stay is None:
        raise ValueError(f"reservation {number}: no arrival and departure")

    hotel: dict = {"@type": "Hotel", "name": hotel_name}
    for i, line in enumerate(lines):
        phone = PHONE_RE.match(line)
        if phone is None:
            continue
        hotel["telephone"] = phone.group(1)
        address = ADDRESS_RE.match(lines[i - 1])
        if address:
            hotel["address"] = {
                "@type": "PostalAddress",
                "streetAddress": address.group(1),
                "addressCountry": address.group(2),
            }
        break

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": number,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "checkinTime": day(stay.group(1)),
        "checkoutTime": day(stay.group(2)),
        "reservationFor": hotel,
    }
    guest = next(
        (lines[i + 1] for i, line in enumerate(lines) if line in GUEST_LABELS), None
    )
    if guest:
        reservation["underName"] = {"@type": "Person", "name": guest}

    Path(f"nh-hotels-{number}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
