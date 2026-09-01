#!/usr/bin/env python3
"""Generic Shopify-templated order confirmations.

Many Shopify-hosted shops use the stock notification templates almost
unchanged. They produce two mail types we care about:

- Order confirmation: subject like `Order #100002 confirmed`. Plain
  text body carries `Order #<id>`, an order summary table with item
  lines and a `Total\\n\\n£42.30 GBP`-style line. Emit a
  `.receipt.json`.
- Shipment notification: subject like `A shipment from order #<id> is
  on the way`. Body carries the same order id plus a line
  `<Carrier> tracking number: <number>`. Emit a `.parcel.json`.

The merchant name is derived from the sender's own domain when the
shop mails from that domain, or from the `From:` display name when
mail is routed through one of Shopify's shared relays (`t.` /
`g.shopifyemail.com`). Dispatch is driven by DKIM: the manifest
whitelists the signing domains Shopify uses so every shop works
without a per-shop `from_domains` list.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# Shopify's transactional/marketing relays that stand in for a shop's
# own domain. Mail from these carries the shop's identity in the
# display name, not the sender address, so `merchant_from_address` has
# to fall back to the display name for these.
_SHOPIFY_RELAY_DOMAINS = ("shopifyemail.com",)

ORDER_ID_RE = re.compile(r"Order\s+#?([A-Za-z0-9]+)")
# Item line in the order-summary table: "Product name × 1" then a
# blank line then "£12.34". Names can contain almost anything except a
# newline; the × is unicode U+00D7 in the wire template.
ITEM_RE = re.compile(
    r"^(?P<name>.+?)\s*[×x]\s*(?P<qty>\d+)\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)",
    re.MULTILINE,
)
# Final "Total" line: `Total\n\n£42.30 GBP` - the currency suffix is
# what disambiguates the line from the subtotal.
TOTAL_RE = re.compile(
    r"^Total\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)\s+(?P<currency>[A-Z]{3})",
    re.MULTILINE,
)
# Carrier tracking line. The label varies (`DPD tracking number`,
# `Special Care tracking number`, `Royal Mail tracking number`, ...);
# the value is alphanumeric. Restrict the carrier label to non-newline
# whitespace so we don't slurp surrounding lines.
TRACKING_RE = re.compile(
    r"^(?P<carrier>[A-Za-z][A-Za-z0-9 ]*?)\s+tracking\s+number:\s*(?P<number>[A-Za-z0-9]+)",
    re.MULTILINE | re.IGNORECASE,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}

# Characters that aren't safe as a filename component. Anything else
# collapses to a single `-` for the artifact filename slug.
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9]+")


def merchant_slug(merchant: str) -> str:
    """Kebab-cased lowercased merchant name, for use in a filename."""
    return _UNSAFE_FILENAME_RE.sub("-", merchant).strip("-").lower() or "shop"


# Map the parsed carrier label (as it appears in the body) to our
# canonical carrier ids. Anything we don't recognise gets the slugged
# carrier name verbatim so the parcels target still has *something*.
CARRIER_MAP = {
    "dpd": "dpd",
    "royal mail": "royal-mail",
    "special care": "royal-mail",  # The Pi Hut's "Special Care" is Royal Mail Tracked
    "dhl": "dhl",
    "dhl express": "dhl",
    "fedex": "fedex",
    "ups": "ups",
    "evri": "evri",
    "yodel": "yodel",
    "parcelforce": "parcelforce",
}


def merchant_name(mail) -> str:
    """Pick the shop name for the artifact filename and record.

    When the sender domain is one of Shopify's own relays
    (`t.shopifyemail.com`, `g.shopifyemail.com`, ...) the address is a
    shared shopify-hosted mailer that carries no shop identity in the
    domain, so we lift the shop name from the `From:` display name.
    Shops that send from their own domain keep the domain-based
    heuristic; changing that would rename every existing artifact.
    """
    from_address = mail.from_address or ""
    domain = from_address.rsplit("@", 1)[-1].lower() if "@" in from_address else ""

    is_relay = any(
        domain == d or domain.endswith("." + d) for d in _SHOPIFY_RELAY_DOMAINS
    )
    if is_relay:
        return _display_name(mail) or "Shop"

    if domain:
        # `contact@thepihut.com` -> "thepihut.com" -> "Thepihut".
        return domain.split(".")[0].capitalize()
    return "Shop"


def _display_name(mail) -> str:
    """Return the RFC 5322 display name from `From:`, empty if none.

    Falls through the raw header because [`mail.from_address`] has
    already had the address half extracted; we want the phrase.
    """
    raw = mail.message.get("From") if hasattr(mail, "message") else None
    if not raw:
        return ""
    import email.utils

    name, _ = email.utils.parseaddr(raw)
    return name.strip()


def emit_receipt(text: str, mail) -> bool:
    order_m = ORDER_ID_RE.search(text)
    total_m = TOTAL_RE.search(text)
    if not (order_m and total_m):
        return False
    order_id = order_m.group(1)
    merchant = merchant_name(mail)
    items = []
    for item_m in ITEM_RE.finditer(text):
        items.append(
            {
                "@type": "OrderItem",
                "orderedItem": {
                    "@type": "Product",
                    "name": item_m.group("name").strip(),
                },
                "orderQuantity": int(item_m.group("qty")),
                "orderItemSubtotal": {
                    "@type": "PriceSpecification",
                    "price": float(item_m.group("price")),
                    "priceCurrency": SYMBOL_TO_CURRENCY.get(
                        item_m.group("symbol"), "USD"
                    ),
                },
            }
        )
    receipt = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": merchant,
        "orderNumber": order_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total_m.group("price")),
            "priceCurrency": total_m.group("currency"),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    if items:
        receipt["orderedItem"] = items
    Path(f"{merchant_slug(merchant)}-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return True


def emit_parcel(text: str, mail) -> bool:
    order_m = ORDER_ID_RE.search(text)
    track_m = TRACKING_RE.search(text)
    if not track_m:
        return False
    carrier_label = track_m.group("carrier").strip().lower()
    carrier_id = CARRIER_MAP.get(carrier_label, carrier_label.replace(" ", "-"))
    tracking_number = track_m.group("number")
    merchant = merchant_name(mail)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking_number,
        "provider": {
            "@type": "Organization",
            "@id": carrier_id,
            "name": track_m.group("carrier").strip(),
        },
    }
    if order_m:
        parcel["orderNumber"] = order_m.group(1)
    parcel["merchant"] = merchant

    Path(f"{merchant_slug(merchant)}-{tracking_number}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return True


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    text = mail.text or ""
    if not text:
        return 0

    subject_lower = subject.lower()
    emitted_any = False
    # Order confirmation: `Order #N confirmed` (also seen: `Thank you
    # for your order!`, `Order confirmation`).
    if "confirmed" in subject_lower or "thank you for your order" in subject_lower:
        emitted_any |= emit_receipt(text, mail)
    # Shipment: `A shipment from order #N is on the way`.
    if "on the way" in subject_lower or "shipped" in subject_lower:
        emitted_any |= emit_parcel(text, mail)
    # Some shops collapse confirmation and shipping into a single
    # "Order X has been delivered" mail; treat as parcel update.
    if "has been delivered" in subject_lower:
        emitted_any |= emit_parcel(text, mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
