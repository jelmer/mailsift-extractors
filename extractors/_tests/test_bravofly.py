"""Tests for the Bravofly flight booking confirmation extractor."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"

CONTEXT = {"@vocab": "https://schema.org/", "pending": "https://pending.schema.org/"}
LHR = {"@type": "Airport", "name": "London Heathrow", "iataCode": "LHR"}
FRA = {"@type": "Airport", "name": "Frankfurt Int.", "iataCode": "FRA"}
HND = {"@type": "Airport", "name": "Tokyo Haneda", "iataCode": "HND"}
LUFTHANSA = {"@type": "Airline", "iataCode": "LH", "name": "Lufthansa"}


def reservation(flight: dict) -> dict:
    return {
        "@context": CONTEXT,
        "@type": "FlightReservation",
        "reservationNumber": "ABC123",
        "broker": {"@type": "Organization", "name": "Bravofly"},
        "underName": {"@type": "Person", "name": "Test User"},
        "ticketNumber": "2050000000000",
        "reservationFor": flight,
    }


def test_return_trip_emits_one_reservation_per_leg(run_extractor):
    out = run_extractor("bravofly", "bravofly-confirmation.eml")
    assert out == {
        "bravofly-100000000-LH905.reservation.json": reservation(
            {
                "@type": "Flight",
                "flightNumber": "905",
                "airline": LUFTHANSA,
                "departureAirport": LHR,
                "arrivalAirport": FRA,
                "departureTime": "2015-07-25T11:30:00",
                "arrivalTime": "2015-07-25T14:05:00",
                "pending:cabinClass": "Economy",
            }
        ),
        # Overnight: lands the day after the date on the row.
        "bravofly-100000000-LH716.reservation.json": reservation(
            {
                "@type": "Flight",
                "flightNumber": "716",
                "airline": LUFTHANSA,
                "departureAirport": FRA,
                "arrivalAirport": HND,
                "departureTime": "2015-07-25T18:05:00",
                "arrivalTime": "2015-07-26T12:15:00",
                "pending:cabinClass": "Economy",
            }
        ),
        "bravofly-100000000-NH211.reservation.json": reservation(
            {
                "@type": "Flight",
                "flightNumber": "211",
                "airline": {"@type": "Airline", "iataCode": "NH", "name": "ANA"},
                "departureAirport": HND,
                "arrivalAirport": LHR,
                "departureTime": "2015-08-16T11:40:00",
                "arrivalTime": "2015-08-16T16:10:00",
                "pending:cabinClass": "Economy",
            }
        ),
    }


def test_refuses_after_cutoff(tmp_path):
    # The mail is unsigned, so a recent message in the old template is
    # treated as a spoof.
    eml = (CORPUS_DIR / "bravofly-confirmation.eml").read_bytes()
    eml = eml.replace(b"Date: Tue, 5 May 2015", b"Date: Sun, 5 May 2024")
    subprocess.run(
        [sys.executable, str(EXTRACTORS_DIR / "bravofly.py")],
        cwd=tmp_path,
        input=eml,
        check=True,
    )
    assert list(tmp_path.iterdir()) == []
