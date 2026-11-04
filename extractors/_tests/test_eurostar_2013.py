"""Tests for the 2013-2016 Eurostar confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def reservation(
    slug: str,
    route: tuple[str, str],
    times: tuple[str, str],
    seat: tuple[str, str],
) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": slug,
        "mailsift:itineraryComplete": True,
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": route[0]},
            "arrivalStation": {"@type": "TrainStation", "name": route[1]},
            "departureTime": times[0],
            "arrivalTime": times[1],
        },
        "ticketedSeat": {
            "@type": "Seat",
            "seatSection": seat[0],
            "seatNumber": seat[1],
        },
    }


def test_one_return_booking_per_passenger(run_extractor):
    out = run_extractor("eurostar-2013", "eurostar-2013-two-bookings.eml")
    there = ("Beta Midi", "Alpha International")
    back = ("Alpha International", "Beta Midi")
    out_times = ("2046-10-05T16:56:00", "2046-10-05T18:06:00")
    back_times = ("2046-10-08T10:58:00", "2046-10-08T14:05:00")
    assert out == {
        "eurostar-NNNNNN-outbound.reservation.json": reservation(
            "eurostar-NNNNNN-outbound", there, out_times, ("9", "13")
        ),
        "eurostar-NNNNNN-return.reservation.json": reservation(
            "eurostar-NNNNNN-return", back, back_times, ("9", "13")
        ),
        "eurostar-PPPPPP-outbound.reservation.json": reservation(
            "eurostar-PPPPPP-outbound", there, out_times, ("9", "14")
        ),
        "eurostar-PPPPPP-return.reservation.json": reservation(
            "eurostar-PPPPPP-return", back, back_times, ("9", "14")
        ),
    }


def test_exchange_into_the_next_year(run_extractor):
    out = run_extractor("eurostar-2013", "eurostar-2013-exchange.eml")
    assert out == {
        "eurostar-QQQQQQ-outbound.reservation.json": reservation(
            "eurostar-QQQQQQ-outbound",
            ("Alpha International", "Beta Midi"),
            ("2047-01-31T08:55:00", "2047-01-31T12:05:00"),
            ("3", "76"),
        ),
    }


def _subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "eurostar-2013.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError(f"{manifest.name} has no subject_regex")


@pytest.mark.parametrize(
    ("subject", "matches"),
    [
        ("Your Eurostar booking confirmation Tue 5th Nov 2043 - QQQQQQ", True),
        ("Your Eurostar booking confirmation Fri 2nd Oct 2046 - NNNNNN,PPPPPP", True),
        ("Your Eurostar exchange confirmation Fri 10th Apr 2045 - QQQQQQ", True),
        ("Your Eurostar booking confirmation Fri, 1 February - QQQQQQ", False),
        ("Your Eurostar exchange confirmation Fri, 29 December - QQQQQQ", False),
        ("Eurostar - Your mobile booking confirmation - QQQQQQ", False),
        ("Fwd: Your Eurostar booking confirmation Tue 5th Nov 2043 - QQQQQQ", False),
    ],
)
def test_manifest_subject(subject, matches):
    assert bool(_subject_regex().search(subject)) == matches
