#!/usr/bin/env python3
"""easyJet flight booking confirmations.

Two body layouts in the wild:

Modern (post-2014-ish):

    <N> of <M> <Origin> to <Destination> <FLIGHTNUM>
    Departs: <Day DD Mon YYYY HH:MM>
    Arrives: <Day DD Mon YYYY HH:MM>

Legacy (pre-2014):

    <Origin> to <Destination>
    Dep <DD Month YYYY HH:MM>
    Arr <DD Month YYYY HH:MM>
    Flight <NUMBER>

We emit one FlightReservation per leg, keyed off the booking reference
+ flight number so a "your flight has been moved" update overwrites the
existing event rather than creating a duplicate.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

REFERENCE_RE = re.compile(r"easyJet booking reference:?\s*([A-Z0-9]+)", re.IGNORECASE)

LEG_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s+([A-Z][A-Za-z .'-]+?)\s+to\s+([A-Z][A-Za-z .'-]+?)\s+"
    r"(EZ[YS]?\d+)\s+"
    r"Departs:\s+([A-Z][a-z]+\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,2}:\d{2})\s+"
    r"Arrives:\s+([A-Z][a-z]+\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,2}:\d{2})"
)

# Legacy pre-2014 body layout. No `N of M`, no `EZY` prefix on the
# flight number, dates written out as `25 October 2013 18:55` rather
# than `Fri 25 Oct 2013 18:55`. We locate each leg by the
# fixed-shape trailing block (`Dep <date> Arr <date> Flight <num>`)
# and fish the `<origin> to <destination>` pair out of the tokens
# immediately preceding it - the origin can't be anchored on the
# left because the intro paragraph flows straight into it on the
# first leg.
_LEGACY_DATE = r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,2}:\d{2}"
LEGACY_TRAIL_RE = re.compile(
    rf"Dep\s+({_LEGACY_DATE})\s+Arr\s+({_LEGACY_DATE})\s+Flight\s+(\d+)"
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


def parse_dt(s: str) -> datetime | None:
    # Modern (`Fri 12 Jul 2024 18:45`) and legacy
    # (`25 October 2013 18:55`) formats both.
    s = s.strip()
    for fmt in ("%a %d %b %Y %H:%M", "%d %B %Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def modern_legs(text: str) -> list[tuple]:
    """(origin, dest, flight_no_with_prefix, dep_str, arr_str) per
    leg, for the modern body layout."""
    return [
        (m.group(3), m.group(4), m.group(5), m.group(6), m.group(7))
        for m in LEG_RE.finditer(text)
    ]


def legacy_legs(text: str) -> list[tuple]:
    """Same shape as `modern_legs` but for the pre-2014 layout.

    Legacy bodies use a bare flight number (`Flight 2163`) with no
    airline prefix; we synthesise `EZY<num>` so the downstream
    reservation key is stable across the two formats.

    Origin/destination are lifted from the tokens immediately
    preceding each `Dep <date>` marker rather than from a single
    left-to-right regex: on the first leg the intro paragraph
    flows straight into the origin word with no boundary we can
    anchor on.
    """
    legs = []
    for m in LEGACY_TRAIL_RE.finditer(text):
        dep_s, arr_s, num = m.group(1), m.group(2), m.group(3)
        # Bound the search left of `Dep` to 120 chars, then cut at
        # any easyJet label (`Passengers`, `Seats`, `Bag drop`,
        # `Select seats`, ...) so noise between legs doesn't leak
        # into origin.
        preceding = text[max(0, m.start() - 120) : m.start()]
        preceding = _trim_prefix_at_labels(preceding)
        pair = _legacy_endpoints(preceding)
        if pair is None:
            continue
        origin, dest = pair
        legs.append((origin, dest, f"EZY{num}", dep_s, arr_s))
    return legs


# easyJet labels that sit between legs in the legacy layout. Cut
# the preceding search window at the last of these so only the
# actual `<origin> to <destination>` phrase remains.
_INTER_LEG_LABEL_RE = re.compile(
    r"(?:Passengers|Bag drop [a-z]+|Seats(?:\s+Automatically\s+Allocated)?"
    r"|Select seats|Check in [a-z]+)\b"
)


def _trim_prefix_at_labels(prefix: str) -> str:
    matches = list(_INTER_LEG_LABEL_RE.finditer(prefix))
    if not matches:
        return prefix
    return prefix[matches[-1].end() :]


# Airport name: 1-3 capitalised tokens or a `(Terminal N)` clause.
_AIRPORT_TOKEN = r"[A-Z][A-Za-z.'\-]*|\([^)]{1,40}\)"
_ENDPOINT_RE = re.compile(
    rf"((?:{_AIRPORT_TOKEN})(?:\s+(?:{_AIRPORT_TOKEN})){{0,2}})"
    rf"\s+to\s+"
    rf"((?:{_AIRPORT_TOKEN})(?:\s+(?:{_AIRPORT_TOKEN})){{0,2}})\s*$"
)


def _legacy_endpoints(prefix: str) -> tuple[str, str] | None:
    """Extract `(origin, destination)` from the tail of `prefix`.

    Airports are 1-3 tokens ending immediately before the `Dep`
    marker; take the last such pair to skip the intro paragraph
    that leads into it on the first leg. Trailing tokens that are
    all-uppercase (passenger names like `SURNAME`) are dropped
    since they aren't airport names.
    """
    match = _ENDPOINT_RE.search(prefix.rstrip())
    if not match:
        return None
    return _drop_passenger_names(match.group(1)), _drop_passenger_names(match.group(2))


def _drop_passenger_names(phrase: str) -> str:
    """Strip leading all-caps tokens from `phrase`.

    Passenger names in legacy easyJet bodies are rendered in ALL
    CAPS above the itinerary (`Passengers Mr FIRSTNAME SURNAME`)
    and the first-leg origin regex can't help but grab the last
    one or two of them along with the actual airport name.
    """
    tokens = phrase.split()
    while tokens and _is_all_caps(tokens[0]):
        tokens.pop(0)
    return " ".join(tokens) if tokens else phrase


def _is_all_caps(token: str) -> bool:
    """True if `token` has letters and none of them are lower-case.

    A parenthesised terminal (`(Terminal N)`) has lower-case letters
    and returns False; pure-uppercase surnames return True.
    """
    return any(c.isalpha() for c in token) and not any(c.islower() for c in token)


def extract(mail, max_message_date: datetime | None = None) -> int:
    """Walk the itinerary and emit one reservation per leg.

    `max_message_date` is a date cutoff: refuse to process any mail
    whose `Date:` header is on or after it. Used by the legacy
    extractor variant so a spoofer today can't reach the no-DKIM
    code path.
    """
    if max_message_date is not None and mail.date is not None:
        mail_naive = mail.date.replace(tzinfo=None)
        if mail_naive >= max_message_date:
            return 0

    if not mail.html:
        return 0

    text = strip_html(mail.html)

    ref_match = REFERENCE_RE.search(mail.subject or "") or REFERENCE_RE.search(text)
    if not ref_match:
        return 0
    reference = ref_match.group(1)

    legs = modern_legs(text) or legacy_legs(text)
    if not legs:
        return 0

    for origin, dest, flight_no, dep_s, arr_s in legs:
        dep = parse_dt(dep_s)
        arr = parse_dt(arr_s)
        if dep is None or arr is None:
            continue
        if arr < dep:
            continue

        # easyJet's flight number is e.g. "EZY2521". Split into airline +
        # number so the converter can render "Flight EZY2521: ..." rather
        # than just "Flight 2521".
        m = re.match(r"([A-Z]+)(\d+)", flight_no)
        if m:
            airline_code, num = m.group(1), m.group(2)
        else:
            airline_code, num = "", flight_no

        reservation = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": f"easyjet-{reference}-{flight_no}",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": num,
                "airline": {"@type": "Airline", "iataCode": airline_code},
                "departureAirport": {"@type": "Airport", "name": origin},
                "arrivalAirport": {"@type": "Airport", "name": dest},
                "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }

        slug = f"easyjet-{reference}-{flight_no}".lower()
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


def main() -> int:
    return extract(read_message())


if __name__ == "__main__":
    sys.exit(main())
