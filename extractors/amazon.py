#!/usr/bin/env python3
"""Amazon orders and shipments across locales.

Amazon sends mails as an order moves through its lifecycle, all from
amazon.<tld> addresses:

- "Ordered: ..."            (auto-confirm@ / bestellbestaetigung@)
- "Dispatched: ..."         (shipment-tracking@ / versandbestaetigung@)
- "Out for delivery: ..."   (shipment-tracking@)
- "Delivered: ..."          (order-update@)
- "Delivery attempted: ..." (order-update@)
- "Your return of ..."      (return@)

The English subject prefixes are the same across all the European
locales we've seen (UK, DE, NL, FR, IT, ES); only the body wording and
currency vary. All mails carry a 17-character order number
(`XXX-NNNNNNN-NNNNNNN`) and the first item title. The "Ordered" mail
also carries the total amount and itemised prices - emit it as a
`.receipt.json` (loosely schema.org `Order`-shaped). Every status mail
emits a `.parcel.json` keyed on the order number so the parcels target
can merge them into one record per order as it progresses.

We deliberately don't emit a calendar event: Amazon doesn't promise a
delivery window precise enough to be useful.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


ORDER_RE = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
TOTAL_RE = re.compile(r"^Total\s*\n\s*([0-9]+(?:\.[0-9]{2})?)\s*([A-Z]{3})", re.M)
ITEM_RE = re.compile(
    r"^\*\s+(.+?)\n\s+Quantity:\s+(\d+)(?:\n\s+([0-9]+(?:\.[0-9]{2})?)\s*([A-Z]{3}))?",
    re.M,
)
# Amazon locale TLDs we've seen confirmation mail from. Anything not
# in this map still gets `amazon` as a fall-back provider id.
LOCALE_TO_PROVIDER = {
    "amazon.co.uk": "amazon-uk",
    "amazon.de": "amazon-de",
    "amazon.nl": "amazon-nl",
    "amazon.fr": "amazon-fr",
    "amazon.it": "amazon-it",
    "amazon.es": "amazon-es",
    "amazon.com": "amazon-us",
}


def sender_locale(from_address: str | None) -> str | None:
    """Return the amazon.<tld> portion of the sender, or None."""
    if not from_address:
        return None
    _, _, domain = from_address.lower().partition("@")
    if not domain.startswith("amazon."):
        return None
    return domain


def status_from_subject(subject: str) -> str | None:
    """Map the leading verb in the subject to a schema.org-ish status."""
    if subject.startswith("Ordered"):
        return "OrderProcessing"
    if subject.startswith("Dispatched"):
        return "OrderInTransit"
    if subject.startswith("Out for delivery"):
        return "OrderInTransit"
    if subject.startswith("Delivered"):
        return "OrderDelivered"
    if subject.startswith("Delivery attempted"):
        return "OrderProblem"
    if subject.startswith("Your return"):
        return "OrderReturned"
    return None


def main() -> int:
    mail = read_message()
    locale = sender_locale(mail.from_address)
    if locale is None:
        return 0
    subject = (mail.subject or "").strip()
    text = mail.text or ""
    if not text:
        return 0

    order_m = ORDER_RE.search(text)
    if not order_m:
        return 0
    order_id = order_m.group(1)

    status = status_from_subject(subject)
    provider_id = LOCALE_TO_PROVIDER.get(locale, "amazon")

    # Parcel record on every status mail.
    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": order_id,
        "provider": {
            "@type": "Organization",
            "@id": provider_id,
            "name": "Amazon",
        },
    }
    if status is not None:
        parcel["deliveryStatus"] = status
    Path(f"{provider_id}-{order_id}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    # Receipt only on the order-placed mail. Other mails reference the
    # same order, but the prices live only in the "Ordered" body.
    if not subject.startswith("Ordered"):
        return 0

    total_m = TOTAL_RE.search(text)
    if not total_m:
        return 0

    items = []
    for item_m in ITEM_RE.finditer(text):
        name = item_m.group(1).strip().rstrip(",")
        qty = int(item_m.group(2))
        item: dict = {
            "@type": "OrderItem",
            "orderedItem": {"@type": "Product", "name": name},
            "orderQuantity": qty,
        }
        if item_m.group(3):
            item["orderItemSubtotal"] = {
                "@type": "PriceSpecification",
                "price": float(item_m.group(3)),
                "priceCurrency": item_m.group(4),
            }
        items.append(item)

    receipt = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Amazon",
        "orderNumber": order_id,
        "orderDate": mail.date.strftime("%Y-%m-%d") if mail.date else None,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total_m.group(1)),
            "priceCurrency": total_m.group(2),
        },
    }
    if items:
        receipt["orderedItem"] = items
    Path(f"{provider_id}-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
