#!/usr/bin/env python3
"""British Airways "BA confirmation of cancellation and refund" mails.

Sent when a booking is cancelled and refunded, on ba.com or by BA
itself. The mail lists the passengers, ticket numbers and refund, but
not the flights, so it emits a `FlightReservation` that carries only
the booking reference and `reservationStatus: ReservationCancelled`.
The host matches that against the legs the e-ticket receipts filed
under the same reference and cancels all of them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_RE = re.compile(
    r"^BA confirmation of cancellation and refund: Ref\.\s*([A-Z0-9]{5,8})$",
    re.IGNORECASE,
)
BOOKING_RE = re.compile(r"Booking reference:\s*([A-Z0-9]{5,8})\b")
# Only a whole-booking cancellation can be applied without the flights.
CANCELLED_RE = re.compile(r"Your British Airways flight booking has been cancelled")


def main() -> int:
    mail = read_message()
    subject_m = SUBJECT_RE.match((mail.subject or "").strip())
    if subject_m is None:
        raise ValueError(f"unexpected subject {mail.subject!r}")
    reference = subject_m.group(1).upper()
    if not mail.text:
        raise ValueError(f"{reference}: no text part")
    text = " ".join(mail.text.split())
    body_m = BOOKING_RE.search(text)
    if body_m is None or body_m.group(1) != reference:
        raise ValueError(f"{reference}: body names a different booking reference")
    if not CANCELLED_RE.search(text):
        raise ValueError(f"{reference}: not a cancellation of the whole booking")

    reservation = {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": reference,
        "reservationStatus": "ReservationCancelled",
    }
    Path(f"ba-{reference}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
