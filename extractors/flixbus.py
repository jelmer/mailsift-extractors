#!/usr/bin/env python3
"""FlixBus payment-proof mail.

`noreply@fs.flixbus.com` sends `Payment proof email` after each
booking is paid, with the receipt attached as
`Payment Receipt-<booking-id>.pdf`. Body carries `Thank you for your
booking (#<booking-id>)` and little else - the actual receipt data
lives in the PDF.

Emit a receipt keyed on the booking id and preserve the PDF sidecar.
FlixBus also sends the itinerary in a separate mail with `.ics`
attached; that's handled elsewhere (or should be).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

BOOKING_RE = re.compile(r"booking\s*\(?\#?(\d+)\)?", re.IGNORECASE)
FILENAME_BOOKING_RE = re.compile(r"[-_](\d+)\.pdf$", re.IGNORECASE)


def main() -> int:
    mail = read_message()

    pdf = mail.find_pdf_attachment("payment")
    if pdf is None:
        return 0

    booking_id: str | None = None
    for text in (mail.text or "", mail.html or ""):
        m = BOOKING_RE.search(text)
        if m:
            booking_id = m.group(1)
            break
    if not booking_id:
        m = FILENAME_BOOKING_RE.search(pdf.filename or "")
        if m:
            booking_id = m.group(1)
    if not booking_id:
        return 0

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "FlixBus",
        "orderNumber": booking_id,
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"flixbus-{booking_id}"
    Path(f"{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    Path(f"{slug}.receipt.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
