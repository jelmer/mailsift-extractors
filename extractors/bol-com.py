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

from mailsift_extractor import read_message
from mailsift_extractor import strip_html as block_text

# bol order ids come in two flavours:
# - Legacy (pre-2015): a plain 10-digit numeric (`NNNNNNNNNN`).
# - Modern: `[AC]000` prefix + 6 alphanumerics.
# The footer / `Bestelnummer:` label is the most reliable place; a
# bare regex over the body would match dates and other numbers.
ORDER_ID_RE = re.compile(r"\b([AC]000[A-Z0-9]{6}|\d{10})\b")
BESTELNUMMER_RE = re.compile(
    r"Bestelnummer\s*[:\s]\s*([AC]000[A-Z0-9]{6}|\d{10})", re.IGNORECASE
)
# "Totaal ... € 11,00" - the amount can use either a comma or dot
# decimal separator. "Totaal" appears multiple times in some templates;
# we want the grand total, which is the last match in the body.
TOTAL_RE = re.compile(r"Totaal[^\d€]*€\s*([0-9]+[,.][0-9]{2})", re.IGNORECASE)
SELLER_RE = re.compile(r"Verkoper\s*[:\s]\s*([^\n<]+)", re.IGNORECASE)
# Item names appear in a few positions across the template family:
# - modern "Bedankt..." mail: between the order number and the seller.
# - shipped/delivered mails: after "Dit is (onderweg|bezorgd) N artikel(en)".
# - legacy "Bevestiging van uw bestelling" mail: after "Besteld bij bol.com:".
ITEM_MODERN_RE = re.compile(
    r"Bestelnummer:\s*[AC]000[A-Z0-9]{6}\s+(.+?)\s+Verkoper:", re.IGNORECASE
)
ITEM_STATUS_RE = re.compile(
    r"Dit is (?:onderweg|bezorgd)\s+\d+\s+artike\w*\s+(.+?)\s+(?:[AC]000[A-Z0-9]{6}|\d{10})",
    re.IGNORECASE,
)
# Pre-2015 mails list the items in a table under "Besteld bij
# bol.com:": title (`Of Mice and Men -`), author, format, then the
# quantity, the price and line total (`€` / `9,99`), and on the order
# confirmation the delivery time.
LEGACY_TABLE_HEADINGS = {"Titel", "Aantal", "Prijs", "Totaal", "Levertijd"}
LEGACY_TABLE_END = {"Bestelbedrag", "Subtotaal", "Totaalbedrag", "Totaal"}
LEGACY_PRICE_RE = re.compile(r"^(?:€|€\s*[\d.,]+|[\d.,]+)$")
LEGACY_QUANTITY_RE = re.compile(r"^\d+$")
LEGACY_DELIVERY_TIME_RE = re.compile(r"werkdag|in huis|weken|voorraad", re.IGNORECASE)
LEGACY_NOT_TITLE_RE = re.compile(
    r"^(?:Schrijf een review|(?:Engels|Nederlands|Duits|Frans)\b.*)$|"
    r"\b(?:Paperback|Hardcover|Gebonden|E-book)\b",
    re.IGNORECASE,
)


def legacy_items(html: str) -> list[tuple[str, int, float | None]]:
    """`(title, quantity, price)` for each row of the pre-2015 table."""
    lines = [line.strip() for line in block_text(html, block_tags=True).splitlines()]
    lines = [line for line in lines if line]
    try:
        index = lines.index("Besteld bij bol.com:") + 1
    except ValueError:
        return []
    while index < len(lines) and lines[index] in LEGACY_TABLE_HEADINGS:
        index += 1
    items = []
    while index < len(lines) and lines[index] not in LEGACY_TABLE_END:
        names = []
        while index < len(lines) and not LEGACY_QUANTITY_RE.match(lines[index]):
            names.append(lines[index])
            index += 1
        if index == len(lines):
            break
        quantity = int(lines[index])
        index += 1
        prices = []
        while index < len(lines) and LEGACY_PRICE_RE.match(lines[index]):
            amount = lines[index].lstrip("€").strip()
            if amount:
                prices.append(float(amount.replace(",", ".")))
            index += 1
        if index < len(lines) and LEGACY_DELIVERY_TIME_RE.search(lines[index]):
            index += 1
        # A missing author shows as `-`.
        parts = [n.rstrip(" -") for n in names[:1]]
        parts += [
            n for n in names[1:2] if n.strip(" -") and not LEGACY_NOT_TITLE_RE.search(n)
        ]
        if parts:
            items.append((" - ".join(parts), quantity, prices[0] if prices else None))
    return items


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
    """Map the Dutch subject to a schema.org-ish delivery status.

    Modern bol templates use informal `je` phrasing; legacy 2012-era
    ones use the formal `uw` form (`Bevestiging van uw bestelling ...`
    for orders, `Uw bestelling ... wordt verzonden` for dispatch).
    """
    s = subject.lower()
    if s.startswith(
        (
            "bedankt voor je bestelling",
            "bevestiging van je bestelling",
            "bevestiging van uw bestelling",
        )
    ):
        return "OrderProcessing"
    if "wordt verzonden" in s:
        return "OrderInTransit"
    if "nu bij postnl" in s:
        return "OrderInTransit"
    if "bezorger is onderweg" in s:
        return "OrderInTransit"
    if "ligt bij de buren" in s or "afgeleverd" in s:
        return "OrderDelivered"
    if "pakket is bezorgd" in s:
        return "OrderDelivered"
    return None


def main() -> int:
    mail = read_message()
    # bol has used at least two automated senders over the years:
    # `automail@bol.com` on the modern templates and `noreply@bol.com`
    # on the pre-2015 ones. Accept either; the manifest only lets the
    # older, mostly unsigned, ones through for mail received before
    # bol signed it.
    from_address = (mail.from_address or "").lower()
    if from_address not in ("automail@bol.com", "noreply@bol.com"):
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
    # Item name, if a template we understand names it. The bul (buren /
    # neighbours) template just carries an address, so no item field.
    item_m = ITEM_MODERN_RE.search(text) or ITEM_STATUS_RE.search(text)
    # An old dispatch mail lists only what went in that shipment, and
    # would replace the whole order the confirmation listed.
    old_items = (
        legacy_items(mail.html) if not item_m and status == "OrderProcessing" else []
    )
    if item_m:
        parcel["itemShipped"] = {
            "@type": "Product",
            "name": item_m.group(1).strip(),
        }
    elif old_items:
        products = [{"@type": "Product", "name": name} for name, _, _ in old_items]
        parcel["itemShipped"] = products[0] if len(products) == 1 else products
    Path(f"bol-{order_id}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    # Receipt only on the order-confirmation mail. The other mails
    # don't carry the total. Accept both the modern
    # `Bedankt voor je bestelling` and the legacy
    # `Bevestiging van (je|uw) bestelling` phrasings.
    if not subject.lower().startswith(
        (
            "bedankt voor je bestelling",
            "bevestiging van je bestelling",
            "bevestiging van uw bestelling",
        )
    ):
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
    if old_items:
        receipt["orderedItem"] = [
            {
                "@type": "OrderItem",
                "orderedItem": {"@type": "Product", "name": name},
                "orderQuantity": quantity,
            }
            | (
                {}
                if price is None
                else {
                    "orderItemSubtotal": {
                        "@type": "PriceSpecification",
                        "price": price,
                        "priceCurrency": "EUR",
                    }
                }
            )
            for name, quantity, price in old_items
        ]
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
