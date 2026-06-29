#!/usr/bin/env python3
"""E.ON Next monthly energy statements.

The "FYI: Your energy statement" mail body opens with the account number
and statement period, and includes the direct-debit collection line:

    Account no. - A-00000000
    9th May 2026 - 8th June 2026
    ...
    Direct Debit collection - 1st June 2026: £24.12 CR

No explicit invoice number, so we synthesise one from
`<account>-<period-end>` - stable across re-sends, deterministic per
statement.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


ACCOUNT_RE = re.compile(r"Account no\.?\s*[-:]\s*([A-Z0-9-]+)", re.I)
PERIOD_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s*-\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.I,
)
DD_RE = re.compile(
    r"Direct Debit collection\s*-\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s*:\s*£\s*([0-9]+(?:\.[0-9]{2})?)",
    re.I,
)

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

    account_m = ACCOUNT_RE.search(text)
    period_m = PERIOD_RE.search(text)
    if not (account_m and period_m):
        return 0

    account = account_m.group(1).strip()
    period_end = datetime(
        int(period_m.group(6)),
        MONTHS[period_m.group(5).lower()],
        int(period_m.group(4)),
    )

    invoice_id = f"{account}-{period_end.strftime('%Y%m')}"

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "E.ON Next",
        "invoiceNumber": invoice_id,
        "accountName": account,
    }

    dd_m = DD_RE.search(text)
    if dd_m:
        amount = float(dd_m.group(4))
        due_date = datetime(
            int(dd_m.group(3)),
            MONTHS[dd_m.group(2).lower()],
            int(dd_m.group(1)),
        )
        bill["totalPaymentDue"] = {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": "GBP",
        }
        bill["paymentDueDate"] = due_date.strftime("%Y-%m-%d")
    else:
        # No DD line - file the statement against the period end so the
        # bill still lands in the right year folder.
        bill["paymentDueDate"] = period_end.strftime("%Y-%m-%d")

    Path(f"eon-next-{invoice_id}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
