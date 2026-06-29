#!/usr/bin/env python3
"""KPN Mobiel monthly invoice emails (Dutch).

The HTML body, tag-stripped, opens with:

    Deze maand is het totaalbedrag van uw factuur € 16,95.
    Deze factuur hoort bij klantnummer 10000000000.

There is no invoice number in the mail itself, so we synthesise one
from `<klantnummer>-<YYYYMM>` where the year/month come from the message
Date - stable across resends, deterministic per invoice.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


AMOUNT_RE = re.compile(
    r"totaalbedrag van uw factuur\s*€\s*(-?[0-9]+[,.]\d{2})",
    re.I,
)
KLANT_RE = re.compile(r"klantnummer\s*(\d+)", re.I)


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

    amount_m = AMOUNT_RE.search(text)
    klant_m = KLANT_RE.search(text)
    if not (amount_m and klant_m):
        return 0

    amount = float(amount_m.group(1).replace(",", "."))
    klant = klant_m.group(1)

    if mail.date is None:
        return 0
    period = mail.date.strftime("%Y%m")
    invoice_id = f"{klant}-{period}"

    bill = {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "KPN Mobiel",
        "invoiceNumber": invoice_id,
        "accountName": klant,
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": "EUR",
        },
        "paymentDueDate": mail.date.strftime("%Y-%m-%d"),
    }

    Path(f"kpn-mobiel-{invoice_id}.bill.json").write_text(
        json.dumps(bill, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
