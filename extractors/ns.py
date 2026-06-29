#!/usr/bin/env python3
"""Nederlandse Spoorwegen (NS) "Uw factuur staat klaar" invoice mails.

NS doesn't ship a journey-level breakdown by email - those live behind
MijnNS - but each invoice carries enough to file an Invoice record and
a calendar reminder for when the direct debit hits.

Pulled out of the HTML body:

- `factuur <DIGITS>` -> invoice number
- amount in euros (`EUR X,YY`)
- `rond <DD <Dutch month> YYYY>` -> direct-debit date
- `Relatienummer: <DIGITS>` -> customer reference

We emit:

- a `.bill.json` with the invoice details, and
- a `.reservation.json` (`EventReservation`) for the debit date, so
  the user gets a calendar reminder of when the money leaves their
  account.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


INVOICE_RE = re.compile(r"factuur\s+(\d{6,})", re.I)
AMOUNT_RE = re.compile(r"(?:€|EUR)\s*([0-9]+[,.]\d{2})", re.I)
DEBIT_DATE_RE = re.compile(
    r"rond\s+(\d{1,2})\s+(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+(\d{4})",
    re.I,
)
RELATIE_RE = re.compile(r"Relatienummer:\s*(\d+)", re.I)

DUTCH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    invoice_m = INVOICE_RE.search(text)
    if not invoice_m:
        return 0
    invoice_no = invoice_m.group(1)

    amount = None
    if (m := AMOUNT_RE.search(text)) is not None:
        amount = float(m.group(1).replace(",", "."))

    debit_date: datetime | None = None
    if (m := DEBIT_DATE_RE.search(text)) is not None:
        day = int(m.group(1))
        month = DUTCH_MONTHS[m.group(2).lower()]
        year = int(m.group(3))
        debit_date = datetime(year, month, day)

    relatie = None
    if (m := RELATIE_RE.search(text)) is not None:
        relatie = m.group(1)

    bill: dict = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Nederlandse Spoorwegen",
        "invoiceNumber": invoice_no,
    }
    if amount is not None:
        bill["totalPaymentDue"] = {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": "EUR",
        }
    if debit_date is not None:
        bill["paymentDueDate"] = debit_date.strftime("%Y-%m-%d")
    if relatie is not None:
        bill["accountName"] = relatie

    Path(f"ns-{invoice_no}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )

    if debit_date is not None:
        summary = "NS auto-debit"
        if amount is not None:
            # Use a decimal point for iCalendar friendliness; the
            # summary is the only human-facing string.
            summary = f"NS auto-debit (€{amount:.2f})"
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"ns-debit-{invoice_no}",
            "reservationFor": {
                "@type": "Event",
                "name": summary,
                "startDate": debit_date.strftime("%Y-%m-%dT00:00:00"),
                "endDate": debit_date.strftime("%Y-%m-%dT23:59:00"),
            },
        }
        Path(f"ns-debit-{invoice_no}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
