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
rather than a specific train, so there is no single train trip to
record as a `TrainReservation` (and schema.org has no date-only
train slot anyway). Instead we emit the attached VAT receipt PDF
as a bill plus a ticket blob keyed on the booking code; the bill
captures payee/invoice-number for Firefly, the ticket carries the
paper proof you present to the conductor.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

BOOKING_CODE_RE = re.compile(r"Booking code:\s*([0-9]{4}(?:\s+[0-9]{4}){2,4})")
TRANSACTION_RE = re.compile(r"Transaction number:\s*([0-9]+)")


def main() -> int:
    mail = read_message()
    if not mail.text:
        return 0

    code_match = BOOKING_CODE_RE.search(mail.text)
    if not code_match:
        return 0
    booking_code = re.sub(r"\s+", "", code_match.group(1))

    pdf = mail.find_pdf_attachment("bescheinigung") or mail.find_pdf_attachment(
        "ticket"
    )
    if pdf is None or not pdf.bytes:
        return 0

    tx_match = TRANSACTION_RE.search(mail.text)
    invoice_number = tx_match.group(1) if tx_match else booking_code

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        # mailsift's bill sink keys files under <payee>-<invoice>, so
        # `payee` is load-bearing rather than merely descriptive.
        "payee": "ÖBB",
        "accountId": booking_code,
        "invoiceNumber": invoice_number,
    }
    if mail.date:
        bill["issueDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"oebb-{invoice_number}"
    Path(f"{slug}.bill.json").write_text(json.dumps(bill, ensure_ascii=False))
    Path(f"{slug}.bill.pdf").write_bytes(pdf.bytes)
    Path(f"oebb-{booking_code}.ticket.pdf").write_bytes(pdf.bytes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
