#!/usr/bin/env python3
"""Switch2 (community heat network) payment receipts.

The "Your payment receipt" mail confirms a direct debit / card payment
against a Switch2 account. Plain-text body:

    Date: 04 June 2026 09:42
    Payment Amount: £70.81
    Reference Number; 00000000000000000000000000000000

The portal-facing "New Bill Available" nudges carry no amount in the
body and are skipped. We file an Invoice receipt with the Switch2
reference number as `invoiceNumber` and the payment date as `dueDate` so
the bill ends up in the right year folder.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


DATE_RE = re.compile(
    r"Date:?\s+(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.I,
)
AMOUNT_RE = re.compile(r"Payment Amount:?\s*£\s*([0-9]+(?:\.[0-9]{2})?)", re.I)
REF_RE = re.compile(r"Reference Number[;:]?\s*([A-Fa-f0-9]{8,})")


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def main() -> int:
    mail = read_message()
    text = mail.text or ""
    if not text:
        return 0

    amount_m = AMOUNT_RE.search(text)
    ref_m = REF_RE.search(text)
    date_m = DATE_RE.search(text)
    if not (amount_m and ref_m and date_m):
        return 0

    amount = float(amount_m.group(1))
    reference = ref_m.group(1)
    day = int(date_m.group(1))
    month = MONTHS[date_m.group(2).lower()]
    year = int(date_m.group(3))
    paid_on = datetime(year, month, day)

    bill = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Switch2 Energy",
        "invoiceNumber": reference,
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": "GBP",
        },
        "paymentDueDate": paid_on.strftime("%Y-%m-%d"),
    }
    Path(f"switch2-{reference}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
