"""Tests for the easyJet flight-confirmation extractor.

One mail can carry multiple legs; each leg becomes its own
FlightReservation file keyed off booking ref + flight number.
"""

from __future__ import annotations


def test_two_legs_one_per_file(run_extractor):
    out = run_extractor("easyjet", "easyjet-confirmation.eml")
    assert set(out) == {
        "easyjet-abcdefg-ezy2512.reservation.json",
        "easyjet-abcdefg-ezy2521.reservation.json",
    }
    assert out["easyjet-abcdefg-ezy2521.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "easyjet-ABCDEFG-EZY2521",
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "2521",
            "airline": {"@type": "Airline", "iataCode": "EZY"},
            "departureAirport": {"@type": "Airport", "name": "London Luton"},
            "arrivalAirport": {"@type": "Airport", "name": "Amsterdam"},
            "departureTime": "2024-07-12T18:45:00",
            "arrivalTime": "2024-07-12T20:55:00",
        },
    }
    assert (
        out["easyjet-abcdefg-ezy2512.reservation.json"]["reservationFor"][
            "departureAirport"
        ]["name"]
        == "Amsterdam"
    )
    assert (
        out["easyjet-abcdefg-ezy2512.reservation.json"]["reservationFor"][
            "arrivalAirport"
        ]["name"]
        == "London Luton"
    )
