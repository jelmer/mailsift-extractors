"""Tests for the 2018-2023 Eurostar booking and exchange confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_lists_both_journeys(run_extractor):
    # The outbound was travelled before the exchange: its date, with no
    # year, lies before the mail's.
    out = run_extractor("eurostar-legacy-exchange", "eurostar-legacy-exchange.eml")
    assert out == {
        "eurostar-KKKKKK-outbound.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-KKKKKK-outbound",
            "mailsift:itineraryComplete": True,
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "Eurostar"},
                "departureStation": {"@type": "TrainStation", "name": "Beta Central"},
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": "Alpha International",
                },
                "departureTime": "2045-12-29T17:28:00",
                "arrivalTime": "2045-12-29T20:00:00",
            },
            "ticketedSeat": {"@type": "Seat", "seatSection": "11", "seatNumber": "43"},
        },
        "eurostar-KKKKKK-return.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-KKKKKK-return",
            "mailsift:itineraryComplete": True,
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "Eurostar"},
                "departureStation": {
                    "@type": "TrainStation",
                    "name": "Alpha International",
                },
                "arrivalStation": {"@type": "TrainStation", "name": "Beta Central"},
                "departureTime": "2046-03-21T06:16:00",
                "arrivalTime": "2046-03-21T10:32:00",
            },
            "ticketedSeat": {"@type": "Seat", "seatSection": "4", "seatNumber": "62"},
        },
    }


def _reservation(slug: str, trip: dict, coach: str, seat: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": slug,
        "mailsift:itineraryComplete": True,
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            **trip,
        },
        "ticketedSeat": {"@type": "Seat", "seatSection": coach, "seatNumber": seat},
    }


def _station(name: str) -> dict:
    return {"@type": "TrainStation", "name": name}


def test_booking_confirmation(run_extractor):
    # Both journeys change trains on the way; the seat is the first
    # passenger's.
    out = run_extractor("eurostar-legacy-exchange", "eurostar-legacy-booking.eml")
    assert out == {
        "eurostar-LLLLLL-outbound.reservation.json": _reservation(
            "eurostar-LLLLLL-outbound",
            {
                "departureStation": _station("Alpha International"),
                "arrivalStation": _station("Delta Station"),
                "departureTime": "2046-06-29T17:01:00",
                "arrivalTime": "2046-06-29T23:41:00",
            },
            "11",
            "63",
        ),
        "eurostar-LLLLLL-return.reservation.json": _reservation(
            "eurostar-LLLLLL-return",
            {
                "departureStation": _station("Delta Station"),
                "arrivalStation": _station("Alpha International"),
                "departureTime": "2046-07-01T17:17:00",
                "arrivalTime": "2046-07-01T22:00:00",
            },
            "13",
            "78",
        ),
    }


def test_one_way_booking_without_direction_header(run_extractor):
    out = run_extractor(
        "eurostar-legacy-exchange", "eurostar-legacy-booking-one-way.eml"
    )
    assert out == {
        "eurostar-MMMMMM-outbound.reservation.json": _reservation(
            "eurostar-MMMMMM-outbound",
            {
                "departureStation": _station("Alpha International"),
                "arrivalStation": _station("Epsilon Central"),
                "departureTime": "2047-09-15T11:04:00",
                "arrivalTime": "2047-09-15T16:11:00",
            },
            "1",
            "14",
        ),
    }


def _subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "eurostar-legacy-exchange.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError(f"{manifest.name} has no subject_regex")


@pytest.mark.parametrize(
    ("subject", "matches"),
    [
        ("Your Eurostar exchange confirmation Fri, 29 December - KKKKKK", True),
        ("Your Eurostar exchange confirmation Fri, 1 February - KKKKKK", True),
        # The 2015 layout, which this extractor can't parse.
        ("Your Eurostar exchange confirmation Fri 10th Apr 2045 - KKKKKK", False),
        ("Your exchange confirmation | Sunday, 6 July 2045 - Reference: KKKKKK", False),
        ("Your Eurostar booking confirmation Fri, 1 February - KKKKKK", True),
        ("Your Eurostar booking confirmation Fri 3rd Feb 2045 - KKKKKK", False),
        (
            "Booking confirmation - please print tickets | Tue, 15 September - KKKKKK",
            True,
        ),
        (
            "Booking confirmation - here's a link to your tickets | Sat, 11 May - KKKKKK",
            True,
        ),
        (
            "Booking confirmation - here\u2019s a link to your tickets | Fri, 3 May - KKKKKK",
            True,
        ),
        ("Booking confirmation | Monday, 30 October - Reference: KKKKKK", False),
        ("Fwd: Your Eurostar booking confirmation Fri, 1 February - KKKKKK", False),
    ],
)
def test_manifest_subject(subject, matches):
    assert bool(_subject_regex().search(subject)) == matches
