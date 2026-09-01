#!/usr/bin/env python3
"""SNCF Connect trip confirmations.

SNCF Connect sends a `Your trip <Origin> - <Destination>, outbound
on <Weekday, D Month YYYY>` mail after every purchase. The English
plain-text body carries the booking reference (PNR) and the order
total but not, unfortunately, per-train departure times or seat
assignments; those are only in the HTML rendering and are laid out
too fragilely to scrape reliably.

We emit a `.receipt.json` per trip, keyed on the PNR. A follow-up
`Your Purchase Proof` receipt is skipped: it carries the same PNR
and would just overwrite the record in place.

Subject on French-locale accounts (`Votre voyage ...`) isn't matched
by the manifest; adding French would need parallel parsing of the
"Total commande" / "Numero de reservation" body labels and there
are none of those in the corpus we've seen. Add when a real
French-locale mail turns up.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# `Reference number  TB425X / HP5290517200` - the first token is the
# PNR the user sees; the second is SNCF's internal order id. Two
# spaces after the label is intentional; SNCF's template pads it.
PNR_RE = re.compile(r"Reference number\s+(?P<pnr>[A-Z0-9]{6})\s*/\s*[A-Z0-9]{8,}")
# `Order total : €204.00` - space around the colon matches the wire
# template exactly.
TOTAL_RE = re.compile(
    r"Order total\s*:\s*(?P<symbol>[€£$])\s*(?P<amount>\d+(?:\.\d{2})?)"
)
# `Your trip <O> - <D>, outbound on <weekday>, <D Month YYYY>`
SUBJECT_TRIP_RE = re.compile(
    r"^Your trip\s+(?P<origin>.+?)\s+-\s+(?P<destination>.+?),\s*outbound on",
    re.IGNORECASE,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    text = mail.text or ""
    if not text:
        return 0

    pnr_match = PNR_RE.search(text)
    total_match = TOTAL_RE.search(text)
    subject_match = SUBJECT_TRIP_RE.match(subject)
    if not (pnr_match and total_match and subject_match):
        return 0

    pnr = pnr_match.group("pnr")
    origin = subject_match.group("origin").strip()
    destination = subject_match.group("destination").strip()

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "SNCF Connect",
        "orderNumber": pnr,
        "description": f"{origin} - {destination}",
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total_match.group("amount")),
            "priceCurrency": SYMBOL_TO_CURRENCY.get(total_match.group("symbol"), "EUR"),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    Path(f"sncf-connect-{pnr}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
