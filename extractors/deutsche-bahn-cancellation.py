#!/usr/bin/env python3
"""Deutsche Bahn cancellation confirmations.

"Confirmation of cancellation (order <code>)" and Dutch
"Annuleringsbevestiging (Order <code>)" mails confirm that an online
ticket was cancelled and refunded. They give the order number and the
refund but not the journey, so they emit a `TrainReservation` that
carries only the order number and `reservationStatus:
ReservationCancelled`, for the host to match against the legs
deutsche-bahn filed under the same order number.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_RE = re.compile(
    r"^(?:Confirmation of cancellation|Annuleringsbevestiging) \(order ([A-Z0-9]+)\)$",
    re.IGNORECASE,
)
ORDER_RE = re.compile(r"^(?:Order number|Ordernummer):\s*([A-Z0-9]+)\s*$", re.MULTILINE)


def main() -> int:
    mail = read_message()
    subject_m = SUBJECT_RE.match((mail.subject or "").strip())
    if subject_m is None:
        raise ValueError(f"unexpected subject {mail.subject!r}")
    order = subject_m.group(1)
    if not mail.text:
        raise ValueError(f"order {order}: no text part")
    body_m = ORDER_RE.search(mail.text)
    if body_m is None or body_m.group(1) != order:
        raise ValueError(f"order {order}: body names a different order")

    reservation = {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": order,
        "reservationStatus": "ReservationCancelled",
    }
    Path(f"deutsche-bahn-{order.lower()}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
