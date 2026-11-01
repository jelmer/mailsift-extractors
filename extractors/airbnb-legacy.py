#!/usr/bin/env python3
"""Airbnb reservation mail from before schema.org markup (2013-2018).

Three shapes, none of which carry JSON-LD:

- "Reservation Confirmed - <host>" (2013): the guest's own
  confirmation. HTML only; the listing name and a multi-line address
  follow the "Guests" count.
- "Reservation Itinerary from <guest>" (2015-2018): an itinerary
  someone shared with us. The text part has the dates and a one-line
  address; the 2017-era HTML adds check-in and check-out hours but
  drops the address, so we read both.
- "Billing receipt for reservation" (2013): emitted as a receipt
  keyed on the receipt number, like the modern `airbnb` extractor.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, normalize_unicode, read_message, strip_html

CONFIRMATION_RE = re.compile(r"Confirmation Code:\s*([A-Z0-9]{5,12})\b", re.IGNORECASE)
RECEIPT_RE = re.compile(r"^Receipt #\s*(\d+)$")
HELLO_RE = re.compile(r"^Hello (.+),$")
CLOCK_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AP]M)\b", re.IGNORECASE)
TRAILING_POSTCODE_RE = re.compile(r"^(.*?)(\s*(\d[\d-]*))?$")
AMOUNT_RE = re.compile(r"^(?P<symbol>[€£])\s*(?P<amount>[0-9,]+(?:\.[0-9]{2})?)$")
CURRENCIES = {"€": "EUR", "£": "GBP"}

DATE_FORMATS = [
    "%a, %B %d, %Y",  # "Wed, March 06, 2013"
    "%a, %d %B, %Y",  # "Fri, 26 January, 2018"
    "%B %d, %Y",  # "August 08, 2015"
    "%d %B, %Y",  # "26 January, 2018"
]


def to_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_date(s: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {s!r}")


def with_clock(date: datetime, line: str | None) -> str:
    """Add the hour from "Check-in is anytime after 3PM" / "10AM"."""
    m = CLOCK_RE.search(line or "")
    if not m:
        return date.strftime("%Y-%m-%d")
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
    return date.replace(hour=hour, minute=int(m.group(2) or 0)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def address_from_lines(lines: list[str]) -> dict | None:
    """'<street>' ... '<town>, <postcode>' '<country>' (2013 layout)."""
    for i in range(1, len(lines)):
        if not re.search(r"[\d,]", lines[i]) and "," in lines[i - 1]:
            town, _, postcode = lines[i - 1].partition(",")
            address: dict = {"@type": "PostalAddress"}
            if i > 1:
                address["streetAddress"] = ", ".join(lines[: i - 1])
            address["addressLocality"] = town.strip()
            if postcode.strip():
                address["postalCode"] = postcode.strip()
            address["addressCountry"] = lines[i]
            return address
    return None


def address_from_line(line: str) -> dict:
    """'18 Example Place, Forest Lodge, NSW 2037, Australia'.

    The town is the last comma-separated part before the country that
    still has words in it once a trailing postcode is cut off; bare
    postcodes and state abbreviations after it are split out.
    """
    parts = [p.strip() for p in line.split(",") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"unrecognised address {line!r}")
    street = locality = region = postcode = None
    for i in range(len(parts) - 2, -1, -1):
        m = TRAILING_POSTCODE_RE.match(parts[i])
        assert m is not None  # every string matches
        name, _, code = m.groups()
        postcode = postcode or code
        if re.fullmatch(r"[A-Z]{2,3}", name):
            region = name
        elif name:
            street = ", ".join(parts[:i]) or None
            locality = name
            break
    address: dict = {"@type": "PostalAddress"}
    for key, value in [
        ("streetAddress", street),
        ("addressLocality", locality),
        ("addressRegion", region),
        ("postalCode", postcode),
        ("addressCountry", parts[-1]),
    ]:
        if value:
            address[key] = value
    return address


def reservation(
    code: str,
    checkin: str,
    checkout: str,
    listing: str,
    address: dict | None,
    guest: str | None,
) -> dict:
    out: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": code,
        "checkinTime": checkin,
        "checkoutTime": checkout,
        "reservationFor": {"@type": "LodgingBusiness", "name": listing},
    }
    if address:
        out["reservationFor"]["address"] = address
    if guest:
        out["underName"] = {"@type": "Person", "name": guest}
    return out


def confirmed(mail: Mail, lines: list[str]) -> dict:
    # Values precede their labels here: "<date>", "<hours>", "Check In".
    ci = lines.index("Check In")
    co = lines.index("Check Out")
    g = next(i for i in range(co, len(lines)) if re.fullmatch(r"Guests?", lines[i]))
    # The host's name, phone and email follow the country; stop there.
    address = address_from_lines(lines[g + 2 : g + 8])
    m = next(filter(None, (HELLO_RE.match(line) for line in lines)), None)
    return reservation(
        code=confirmation_code(lines),
        checkin=with_clock(parse_date(lines[ci - 2]), lines[ci - 1]),
        checkout=with_clock(parse_date(lines[co - 2]), lines[co - 1]),
        listing=lines[g + 1],
        address=address,
        guest=m.group(1) if m else None,
    )


def itinerary(mail: Mail, lines: list[str]) -> dict:
    if not mail.text:
        raise ValueError("itinerary without a text part")
    text = to_lines(normalize_unicode(mail.text))
    ci = next(i for i, line in enumerate(text) if line.startswith("* Check In "))
    co = next(i for i, line in enumerate(text) if line.startswith("* Check Out "))
    g = next(i for i, line in enumerate(text) if re.fullmatch(r"\* \d+ Guests?", line))
    # Listing name, host name, address.
    listing, address = text[g + 1], text[g + 3]

    # The 2017-era HTML follows each date with the hours.
    def hours(label: str) -> str | None:
        if label in lines:
            i = lines.index(label)
            return lines[i + 2] if i + 2 < len(lines) else None
        return None

    guest = re.sub(
        r"^Reservation Itinerary from ", "", mail.subject or "", flags=re.IGNORECASE
    )
    return reservation(
        code=confirmation_code(text),
        checkin=with_clock(
            parse_date(text[ci][len("* Check In ") :]), hours("Check In")
        ),
        checkout=with_clock(
            parse_date(text[co][len("* Check Out ") :]), hours("Check Out")
        ),
        listing=listing,
        address=address_from_line(address),
        guest=guest.strip() or None,
    )


def confirmation_code(lines: list[str]) -> str:
    for line in lines:
        m = CONFIRMATION_RE.search(line)
        if m:
            return m.group(1)
    raise ValueError("no confirmation code")


def receipt(mail: Mail, lines: list[str]) -> dict:
    number = next(m.group(1) for line in lines if (m := RECEIPT_RE.match(line)))
    t = lines.index("Total")
    m = AMOUNT_RE.match(lines[t + 1])
    if not m:
        raise ValueError(f"unrecognised total {lines[t + 1]!r}")
    currency = CURRENCIES.get(m.group("symbol"))
    if currency is None:
        raise ValueError(f"unknown currency symbol {m.group('symbol')!r}")
    out: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Airbnb",
        "orderNumber": number,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(m.group("amount").replace(",", "")),
            "priceCurrency": currency,
        },
        "confirmationNumber": confirmation_code(lines),
    }
    if mail.date:
        out["orderDate"] = mail.date.strftime("%Y-%m-%d")
    return out


def main() -> int:
    mail = read_message()
    if not mail.html or mail.ld_json:
        # With JSON-LD the schema-ld extractor already has it.
        return 0
    subject = (mail.subject or "").strip().lower()
    lines = to_lines(strip_html(mail.html, block_tags=True))

    if subject.startswith("billing receipt"):
        order = receipt(mail, lines)
        Path(f"airbnb-{order['orderNumber']}.receipt.json").write_text(
            json.dumps(order, ensure_ascii=False), encoding="utf-8"
        )
        return 0
    if subject.startswith("reservation confirmed"):
        res = confirmed(mail, lines)
    elif subject.startswith("reservation itinerary"):
        res = itinerary(mail, lines)
    else:
        return 0
    Path(f"airbnb-{res['reservationNumber']}.reservation.json").write_text(
        json.dumps(res, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
