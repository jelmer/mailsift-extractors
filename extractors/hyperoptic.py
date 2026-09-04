#!/usr/bin/env python3
"""Hyperoptic broadband payment-receipt mail.

`no_reply@hyperoptic.com` sends a `Thanks for your payment` mail with
the payment receipt attached as a PDF (filename like
`WP000001830427_Invoice.pdf`). The email body is HTML-only boilerplate
- amount, period, and everything else lives in the PDF.

Emit a stub `.receipt.json` keyed on the receipt number pulled from
the PDF filename, and preserve the PDF as a `.receipt.pdf` sidecar.

The corpus fixture uses a second Hyperoptic mail sent seconds later
that carries the actual PDF; the sibling no-PDF `Thanks for your
payment` mail is filtered out by the `attachment:filename:*.pdf`
requirement in the manifest.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

FILENAME_ID_RE = re.compile(r"(WP\d+)", re.IGNORECASE)


def main() -> int:
    mail = read_message()

    pdf = mail.find_pdf_attachment()
    if pdf is None:
        return 0

    m = FILENAME_ID_RE.search(pdf.filename or "")
    if not m:
        return 0
    receipt_id = m.group(1).upper()

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Hyperoptic",
        "orderNumber": receipt_id,
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"hyperoptic-{receipt_id}"
    Path(f"{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    Path(f"{slug}.receipt.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
