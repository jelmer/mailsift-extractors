#!/usr/bin/env python3
"""Sainsbury's grocery orders, delivery slots and receipts.

Three message types share the sainsburys.co.uk sender:

- "Thanks for your order - N" (order confirmation, HTML only). Emits the
  delivery slot as an EventReservation and the estimated total as a
  Bill; the payment-taken date lines up with the delivery date.

- "Your delivery will arrive between H:MMam - H:MMpm" (delivery window
  update, HTML). Emits an EventReservation for the slot, keyed by order
  number so it replaces the confirmation-mail slot in place.

- "Receipt for your Sainsbury's order N" (post-delivery receipt, plain
  text with a PDF attached). Emits an Order receipt with the actual
  payment total.

All three UIDs are `sainsburys-<order-number>` so downstream dedup
merges them per order.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, read_message

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

POSTCODE_RE = r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}"

# Delivery window mail: "Tuesday 17 March, 11:37am - 12:37pm to EC1A 1AA"
SLOT_WITH_POSTCODE_RE = re.compile(
    r"(?P<weekday>Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]+)"
    r",\s*"
    r"(?P<start>\d{1,2}(?::\d{2})?(?:am|pm))\s*(?:-|to)\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?(?:am|pm))"
    r"\s+to\s+(?P<postcode>" + POSTCODE_RE + r")",
    re.IGNORECASE,
)

# Order confirmation body: "Slot date: Monday 17 August 11am to 3pm"
SLOT_ORDER_RE = re.compile(
    r"Slot\s+date:\s*"
    r"(?P<weekday>Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Z][a-z]+)\s+"
    r"(?P<start>\d{1,2}(?::\d{2})?(?:am|pm))\s*(?:-|to)\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?(?:am|pm))",
    re.IGNORECASE,
)

# Receipt body: "Slot date: Monday 17th August, 11:00am to 3:00pm"
SLOT_RECEIPT_RE = re.compile(
    r"Slot\s+date:\s*"
    r"(?P<weekday>Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Z][a-z]+)"
    r",\s*"
    r"(?P<start>\d{1,2}(?::\d{2})?(?:am|pm))\s*(?:-|to)\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?(?:am|pm))",
    re.IGNORECASE,
)

ORDER_RE = re.compile(r"Order\s+number[:\s]+(\d+)", re.IGNORECASE)
ORDER_SUBJECT_RE = re.compile(r"order\s+(\d+)", re.IGNORECASE)

PAYMENT_RECEIVED_RE = re.compile(
    r"Payment\s+received[:\s]+£\s*([0-9]+(?:\.[0-9]{2})?)", re.IGNORECASE
)
ESTIMATED_TOTAL_RE = re.compile(
    r"Estimated\s+total\s*£\s*([0-9]+(?:\.[0-9]{2})?)", re.IGNORECASE
)

# "We'll take payment for your order on Tuesday, 19 May"
PAYMENT_DATE_RE = re.compile(
    r"take\s+payment[^.]*?on\s+"
    r"(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)?,?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)",
    re.IGNORECASE,
)

ADDRESS_RE = re.compile(
    r"(?:Delivery\s+address|Address):\s*(?P<address>.+?)\s+"
    r"(?P<postcode>" + POSTCODE_RE + r")",
    re.IGNORECASE | re.DOTALL,
)


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


def parse_clock(time_str: str) -> tuple[int, int]:
    """Parse "11am", "11:30am", "1:07pm" into (hour, minute)."""
    s = time_str.strip().lower()
    suffix = s[-2:]
    core = s[:-2]
    if ":" in core:
        h, m = core.split(":")
    else:
        h, m = core, "0"
    hour = int(h)
    minute = int(m)
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return hour, minute


def resolve_year(message_date: datetime | None, day: int, month: int) -> int:
    """Pick the year that places the slot closest to the message date."""
    if message_date is None:
        return datetime.now(UTC).year
    candidates = [
        datetime(message_date.year - 1, month, day),
        datetime(message_date.year, month, day),
        datetime(message_date.year + 1, month, day),
    ]
    ref = message_date.replace(tzinfo=None)
    candidates.sort(key=lambda d: abs((d - ref).days))
    return candidates[0].year


def _slot_datetimes(
    day: int, month: int, start: str, end: str, ref: datetime | None
) -> tuple[datetime, datetime]:
    year = resolve_year(ref, day, month)
    start_h, start_m = parse_clock(start)
    end_h, end_m = parse_clock(end)
    dtstart = datetime(year, month, day, start_h, start_m)
    dtend = datetime(year, month, day, end_h, end_m)
    if dtend < dtstart:
        dtend += timedelta(days=1)
    return dtstart, dtend


def _month_number(name: str) -> int | None:
    return MONTHS.get(name.lower())


def _make_reservation(
    order_id: str | None,
    dtstart: datetime,
    dtend: datetime,
    postcode: str | None,
) -> dict:
    location: dict = {"@type": "Place"}
    if postcode:
        location["address"] = postcode
    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Sainsbury's delivery",
            "startDate": dtstart.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDate": dtend.strftime("%Y-%m-%dT%H:%M:%S"),
            "location": location,
        },
    }
    if order_id:
        reservation["reservationNumber"] = f"sainsburys-{order_id}"
    return reservation


def handle_delivery_slot(mail: Mail) -> bool:
    if not mail.html:
        return False
    text = strip_html(mail.html)
    slot = SLOT_WITH_POSTCODE_RE.search(text)
    if not slot:
        return False
    month = _month_number(slot.group("month"))
    if month is None:
        return False
    day = int(slot.group("day"))
    dtstart, dtend = _slot_datetimes(
        day, month, slot.group("start"), slot.group("end"), mail.date
    )
    order = ORDER_RE.search(text)
    order_id = order.group(1) if order else None
    reservation = _make_reservation(
        order_id, dtstart, dtend, slot.group("postcode").strip()
    )
    slug = order_id or dtstart.date().isoformat()
    Path(f"sainsburys-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return True


def _payment_due_date(
    text: str, message_date: datetime | None, dtstart: datetime | None
) -> datetime | None:
    m = PAYMENT_DATE_RE.search(text)
    if m:
        month = _month_number(m.group(2))
        if month is not None:
            day = int(m.group(1))
            year = resolve_year(message_date, day, month)
            return datetime(year, month, day)
    return dtstart


def handle_order_confirmation(mail: Mail) -> bool:
    if not mail.html:
        return False
    text = strip_html(mail.html)

    subject_match = ORDER_SUBJECT_RE.search(mail.subject or "")
    order_id = subject_match.group(1) if subject_match else None
    if not order_id:
        body_match = ORDER_RE.search(text)
        order_id = body_match.group(1) if body_match else None
    if not order_id:
        return False

    slot = SLOT_ORDER_RE.search(text)
    postcode = None
    dtstart = dtend = None
    if slot:
        month = _month_number(slot.group("month"))
        if month is not None:
            day = int(slot.group("day"))
            dtstart, dtend = _slot_datetimes(
                day, month, slot.group("start"), slot.group("end"), mail.date
            )
        addr = ADDRESS_RE.search(text)
        if addr:
            postcode = addr.group("postcode").strip()

    if dtstart and dtend:
        reservation = _make_reservation(order_id, dtstart, dtend, postcode)
        Path(f"sainsburys-{order_id}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    total_match = ESTIMATED_TOTAL_RE.search(text)
    if total_match:
        bill: dict = {
            "@context": "https://schema.org",
            "@type": "Invoice",
            "payee": "Sainsbury's",
            "invoiceNumber": f"sainsburys-{order_id}",
            "totalPaymentDue": {
                "@type": "PriceSpecification",
                "price": float(total_match.group(1)),
                "priceCurrency": "GBP",
            },
        }
        due_date = _payment_due_date(text, mail.date, dtstart)
        if due_date is not None:
            bill["paymentDueDate"] = due_date.strftime("%Y-%m-%d")
        Path(f"sainsburys-{order_id}.bill.json").write_text(
            json.dumps(bill, ensure_ascii=False), encoding="utf-8"
        )

    return True


def handle_receipt(mail: Mail) -> bool:
    text = mail.text
    if not text:
        return False

    subject_match = ORDER_SUBJECT_RE.search(mail.subject or "")
    order_id = subject_match.group(1) if subject_match else None
    if not order_id:
        body_match = ORDER_RE.search(text)
        order_id = body_match.group(1) if body_match else None
    if not order_id:
        return False

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "orderNumber": f"sainsburys-{order_id}",
        "merchant": "Sainsbury's",
    }

    payment = PAYMENT_RECEIVED_RE.search(text)
    if payment:
        receipt["priceSpecification"] = {
            "@type": "PriceSpecification",
            "price": float(payment.group(1)),
            "priceCurrency": "GBP",
        }

    slot = SLOT_RECEIPT_RE.search(text)
    if slot:
        month = _month_number(slot.group("month"))
        if month is not None:
            day = int(slot.group("day"))
            dtstart, _ = _slot_datetimes(
                day, month, slot.group("start"), slot.group("end"), mail.date
            )
            receipt["orderDate"] = dtstart.strftime("%Y-%m-%d")

    Path(f"sainsburys-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return True


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").lower()

    if "receipt for your" in subject and "order" in subject:
        handle_receipt(mail)
    elif "thanks for your order" in subject:
        handle_order_confirmation(mail)
    else:
        handle_delivery_slot(mail)

    return 0


if __name__ == "__main__":
    sys.exit(main())
