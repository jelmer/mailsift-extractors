#!/usr/bin/env python3
"""BahnCard (Deutsche Bahn) invoice mail.

`noreply.bahncard-rechnung@bahn.de` sends a
`(ID 1-XXXXXXXX) Invoice for your BahnCard` mail with the invoice
attached as a PDF. The body itself is a boilerplate "please find
attached" message; amount, due date and bank details live only in the
PDF.

Emit a stub `.bill.json` keyed on the ID in the subject so the record
files sensibly, and preserve the PDF as a `.bill.pdf` sidecar for the
actual invoice content.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_ID_RE = re.compile(r"\(ID\s+([A-Z0-9-]+)\)", re.IGNORECASE)


def main() -> int:
    mail = read_message()
    if not mail.subject:
        return 0

    m = SUBJECT_ID_RE.search(mail.subject)
    if not m:
        return 0
    invoice_id = m.group(1)

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Deutsche Bahn",
        "invoiceNumber": invoice_id,
    }
    if mail.date:
        bill["issueDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"bahncard-{invoice_id}"
    Path(f"{slug}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )

    pdf = mail.find_pdf_attachment("bahncard")
    if pdf is not None:
        Path(f"{slug}.bill.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
