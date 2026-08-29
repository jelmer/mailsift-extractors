#!/usr/bin/env python3
"""DICE (dice.fm) event ticket purchase confirmations.

Sent from `noreply@dice.fm` (via Mandrill) with a subject that starts
with `Your tickets:`. There's no schema.org markup, but the HTML body
lays out a stable "Ticket details" block after HTML-stripping:

    Ticket details

    Ticket type
    General Admission
    Quantity
    1
    Venue
    The Underworld
    174 Camden High St, London NW1 0NE
    Date & time
    Thu 14 Mar, 7:00 PM GMT
    Name on ticket
    Jelmer Vernooij
    Total price
    ...

DICE never includes the year in the `Date & time` line; we resolve it
by picking the earliest matching weekday+day+month on or after the
`Date:` header. The View-tickets link (`link.dice.fm/<id>`) is the
stablest identifier we get, so we use it as `reservationNumber`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

ORDER_LINK_RE = re.compile(r"link\.dice\.fm/([A-Za-z0-9]+)")
EVENT_LINK_RE = re.compile(r"dice\.fm/event/([A-Za-z0-9-]+)")

# The block sits under a "Ticket details" heading and repeats
# label/value pairs on alternating lines. We match on the labels we
# care about and take the next non-empty line as the value.
BLOCK_HEAD_RE = re.compile(r"^\s*Ticket details\s*$", re.MULTILINE)

DATE_TIME_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]{2})\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<mon>[A-Z][a-z]{2}),\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<ampm>AM|PM)?\s*"
    r"(?P<tz>[A-Z]{2,5})?\s*$"
)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(body: str) -> str:
    p = _Strip()
    p.feed(body)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def event_name_from_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    m = re.match(r"^\s*Your tickets:\s*(.+?)\s*$", subject)
    return m.group(1) if m else None


def next_value(lines: list[str], index: int) -> str | None:
    """Return the next non-empty line strictly after `index`."""
    for i in range(index + 1, len(lines)):
        candidate = lines[i].strip()
        if candidate:
            return candidate
    return None


def resolve_year(
    wday: str, day: int, month: int, hour: int, minute: int, reference: datetime
) -> datetime | None:
    """Pick the first year on or after `reference` where the given
    (weekday, day, month) date exists and the weekday matches.

    DICE omits the year on the ticket-details line so we ground it on
    the mail's `Date:` header. We try up to five years forward in case
    of very late-sent confirmations for far-future events.
    """
    weekday_index = {
        "Mon": 0,
        "Tue": 1,
        "Wed": 2,
        "Thu": 3,
        "Fri": 4,
        "Sat": 5,
        "Sun": 6,
    }.get(wday)
    if weekday_index is None:
        return None
    for year in range(reference.year, reference.year + 6):
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        if candidate.weekday() != weekday_index:
            continue
        # Give a one-day grace so a message sent a few hours after
        # midnight for an event later that same day still resolves.
        if candidate >= reference - timedelta(days=1):
            return candidate
    return None


MONTHS = {
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


def parse_datetime(value: str, reference: datetime | None) -> datetime | None:
    m = DATE_TIME_RE.match(value.strip())
    if not m:
        return None
    hour = int(m.group("hour"))
    minute = int(m.group("minute"))
    ampm = m.group("ampm")
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    month = MONTHS.get(m.group("mon"))
    if month is None:
        return None
    day = int(m.group("day"))
    ref = reference or datetime.now(UTC)
    ref_naive = ref.replace(tzinfo=None)
    return resolve_year(m.group("wday"), day, month, hour, minute, ref_naive)


def slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]+", "-", value).strip("-")
    return cleaned or fallback


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)
    lines = text.split("\n")

    # Anchor the parse on the "Ticket details" heading; everything above
    # it is boilerplate, everything below it is the label/value pairs
    # we care about. If we can't find the anchor, this isn't a purchase
    # confirmation (e.g. it's a "Login code:" or "Waiting List:" mail).
    body_start = None
    for index, line in enumerate(lines):
        if BLOCK_HEAD_RE.match(line):
            body_start = index
            break
    if body_start is None:
        return 0

    ticket_type = None
    quantity = None
    venue_name = None
    venue_address = None
    date_time_raw = None
    total_price_raw = None

    for index in range(body_start, len(lines)):
        stripped = lines[index].strip()
        if stripped == "Ticket type":
            ticket_type = next_value(lines, index)
        elif stripped == "Quantity":
            candidate = next_value(lines, index)
            if candidate and candidate.isdigit():
                quantity = int(candidate)
        elif stripped == "Venue":
            venue_name = next_value(lines, index)
            # The address is on the line after the venue name.
            if venue_name:
                for j in range(index + 1, len(lines)):
                    if lines[j].strip() == venue_name:
                        venue_address = next_value(lines, j)
                        break
        elif stripped == "Date & time":
            date_time_raw = next_value(lines, index)
        elif stripped == "Total price":
            total_price_raw = next_value(lines, index)

    if not date_time_raw or not venue_name:
        return 0

    start_dt = parse_datetime(date_time_raw, mail.date)
    if start_dt is None:
        return 0

    event_name = event_name_from_subject(mail.subject) or venue_name

    order_id = None
    if (m := ORDER_LINK_RE.search(mail.html)) is not None:
        order_id = m.group(1)

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": event_name,
            "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "location": {
                "@type": "Place",
                "name": venue_name,
            },
        },
        "provider": {"@type": "Organization", "name": "DICE"},
    }
    if venue_address:
        reservation["reservationFor"]["location"]["address"] = venue_address
    if order_id:
        reservation["reservationNumber"] = f"dice-{order_id}"
    if ticket_type or quantity is not None:
        ticket: dict = {"@type": "Ticket"}
        if ticket_type:
            ticket["ticketToken"] = ticket_type
        if quantity is not None:
            reservation["numSeats"] = quantity
        reservation["reservedTicket"] = ticket
    if total_price_raw:
        currency = None
        amount = None
        m = re.match(r"^\s*([£$€])\s*(\d+(?:[.,]\d{1,2})?)\s*$", total_price_raw)
        if m:
            currency = {"£": "GBP", "$": "USD", "€": "EUR"}.get(m.group(1))
            amount = float(m.group(2).replace(",", "."))
        if currency and amount is not None:
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": amount,
                "priceCurrency": currency,
            }

    slug_basis = order_id or event_name
    slug = slugify(slug_basis, fallback="dice")
    Path(f"dice-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
