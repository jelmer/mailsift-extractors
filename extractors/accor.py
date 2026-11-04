#!/usr/bin/env python3
"""Accor (ibis, Novotel, Mercure, ...) reservation confirmations.

Accor's ALL confirmations arrive as plain text with a label/value
layout:

    Reservation number: <code>
    ...
    From <DD Mon YYYY> to <DD Mon YYYY>
    ...
    , <n> adult
    ...
    Check in Policy
    The room is available from <HH:MM>.
    Check out Policy
    The room must be vacated by <HH:MM> at the latest.

The hotel name is in the subject rather than the body, where it is
repeated inside marketing copy and is hard to pin down. The check-in
and check-out clock times come from the policy paragraphs, which are
the only place they appear.

"Cancellation of your reservation: <hotel> No. <code>" mails list the
same number and stay dates, so they emit the same reservation with
`reservationStatus: ReservationCancelled`, which replaces the booked
one. They carry no policy paragraphs, so the times are dates only.
Older templates write the stay as `From Jul. 20, 2022 to Jul. 21, 2022`.
Modification mails are kept out by the manifest.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_RE = re.compile(
    r"(?P<kind>Confirmation|Cancellation) of your reservation:"
    r"\s*(?P<hotel>.+?)\s*No\.\s*(?P<ref>[A-Z0-9]+)\s*$",
    re.IGNORECASE,
)
STAY_RE = re.compile(
    r"From\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+to\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
)
MONTH_FIRST_STAY_RE = re.compile(
    r"From\s+([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})\s+to\s+([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})",
)
ADULTS_RE = re.compile(r",\s*(\d+)\s+adults?\b", re.IGNORECASE)
CHECKIN_TIME_RE = re.compile(r"room is available from\s*(\d{1,2}[:.]\d{2})")
CHECKOUT_TIME_RE = re.compile(r"room must be vacated by\s*(\d{1,2}[:.]\d{2})")
TOTAL_RE = re.compile(r"Total\s*\n\s*([A-Z]{3})\s+([0-9]+(?:\.[0-9]{2})?)")


def parse_date(day: str, month: str, year: str) -> datetime | None:
    for fmt in ("%b", "%B"):
        try:
            return datetime.strptime(f"{day} {month} {year}", f"%d {fmt} %Y")
        except ValueError:
            continue
    return None


def cancelled_stay(text: str, hotel: str, reference: str) -> dict:
    stay = STAY_RE.search(text)
    if stay:
        checkin = parse_date(*stay.group(1, 2, 3))
        checkout = parse_date(*stay.group(4, 5, 6))
    else:
        stay = MONTH_FIRST_STAY_RE.search(text)
        if not stay:
            raise ValueError(f"cancellation of {reference} has no stay dates")
        checkin = parse_date(*stay.group(2, 1, 3))
        checkout = parse_date(*stay.group(5, 4, 6))
    if checkin is None or checkout is None:
        raise ValueError(f"cancellation of {reference}: bad dates {stay.group(0)!r}")
    return {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationStatus": "ReservationCancelled",
        "reservationNumber": f"accor-{reference}",
        "checkinTime": checkin.strftime("%Y-%m-%d"),
        "checkoutTime": checkout.strftime("%Y-%m-%d"),
        "reservationFor": {"@type": "LodgingBusiness", "name": hotel},
    }


def apply_clock(stamp: datetime, text: str, pattern: re.Pattern[str]) -> datetime:
    match = pattern.search(text)
    if not match:
        return stamp
    hour, minute = (int(x) for x in re.split(r"[:.]", match.group(1)))
    return stamp.replace(hour=hour, minute=minute)


def main() -> int:
    mail = read_message()

    subject_match = SUBJECT_RE.search(mail.subject or "")
    if not subject_match:
        return 0
    hotel = subject_match.group("hotel").strip()
    reference = subject_match.group("ref")

    # Some mails carry an empty text/plain part next to the HTML.
    text = (mail.text or "").strip()
    if not text and mail.html:
        text = strip_html(mail.html, block_tags=True)
    if not text:
        return 0

    if subject_match.group("kind").lower() == "cancellation":
        cancelled = cancelled_stay(text, hotel, reference)
        Path(f"accor-{reference}.reservation.json").write_text(
            json.dumps(cancelled, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    stay = STAY_RE.search(text)
    if not stay:
        return 0
    checkin = parse_date(*stay.group(1, 2, 3))
    checkout = parse_date(*stay.group(4, 5, 6))
    if checkin is None or checkout is None:
        return 0

    checkin = apply_clock(checkin, text, CHECKIN_TIME_RE)
    checkout = apply_clock(checkout, text, CHECKOUT_TIME_RE)

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"accor-{reference}",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": hotel,
        },
    }

    adults = ADULTS_RE.search(text)
    if adults:
        reservation["@context"] = {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        }
        reservation["pending:numAdults"] = int(adults.group(1))

    # The page repeats the nightly rate before the booking total; the
    # `Total` heading is what covers the whole stay.
    total = TOTAL_RE.search(text)
    if total:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": float(total.group(2)),
            "priceCurrency": total.group(1),
        }

    Path(f"accor-{reference}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
