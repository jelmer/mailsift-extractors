"""Tests for the 2019-2023 Eurostar exchange confirmation extractor."""

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
        ("Your Eurostar booking confirmation Fri, 1 February - KKKKKK", False),
    ],
)
def test_manifest_subject(subject, matches):
    assert bool(_subject_regex().search(subject)) == matches
