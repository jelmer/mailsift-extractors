"""Tests for the Eurostar booking and exchange confirmation extractor.

Each direction of the booking becomes its own TrainReservation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def _trip(origin: str, destination: str, departs: str, arrives: str) -> dict:
    return {
        "@type": "TrainTrip",
        "provider": {"@type": "Organization", "name": "Eurostar"},
        "departureStation": {"@type": "TrainStation", "name": origin},
        "arrivalStation": {"@type": "TrainStation", "name": destination},
        "departureTime": departs,
        "arrivalTime": arrives,
    }


def _seat(coach: str, seat: str, fare: str) -> dict:
    return {
        "@type": "Seat",
        "seatNumber": seat,
        "seatSection": coach,
        "seatingType": fare,
    }


def test_return_trip(run_extractor):
    out = run_extractor("eurostar", "eurostar-confirmation.eml")
    assert out == {
        "eurostar-EEEEEE-outbound.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-EEEEEE-outbound",
            "mailsift:itineraryComplete": True,
            "reservationFor": _trip(
                "London St Pancras Int'l",
                "Rotterdam Centraal",
                "2046-06-13T18:04:00",
                "2046-06-13T22:32:00",
            ),
            "ticketedSeat": _seat("5", "17", "Eurostar Standard"),
        },
        "eurostar-EEEEEE-return.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-EEEEEE-return",
            "mailsift:itineraryComplete": True,
            "reservationFor": _trip(
                "Rotterdam Centraal",
                "London St Pancras Int'l",
                "2046-06-24T19:28:00",
                "2046-06-24T21:57:00",
            ),
            "ticketedSeat": _seat("10", "55", "Eurostar Plus"),
        },
    }


def test_exchange_with_a_change_of_train(run_extractor):
    # The return changes trains on the way, but the mail only gives the
    # journey as a whole; the seat is the one on its first train.
    out = run_extractor("eurostar", "eurostar-exchange.eml")
    assert out == {
        "eurostar-GGGGGG-outbound.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-GGGGGG-outbound",
            "mailsift:itineraryComplete": True,
            "reservationFor": _trip(
                "London St Pancras Int'l",
                "Rotterdam Centraal",
                "2045-11-14T06:04:00",
                "2045-11-14T10:32:00",
            ),
            "ticketedSeat": _seat("3", "21", "Standard"),
        },
        "eurostar-GGGGGG-return.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "eurostar-GGGGGG-return",
            "mailsift:itineraryComplete": True,
            "reservationFor": _trip(
                "Rotterdam Centraal",
                "London St Pancras Int'l",
                "2045-11-22T06:58:00",
                "2045-11-22T09:57:00",
            ),
            "ticketedSeat": _seat("2", "31", "Eurostar Plus"),
        },
    }


def test_exchange_without_journeys_emits_nothing(run_extractor):
    # Since 2026 the exchange confirmation only links to the booking;
    # the ticket mail sent with it lists the trains.
    assert run_extractor("eurostar", "eurostar-exchange-no-journeys.eml") == {}


def _subject_regex() -> re.Pattern[str]:
    for line in (EXTRACTORS_DIR / "eurostar.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError("eurostar.yaml has no subject_regex")


@pytest.mark.parametrize(
    "subject",
    [
        "Booking confirmation | Wednesday, 13 June 2046 - Reference: EEEEEE",
        "Booking confirmation | Monday, 30 October - Reference: EEEEEE",
        "Your exchange confirmation | Tuesday, 14 November 2045 - Reference: GGGGGG",
    ],
)
def test_manifest_accepts(subject):
    assert _subject_regex().search(subject)


@pytest.mark.parametrize(
    "subject",
    [
        # Older layouts, which this extractor can't parse.
        "Booking confirmation - here's a link to your tickets | Fri, 30 December - EEEEEE",
        "Your Eurostar exchange confirmation Thu, 22 June - EEEEEE",
        "Your Eurostar booking confirmation Fri, 1 February - EEEEEE",
        "Fwd: Booking confirmation | Wednesday, 13 June 2046 - Reference: EEEEEE",
    ],
)
def test_manifest_rejects(subject):
    assert not _subject_regex().search(subject)
