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
can merge them into one record per order as it progresses. Item names
that survive the bullet regex land on the parcel as `itemShipped` too,
so downstream tools can name the contents without cross-referencing.

Amazon parcels can't be polled -- they are keyed on an order number,
which only a signed-in session resolves -- so these mails are the only
source of status, and what they say is worth taking in full. The
"Arriving ..." line above each order becomes `expectedArrivalFrom`/
`Until`; it is always relative to the mail and never carries a year,
so both are resolved against the message date. Wording we don't
recognise is left alone rather than guessed at.

One mail can acknowledge several orders, each in its own block, so the
body is sliced per order rather than scanned once.

We deliberately don't emit a calendar event: Amazon doesn't promise a
delivery window precise enough to be useful.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

ORDER_RE = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
# "Arriving ..." sits on its own line above the order it belongs to.
# Amazon never puts a year in it, and uses either an ASCII hyphen or an
# en-dash in ranges. The Spanish template says "Llega ...".
ARRIVING_RE = re.compile(r"^(?:Arriving|Llega)\s+(.+?)\s*$", re.MULTILINE)
DAY_MONTH_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)$")
DAY_MONTH_RANGE_RE = re.compile(
    r"^(\d{1,2})\s+([A-Za-z]+)\s*[-\u2013]\s*(\d{1,2})\s+([A-Za-z]+)$"
)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    # Spanish mails say "Llega el domingo".
    "lunes": 0,
    "martes": 1,
    "\u00e9rcoles": 2,
    "jueves": 3,
    "viernes": 4,
    "s\u00e1bado": 5,
    "domingo": 6,
}
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
TOTAL_RE = re.compile(
    r"^Total\s*\n\s*([0-9]+(?:\.[0-9]{2})?)\s*([A-Z]{3})", re.MULTILINE
)
ITEM_RE = re.compile(
    r"^\*\s+(.+?)\n\s+Quantity:\s+(\d+)(?:\n\s+([0-9]+(?:\.[0-9]{2})?)\s*([A-Z]{3}))?",
    re.MULTILINE,
)
# The "Track package" link in a dispatch mail carries the three
# parameters Amazon's public tracker needs -- `orderId`, `packageIndex`
# and `shipmentId`. Without all three the page shows "shipment can't be
# found", so we keep the whole URL rather than reassembling it.
TRACK_URL_RE = re.compile(
    r"https?://[^\s\"'<>]*/progress-tracker/package[^\s\"'<>]*"
    r"shipmentId=[^\s\"'<>&]+[^\s\"'<>]*"
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


def _block_start(text: str, orders: list[re.Match[str]], index: int) -> int:
    """Where the block for `orders[index]` begins.

    Each order is introduced by its own "Arriving ..." line. Start
    there when one exists between the previous order number and this
    one, so the order's items and Total stay with it; otherwise fall
    back to just after the previous order number.
    """
    if index == 0:
        return 0
    after_previous = orders[index - 1].end()
    heading = None
    for match in ARRIVING_RE.finditer(text, after_previous, orders[index].start()):
        heading = match
    return heading.start() if heading else after_previous


def resolve_year(ref: date, day: int, month: int) -> int:
    """Pick the year that places `day`/`month` closest to the mail date.

    Amazon never writes a year, so a "3 January" in a late-December
    mail belongs to the next year. Choosing the nearest candidate
    handles both directions without special-casing the rollover.
    """
    candidates = [date(ref.year + offset, month, day) for offset in (-1, 0, 1)]
    candidates.sort(key=lambda d: abs((d - ref).days))
    return candidates[0].year


def parse_arrival(phrase: str, ref: date) -> tuple[date, date] | None:
    """Turn an "Arriving ..." phrase into an inclusive date range.

    Returns `(from, until)` -- equal for a single day -- or None for
    wording we don't recognise, which leaves the record's dates alone
    rather than guessing at one.
    """
    text = phrase.strip().rstrip(".")
    # Drop any time-of-day part: "today 12:45 pm - 4:45 pm" is still
    # just today, and mailroom stores arrival as a date.
    lower = text.lower()

    if lower.startswith(("today", "hoy")):
        return (ref, ref)
    if lower.startswith(("tomorrow", "ma\u00f1ana")):
        nxt = ref + timedelta(days=1)
        return (nxt, nxt)

    range_m = DAY_MONTH_RANGE_RE.match(text)
    if range_m:
        start = _day_month(int(range_m.group(1)), range_m.group(2), ref)
        if start is None:
            return None
        # Resolve the end against the start, so a range crossing new
        # year ("28 December - 3 January") doesn't land in the past.
        end = _day_month(int(range_m.group(3)), range_m.group(4), start)
        if end is None:
            return None
        return (start, end)

    single_m = DAY_MONTH_RE.match(text)
    if single_m:
        day = _day_month(int(single_m.group(1)), single_m.group(2), ref)
        return None if day is None else (day, day)

    # "Arriving Thursday" / "Llega el domingo" -- the next such weekday.
    word = lower.removeprefix("el ").split()[0] if lower else ""
    for name, index in WEEKDAYS.items():
        if word.endswith(name):
            ahead = (index - ref.weekday()) % 7 or 7
            day = ref + timedelta(days=ahead)
            return (day, day)
    return None


def _day_month(day: int, month_name: str, ref: date) -> date | None:
    month = MONTHS.get(month_name.lower())
    if month is None:
        return None
    try:
        return date(resolve_year(ref, day, month), month, day)
    except ValueError:
        # 31 February and friends: bad data, not worth a guess.
        return None


def status_from_subject(subject: str) -> str | None:
    """Map the leading verb in the subject to a schema.org-ish status.

    Amazon reuses the same English lifecycle words across every
    locale on one template and localises them on another (`Ihre
    Amazon.de Bestellung von X wurde versandt!` for dispatch,
    `Bezorgd:` for delivery on the Dutch site, etc). The checks
    below cover the English forms plus the German and Dutch
    variants seen in the mailbox; every language landing here
    keys off the same schema.org status.
    """
    lower = subject.lower()
    # English lifecycle keywords - can appear at the start on the
    # English-locale template or anywhere in the subject on the
    # localised ones ("wurde versandt!" appears after the item name
    # for German dispatch mails).
    # Amazon lowercases the leading verb on some delivery-attempted
    # mails ("delivery attempted: ..."), so match these case-insensitively.
    if lower.startswith("delivery attempted"):
        return "OrderProblem"
    if subject.startswith("Your return"):
        return "OrderReturned"
    if lower.startswith(("out for delivery", "en reparto")):
        return "OutForDelivery"
    if (
        subject.startswith("Dispatched")
        or "wurde versandt" in lower
        or "is verzonden" in lower
    ):
        return "OrderInTransit"
    if subject.startswith("Arriving") or "arriving today" in lower:
        return "OrderInTransit"
    if subject.startswith(("Delivered", "Bezorgd")) or "zugestellt" in lower:
        return "OrderDelivered"
    if (
        subject.startswith("Ordered")
        or "bestellung von" in lower  # DE order confirmation
        or "-bestelling van" in lower  # NL order confirmation
        or "order of" in lower  # `Your Amazon.nl order of X`
    ):
        return "OrderProcessing"
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

    # The order number also shows up in the "Track package" and "View
    # or edit order" links below it, so keep only its first appearance
    # -- otherwise each order is emitted twice and the later, blockless
    # copy overwrites the one carrying the arrival estimate.
    orders = []
    seen = set()
    for match in ORDER_RE.finditer(text):
        if match.group(1) not in seen:
            seen.add(match.group(1))
            orders.append(match)
    if not orders:
        return 0

    status = status_from_subject(subject)
    provider_id = LOCALE_TO_PROVIDER.get(locale, "amazon")
    mail_day = mail.date.date() if mail.date else None

    # One mail can acknowledge several orders, each as its own block:
    # an "Arriving" line, the order number, then that order's items and
    # Total. Slice the body on the order numbers so items and prices
    # land on the order they belong to rather than all on the first.
    for index, order_m in enumerate(orders):
        order_id = order_m.group(1)
        # A block runs from just after the previous order's items to
        # the end of this order's own. Cutting at the following order
        # number would leave this order's items and Total in the next
        # block, so cut at the arrival line that heads it instead.
        block_start = _block_start(text, orders, index)
        block_end = (
            _block_start(text, orders, index + 1)
            if index + 1 < len(orders)
            else len(text)
        )
        block = text[block_start:block_end]

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

        # "Arriving Tuesday" / "Arriving 15 September - 21 September".
        # Only the pre-delivery mails carry one; a delivered parcel has
        # an actual date, not an estimate.
        arriving_m = ARRIVING_RE.search(block)
        if arriving_m and mail_day is not None:
            window = parse_arrival(arriving_m.group(1), mail_day)
            if window is not None:
                first, last = window
                parcel["expectedArrivalFrom"] = first.strftime("%Y-%m-%d")
                parcel["expectedArrivalUntil"] = last.strftime("%Y-%m-%d")

        item_names = [
            item_m.group(1).strip().rstrip(",") for item_m in ITEM_RE.finditer(block)
        ]
        if item_names:
            products = [{"@type": "Product", "name": name} for name in item_names]
            parcel["itemShipped"] = products[0] if len(products) == 1 else products

        # A dispatch mail's "Track package" URL carries the packageIndex
        # and shipmentId that Amazon's public tracker needs, so stash it
        # verbatim. Order-placed mails carry an order-summary link too,
        # but no shipmentId -- ignore those, the fallback URL mailroom
        # synthesises for order pages is a better place to land.
        track_m = TRACK_URL_RE.search(block)
        if track_m:
            parcel["trackingUrl"] = track_m.group(0)

        Path(f"{provider_id}-{order_id}.parcel.json").write_text(
            json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
        )

        # Receipt only on the order-placed mail. Other mails reference
        # the same order, but the prices live only in the "Ordered"
        # body. Any localised subject mapping to OrderProcessing counts.
        if status != "OrderProcessing":
            continue

        total_m = TOTAL_RE.search(block)
        if not total_m:
            continue

        items = []
        for item_m in ITEM_RE.finditer(block):
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
