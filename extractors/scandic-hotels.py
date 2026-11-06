#!/usr/bin/env python3
"""Scandic Hotels post-stay receipts.

`noreply@scandichotels.com` sends a bilingual Norwegian/English mail
after every stay with the subject `Receipt from/Kvitto fra<Hotel
Name>, <City> room/rom <N>`. The body is pure boilerplate; the actual
bill is a PDF attachment named `nor_thfolio_en_<folio-number>.pdf`.

Emit a bill keyed on the folio number from the PDF filename, with
the hotel name and city pulled out of the subject for context.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_RE = re.compile(
    r"Receipt\s+from/Kvitto\s+fra\s*(?P<hotel>[^,]+?),\s+(?P<city>[^,]+?)\s+"
    r"room/rom\s+(?P<room>\w+)",
    re.IGNORECASE,
)
FOLIO_RE = re.compile(r"(?:thfolio[_-])?(\d{6,})", re.IGNORECASE)


def main() -> int:
    mail = read_message()
    if not mail.subject:
        return 0

    pdf = mail.find_pdf_attachment()
    if pdf is None or not pdf.bytes:
        return 0

    folio_match = FOLIO_RE.search(pdf.filename or "")
    folio = folio_match.group(1) if folio_match else None
    if not folio:
        return 0

    subject_match = SUBJECT_RE.search(mail.subject)
    hotel = subject_match.group("hotel").strip() if subject_match else "Scandic"

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "identifier": folio,
        "provider": {"@type": "Organization", "name": "Scandic Hotels"},
        "accountId": folio,
    }
    if subject_match:
        bill["description"] = f"{hotel}, {subject_match.group('city').strip()}"
    if mail.date:
        bill["billingDate"] = mail.date.strftime("%Y-%m-%d")

    slug = f"scandic-{folio}"
    Path(f"{slug}.bill.json").write_text(json.dumps(bill, ensure_ascii=False))
    Path(f"{slug}.bill.pdf").write_bytes(pdf.bytes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
