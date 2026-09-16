#!/usr/bin/env python3
"""Google Play receipt extractor.

Google Play sends a stable plaintext receipt format with:

    Order number: GPA.XXXX-XXXX-XXXX-XXXXX
    Order date: 19 Jun 2026 14:13:03 BST
    Your account: test@example.org
    ...
    Total: £1.59/month

Used for one-off purchases and recurring subscription renewals. We emit
a `.receipt.json` for each, loosely schema.org `Order`-shaped.

Renewals additionally say so in the body - either a `/month`-style
suffix on the price, or wording like `Auto-renewing subscription` or
`Monthly Subscription`. Those also get a `.subscription.json` so the
recurring relationship is tracked separately from the individual
charge.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# Modern Google Play order numbers are `GPA.NNNN-NNNN-NNNN-NNNNN`.
# Older mail (pre-2014-ish, including Google Play Music receipts)
# used a bare `<digits>.<digits>` form on its own line right after
# the `Order number:` label.
ORDER_RE = re.compile(
    r"^Order number:\s*\n?\s*(GPA\.[\w.\-]+|\d{10,}\.\d{10,})",
    re.MULTILINE,
)
DATE_RE = re.compile(
    r"^Order date:\s*(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})", re.MULTILINE
)
# Item line: blank line, then the item title (possibly with a
# trailing `(by Publisher)`), then a price on the next line. Line
# endings vary between `\n` (text pipeline) and `\r\n` (email source),
# so we spell them out explicitly.
ITEM_RE = re.compile(
    r"(?:\r?\n){2}([^\r\n]+?(?:\(by [^\)]+\))?)\r?\n(?:£|€|\$)([0-9]+(?:\.[0-9]{1,2})?)"
)
# `Total: £57.99` on its own line (modern), or inline
# `Tax: $0.00Total: $0.00` (2013 Google Play Music format has no
# whitespace between the preceding amount and the `Total:` label).
TOTAL_RE = re.compile(r"Total:\s*(£|€|\$)?\s*([0-9]+(?:\.[0-9]{1,2})?)")
# A recurring charge is flagged either by a period suffix on the price
# (`£1.59/month`) or by wording elsewhere in the body. The 2013 Play
# Music format uses `Monthly Subscription`; current mail says
# `Auto-renewing subscription`.
PERIOD_RE = re.compile(
    r"(?:£|€|\$)[0-9]+(?:\.[0-9]{1,2})?\s*/\s*(month|year|week)\b", re.IGNORECASE
)
RECURRING_RE = re.compile(
    r"auto-renewing subscription|(monthly|yearly|annual|weekly) subscription",
    re.IGNORECASE,
)
# The 2013 format emphasises the item name with asterisks
# (`*Google Play Music All Access*$0.00Monthly Subscription`), which
# the modern ITEM_RE doesn't match.
LEGACY_ITEM_RE = re.compile(r"\*([^*\r\n]+)\*(?:£|€|\$)[0-9]")
# `First charge on 17-Jul-2013` - the date the subscription next bills.
FIRST_CHARGE_RE = re.compile(
    r"First charge on\s*\r?\n?\s*(\d{1,2})-([A-Z][a-z]{2})-(\d{4})", re.IGNORECASE
)
# ISO 8601 durations, which is what `subscriptionDuration` carries.
PERIOD_TO_DURATION = {
    "week": "P1W",
    "month": "P1M",
    "year": "P1Y",
    "monthly": "P1M",
    "yearly": "P1Y",
    "annual": "P1Y",
    "weekly": "P1W",
}

MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def subscription_duration(text: str) -> str | None:
    """ISO 8601 duration if the receipt is a recurring charge, else None."""
    period_m = PERIOD_RE.search(text)
    if period_m:
        return PERIOD_TO_DURATION[period_m.group(1).lower()]
    recurring_m = RECURRING_RE.search(text)
    if recurring_m:
        word = recurring_m.group(1)
        # `Auto-renewing subscription` states no period; monthly is the
        # Play default and the only period that branch ever sees.
        return PERIOD_TO_DURATION[word.lower()] if word else "P1M"
    return None


def main() -> int:
    mail = read_message()
    sender = (mail.from_address or "").lower()
    if "googleplay-noreply@google.com" not in sender:
        return 0
    text = mail.text or ""
    if not text:
        return 0

    order_m = ORDER_RE.search(text)
    if not order_m:
        return 0
    order_id = order_m.group(1)

    total_m = TOTAL_RE.search(text)
    if not total_m:
        return 0
    symbol = total_m.group(1) or ""
    currency = SYMBOL_TO_CURRENCY.get(symbol, "USD")
    amount = float(total_m.group(2))

    receipt = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Google Play",
        "orderNumber": order_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": currency,
        },
    }

    items = []
    item_names = []
    for item_match in ITEM_RE.finditer(text):
        name = item_match.group(1).strip()
        item_names.append(name)
        items.append(
            {
                "@type": "OrderItem",
                "orderedItem": {"@type": "Product", "name": name},
                "orderQuantity": 1,
                "orderItemSubtotal": {
                    "@type": "PriceSpecification",
                    "price": float(item_match.group(2)),
                    "priceCurrency": currency,
                },
            }
        )
    if items:
        receipt["orderedItem"] = items

    date_m = DATE_RE.search(text)
    if date_m:
        try:
            order_date = datetime(
                int(date_m.group(3)),
                MONTH_ABBR[date_m.group(2)],
                int(date_m.group(1)),
            )
            receipt["orderDate"] = order_date.strftime("%Y-%m-%d")
        except (KeyError, ValueError):
            pass
    if "orderDate" not in receipt and mail.date is not None:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    duration = subscription_duration(text)
    if duration is not None:
        # Prefer the item name over the bare order id: a subscription
        # record is a standing relationship, and `name` is what the
        # dashboard lists it under.
        item_name = item_names[0] if item_names else None
        if item_name is None:
            legacy_m = LEGACY_ITEM_RE.search(text)
            if legacy_m:
                item_name = legacy_m.group(1).strip()
        subscription = {
            "@context": "https://schema.org",
            "@type": "Offer",
            "name": item_name or "Google Play subscription",
            # `provider` must stay a plain string; mailsift parses this
            # field as one.
            "provider": "Google Play",
            "subscriptionDuration": duration,
            "price": amount,
            "priceCurrency": currency,
        }
        if "orderDate" in receipt:
            subscription["orderDate"] = receipt["orderDate"]
        charge_m = FIRST_CHARGE_RE.search(text)
        if charge_m:
            try:
                subscription["renewalDate"] = datetime(
                    int(charge_m.group(3)),
                    MONTH_ABBR[charge_m.group(2).title()],
                    int(charge_m.group(1)),
                ).strftime("%Y-%m-%d")
            except (KeyError, ValueError):
                pass
        sub_slug = re.sub(
            r"[^A-Za-z0-9_+-]+", "-", item_name or f"google-play-{order_id}"
        ).strip("-")
        Path(f"{sub_slug}.subscription.json").write_text(
            json.dumps(subscription, ensure_ascii=False), encoding="utf-8"
        )

    # Slugify the order id for the filename. Google's order ids contain
    # dots (`GPA.0000-...`) and sometimes runs of them (`..3` in
    # subscription renewals); replace any non-alphanumeric run with a
    # single hyphen so the only `.` left in the filename is the one
    # separating slug from kind.
    slug = re.sub(r"[^A-Za-z0-9_+-]+", "-", order_id).strip("-")
    Path(f"google-play-{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
