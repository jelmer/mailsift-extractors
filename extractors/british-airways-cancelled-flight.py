#!/usr/bin/env python3
"""British Airways "Your BA491 flight ... has been cancelled" mails.

When BA cancels a flight it rebooks the passenger onto another one
and mails both, side by side, under "Your old flight details" and
"Your new flight details". The mail is HTML only. Each flight block
holds `<p>` elements in a fixed order (`DEPARTS`, date, airport,
`ARRIVES`, date, airport, then the departure and arrival terminals,
blank when there is none); the times sit in table cells between them.

The old flight is emitted as `ReservationCancelled`, under the same
slug and flight number the e-ticket receipt used, so it replaces that
leg. The new flight is emitted as `ReservationPending`: BA asks the
passenger to accept it in Manage My Booking, or pick another flight
or a refund, and no mail confirms the choice. Neither leg carries
`mailsift:itineraryComplete`, since the mail only shows the one
flight.

The template hides the new flight block when BA couldn't rebook; that
variant hasn't been seen, so it fails rather than guessing.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, read_message, strip_html

SUBJECT_RE = re.compile(r"^Your (BA ?\d{1,4}) flight to .+ has been cancelled$")
BOOKING_RE = re.compile(r"Booking Reference:\s*([A-Z0-9]{5,8})\b")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
FLIGHT_NO_RE = re.compile(r">\s*(BA ?\d{1,4})\s*<")
P_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
TIME_RE = re.compile(r">\s*(\d{1,2}:\d{2})\s*<")
CABIN_RE = re.compile(r'class="flight-cabin"[^>]*>(.*?)</td>', re.DOTALL)

OLD_HEADING = "Your old flight details"
NEW_HEADING = "Your new flight details"
END_HEADING = "Traveller names"


def airport(name: str, terminal: str) -> dict:
    out = {"@type": "Airport", "name": name}
    if terminal:
        out["alternateName"] = terminal
    return out


def parse_flight(block: str) -> tuple[str, dict]:
    """Return the `BAnnnn` code and the schema.org `Flight` in `block`."""
    flight_no = FLIGHT_NO_RE.search(block)
    if not flight_no:
        raise ValueError("flight block without a flight number")
    code = flight_no.group(1).replace(" ", "")
    paras = [strip_html(p) for p in P_RE.findall(block)]
    if len(paras) != 8 or paras[0] != "DEPARTS" or paras[3] != "ARRIVES":
        raise ValueError(f"{code}: unexpected flight details {paras!r}")
    times = TIME_RE.findall(block)
    if len(times) != 2:
        raise ValueError(f"{code}: expected 2 times, got {times!r}")
    dep_date, dep_place, _, arr_date, arr_place, dep_term, arr_term = paras[1:]
    flight: dict = {
        "@type": "Flight",
        "flightNumber": code[2:].lstrip("0") or "0",
        "airline": {
            "@type": "Airline",
            "iataCode": "BA",
            "name": "British Airways",
        },
        "departureAirport": airport(dep_place, dep_term),
        "arrivalAirport": airport(arr_place, arr_term),
        "departureTime": parse_dt(dep_date, times[0]),
        "arrivalTime": parse_dt(arr_date, times[1]),
    }
    cabin = CABIN_RE.search(block)
    if cabin and (name := strip_html(cabin.group(1))):
        flight["pending:cabinClass"] = name
    return code, flight


def parse_dt(date_str: str, time_str: str) -> str:
    dt = datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def section(html: str, start: str, end: str) -> str:
    begin = html.find(start)
    finish = html.find(end, begin)
    if begin < 0 or finish < 0:
        raise ValueError(f"no {start!r} section")
    return html[begin + len(start) : finish]


def write_leg(booking_code: str, code: str, flight: dict, status: str) -> None:
    reservation = {
        "@context": {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        },
        "@type": "FlightReservation",
        "reservationNumber": booking_code,
        "reservationStatus": status,
        "reservationFor": flight,
    }
    # BA's receipts pad the flight number to four digits; match their slug.
    slug = f"ba-{booking_code}-BA{code[2:].zfill(4)}"
    Path(f"{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )


def extract(mail: Mail) -> int:
    subject = SUBJECT_RE.match(mail.subject or "")
    if not subject:
        return 0
    if not mail.html:
        raise ValueError("no HTML part")
    html = COMMENT_RE.sub("", mail.html)
    booking = BOOKING_RE.search(strip_html(html))
    if not booking:
        raise ValueError("no booking reference")
    booking_code = booking.group(1)

    old_code, old_flight = parse_flight(section(html, OLD_HEADING, NEW_HEADING))
    new_code, new_flight = parse_flight(section(html, NEW_HEADING, END_HEADING))
    if old_code != subject.group(1).replace(" ", ""):
        raise ValueError(f"subject names {subject.group(1)}, mail {old_code}")
    if old_code == new_code:
        raise ValueError(f"{old_code} rebooked onto itself")
    write_leg(booking_code, old_code, old_flight, "ReservationCancelled")
    write_leg(booking_code, new_code, new_flight, "ReservationPending")
    return 0


def main() -> int:
    return extract(read_message())


if __name__ == "__main__":
    sys.exit(main())
