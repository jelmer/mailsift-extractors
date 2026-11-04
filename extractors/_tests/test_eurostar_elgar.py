"""Tests for the extractor of confirmations from booking.elgar@eurostar.com."""

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
    train: str,
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
            "trainNumber": train,
        },
        "ticketedSeat": {
            "@type": "Seat",
            "seatSection": seat[0],
            "seatNumber": seat[1],
        },
    }


def test_return_trip_in_the_next_year(run_extractor):
    out = run_extractor("eurostar-elgar", "eurostar-elgar-return.eml")
    assert out == {
        "eurostar-RRRRRR-outbound.reservation.json": reservation(
            "eurostar-RRRRRR-outbound",
            ("Alpha International", "Beta Midi"),
            ("2047-02-01T15:04:00", "2047-02-01T18:05:00"),
            "9140",
            ("5", "71"),
        ),
        "eurostar-RRRRRR-return.reservation.json": reservation(
            "eurostar-RRRRRR-return",
            ("Beta Midi", "Alpha International"),
            ("2047-02-03T20:22:00", "2047-02-03T21:33:00"),
            "9163",
            ("11", "21"),
        ),
    }


def test_one_way_with_two_passengers(run_extractor):
    out = run_extractor("eurostar-elgar", "eurostar-elgar-one-way.eml")
    assert out == {
        "eurostar-SSSSSS-outbound.reservation.json": reservation(
            "eurostar-SSSSSS-outbound",
            ("Alpha International", "Gamma Nord"),
            ("2045-12-14T07:55:00", "2045-12-14T11:17:00"),
            "9008",
            ("12", "56"),
        ),
    }


def _subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "eurostar-elgar.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError(f"{manifest.name} has no subject_regex")


@pytest.mark.parametrize(
    ("subject", "matches"),
    [
        ("Your Eurostar booking confirmation Fri, 01 February - RRRRRR", True),
        ("Your Eurostar confirmation email - Ref:SSSSSS", True),
        # The 2013-2016 layout, from the same domain.
        ("Your Eurostar booking confirmation Fri 3rd Feb 2045 - RRRRRR", False),
        ("Your Eurostar exchange confirmation Fri, 01 February - RRRRRR", False),
        ("Fwd: Your Eurostar confirmation email - Ref:SSSSSS", False),
    ],
)
def test_manifest_subject(subject, matches):
    assert bool(_subject_regex().search(subject)) == matches
