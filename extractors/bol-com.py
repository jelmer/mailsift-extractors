#!/usr/bin/env python3
"""bol.com order confirmations and parcel-status mails.

bol sends a stream of HTML-only mails from `automail@bol.com` as an
order moves through its lifecycle:

- `Bedankt voor je bestelling` - order accepted; carries the order
  number (`Bestelnummer: A000XXXXXX` or `C000XXXXXX`), seller, item,
  and a `Totaal` line.
- `Je pakket is nu bij PostNL` - shipment handed over.
- `De bezorger is onderweg` - out for delivery window.
- `Je pakket is bezorgd!` - delivered.
- `Je pakket ligt bij de buren` - left with a neighbour.

These mails have no plaintext part. The order id is repeated in a
hidden footer `<div>`, which is the most reliable place to find it.

We deliberately don't try to parse the PostNL tracking number out of
these mails - it's only present as an opaque URL in the "Volg je pakket"
button. The companion `noreply@verkopen.bol.com` partner-forwarded
mail does carry a `3S...` code, which the `postnl` extractor picks up
on its own. So our parcel record keys on the bol order id; the parcels
target merges them across status mails.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


# bol order ids: A/C prefix + 9 alphanumerics. The footer copy is the
# most reliable place to find it; the order-confirmation body also says
# "Bestelnummer: XYZ".
ORDER_ID_RE = re.compile(r"\b([AC]000[A-Z0-9]{6})\b")
BESTELNUMMER_RE = re.compile(r"Bestelnummer\s*[:\s]\s*([AC]000[A-Z0-9]{6})", re.I)
# "Totaal ... € 11,00" - the amount can use either a comma or dot
# decimal separator. "Totaal" appears multiple times in some templates;
# we want the grand total, which is the last match in the body.
TOTAL_RE = re.compile(r"Totaal[^\d€]*€\s*([0-9]+[,.][0-9]{2})", re.I)
SELLER_RE = re.compile(r"Verkoper\s*[:\s]\s*([^\n<]+)", re.I)


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
    return "".join(p.parts)


def status_from_subject(subject: str) -> str | None:
    """Map the Dutch subject to a schema.org-ish delivery status."""
    s = subject.lower()
    if s.startswith("bedankt voor je bestelling"):
        return "OrderProcessing"
    if "nu bij postnl" in s:
        return "OrderInTransit"
    if "bezorger is onderweg" in s:
        return "OrderInTransit"
    if "ligt bij de buren" in s:
        return "OrderDelivered"
    if "pakket is bezorgd" in s:
        return "OrderDelivered"
    return None


def main() -> int:
    mail = read_message()
    if (mail.from_address or "").lower() != "automail@bol.com":
        return 0
    subject = (mail.subject or "").strip()
    if not mail.html:
        return 0
    text = strip_html(mail.html)

    # Prefer the explicit "Bestelnummer: XYZ" hit on order
    # confirmations; fall back to any A000.../C000... token anywhere
    # in the body (status mails only carry it in the hidden footer).
    bestel_m = BESTELNUMMER_RE.search(text)
    if bestel_m:
        order_id = bestel_m.group(1)
    else:
        order_m = ORDER_ID_RE.search(text)
        if not order_m:
            return 0
        order_id = order_m.group(1)

    status = status_from_subject(subject)

    # Parcel on every status mail (including the order-placed one, so
    # the parcels target has something to merge into later).
    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": f"bol-{order_id}",
        "orderNumber": order_id,
        "provider": {
            "@type": "Organization",
            "@id": "bol",
            "name": "bol",
        },
    }
    if status is not None:
        parcel["deliveryStatus"] = status
    Path(f"bol-{order_id}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    # Receipt only on the order-confirmation mail. The other mails
    # don't carry the total.
    if not subject.lower().startswith("bedankt voor je bestelling"):
        return 0

    totals = TOTAL_RE.findall(text)
    if not totals:
        return 0
    grand_total = totals[-1].replace(",", ".")

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "bol",
        "orderNumber": order_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(grand_total),
            "priceCurrency": "EUR",
        },
    }
    seller_m = SELLER_RE.search(text)
    if seller_m:
        receipt["seller"] = seller_m.group(1).strip()
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    Path(f"bol-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
