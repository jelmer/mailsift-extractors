#!/usr/bin/env python3
"""Miio Electric EV charging invoice mail.

`invoices@miio.pt` sends `Your invoice` (English or Portuguese) mails
with the invoice PDF attached; the filename is a UUID. The body is
just "we attached an invoice for the period up to DD/MM/YYYY"
boilerplate - amount, session detail and everything else live in the
PDF (or behind a signed link that expires in 7 days).

Emit a receipt keyed on the PDF UUID (stable per invoice, unique) and
preserve the PDF as a sidecar.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
# Body: "invoice for the period up to DD/MM/YYYY"
PERIOD_RE = re.compile(r"period up to\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)


def main() -> int:
    mail = read_message()

    pdf = mail.find_pdf_attachment()
    if pdf is None:
        return 0

    m = UUID_RE.search(pdf.filename or "")
    if not m:
        return 0
    invoice_id = m.group(1).lower()

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Miio",
        "orderNumber": invoice_id,
    }

    text = mail.text or ""
    period_m = PERIOD_RE.search(text)
    if period_m:
        day, month, year = period_m.groups()
        receipt["orderDate"] = f"{year}-{int(month):02d}-{int(day):02d}"
    elif mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"miio-{invoice_id}"
    Path(f"{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    Path(f"{slug}.receipt.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
