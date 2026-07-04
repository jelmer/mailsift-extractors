#!/usr/bin/env python3
"""Deliveroo order-confirmation emails.

Deliveroo sends order-accepted mails from noreply@t.deliveroo.com.
Subjects vary by restaurant ("<X> has accepted your order", "Your
order's in the kitchen") but the plaintext body always carries the
same structured receipt:

    Hi <name>,
    The Example Grill has accepted your order
          Your order will arrive today at 22:30.
    ...
    Your Receipt for Order #4401
    Deliver from:
    The Example Grill
    1 Example Street
    London EC1A 1AA
    +442036020862
    Deliver to:
    ...
    ---------------------
      1x Mixed Salad - £6.90
      1x Hummus - £6.90
      1x Grilled Halloumi - £8.15
      1x Shish Taouk - £17.25
    Subtotal £39.20
    ...
    Total £42.19
    ...
    Your Deliveroo order ID is 50000000000.

We extract the order id, restaurant, line items, totals, and the
delivery ETA (when the body says "arrive today at HH:MM"). We emit a
`receipt` always, and an `EventReservation` if we have an ETA.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


ORDER_ID_RE = re.compile(r"Your\s+Deliveroo\s+order\s+ID\s+is\s+(\d+)", re.I)
SHORT_ORDER_ID_RE = re.compile(r"Order\s+#(\d+)", re.I)
DELIVER_FROM_RE = re.compile(r"Deliver\s+from:\s*\n\s*\n(?P<merchant>[^\n]+)\n", re.I)
ITEM_RE = re.compile(
    r"^\s*(?P<qty>\d+)x\s+(?P<name>[^\n-]+?)\s+-\s+([£€$])(?P<price>\d+(?:\.\d{2})?)\s*$",
    re.M,
)
TOTAL_RE = re.compile(r"^Total\s+([£€$])(?P<price>\d+(?:\.\d{2})?)\s*$", re.M)
ETA_RE = re.compile(
    r"Your\s+order\s+will\s+arrive\s+today\s+at\s+(?P<time>\d{1,2}:\d{2})", re.I
)
SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def main() -> int:
    mail = read_message()
    if not mail.text:
        return 0
    text = mail.text

    order_match = ORDER_ID_RE.search(text) or SHORT_ORDER_ID_RE.search(text)
    if not order_match:
        return 0
    order_id = order_match.group(1)

    merchant_match = DELIVER_FROM_RE.search(text)
    if not merchant_match:
        return 0
    merchant = merchant_match.group("merchant").strip()

    items: list[dict] = []
    currency = "GBP"
    for item_match in ITEM_RE.finditer(text):
        symbol = item_match.group(3)
        currency = SYMBOL_TO_CURRENCY.get(symbol, currency)
        items.append(
            {
                "@type": "OrderItem",
                "orderQuantity": int(item_match.group("qty")),
                "orderedItem": {
                    "@type": "Product",
                    "name": item_match.group("name").strip(),
                },
                "orderItemSubtotal": {
                    "@type": "PriceSpecification",
                    "price": float(item_match.group("price")),
                    "priceCurrency": SYMBOL_TO_CURRENCY.get(symbol, "USD"),
                },
            }
        )

    total = None
    total_match = TOTAL_RE.search(text)
    if total_match:
        currency = SYMBOL_TO_CURRENCY.get(total_match.group(1), currency)
        total = float(total_match.group("price"))

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": merchant,
        "broker": {"@type": "Organization", "name": "Deliveroo"},
        "orderNumber": f"deliveroo-{order_id}",
    }
    if total is not None:
        receipt["priceSpecification"] = {
            "@type": "PriceSpecification",
            "price": total,
            "priceCurrency": currency,
        }
    if items:
        receipt["orderedItem"] = items
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    Path(f"deliveroo-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )

    eta_match = ETA_RE.search(text)
    if eta_match and mail.date is not None:
        eta_hour, eta_minute = (int(x) for x in eta_match.group("time").split(":"))
        day = mail.date.replace(tzinfo=None)
        eta = day.replace(hour=eta_hour, minute=eta_minute, second=0, microsecond=0)
        # If the ETA already happened today (parsing midnight crossover),
        # bump to the next day so the calendar entry is in the future.
        if eta < day:
            eta = eta + timedelta(days=1)
        # Treat the ETA as a 30-minute window so it shows up nicely.
        end = eta + timedelta(minutes=30)
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"deliveroo-delivery-{order_id}",
            "reservationFor": {
                "@type": "Event",
                "name": f"Deliveroo: {merchant}",
                "startDate": eta.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"deliveroo-delivery-{order_id}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
