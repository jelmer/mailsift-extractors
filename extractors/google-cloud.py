#!/usr/bin/env python3
"""Google Cloud Platform monthly invoice mail.

`payments-noreply@google.com` sends a `Google Cloud Platform & APIs:
Your invoice is available for <customer-id>` mail on the first days of
each month. The plain-text body carries the invoice number and a
customer identifier; the PDF invoice is attached.

Body extract:

    Domain 01920C-C508B1-A90BAD
    Name Some Person
    Invoice number 5684506471
    Payments profile ID 0635-3736-8691

The mail says the balance will be auto-charged, so this is
functionally a bill that will be paid without action - but auto-pay
timing isn't guaranteed, so treat it as a bill and let downstream
tooling schedule the reminder.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

INVOICE_NUMBER_RE = re.compile(r"Invoice number\s+(\S+)")


def main() -> int:
    mail = read_message()
    text = mail.text or ""
    if not text:
        return 0

    m = INVOICE_NUMBER_RE.search(text)
    if not m:
        return 0
    invoice_number = m.group(1)

    # No explicit due date in the body; use the message Date as the
    # issue date and let downstream tooling infer the due date.
    issue_date = mail.date.strftime("%Y-%m-%d") if mail.date else None

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Google Cloud",
        "invoiceNumber": invoice_number,
    }
    if issue_date:
        bill["issueDate"] = issue_date

    slug = f"google-cloud-{invoice_number}"
    Path(f"{slug}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )

    pdf = mail.find_pdf_attachment(invoice_number)
    if pdf is not None:
        Path(f"{slug}.bill.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
