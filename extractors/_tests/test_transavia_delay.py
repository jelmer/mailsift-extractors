"""Tests for the Transavia flight-delay notification extractor."""

from __future__ import annotations


def test_delay_emits_reservation(run_extractor):
    out = run_extractor("transavia-delay", "transavia-delay.eml")
    assert set(out) == {"transavia-DDDDDD-HV5314.reservation.json"}
    res = out["transavia-DDDDDD-HV5314.reservation.json"]
    assert res["@type"] == "FlightReservation"
    assert res["reservationNumber"] == "DDDDDD"
    assert res["reservationStatus"] == "https://schema.org/ReservationConfirmed"
    assert res["modifiedTime"] == "2025-12-30T11:57:06+00:00"
    assert res["reservationFor"] == {
        "@type": "Flight",
        "flightNumber": "5314",
        "airline": {
            "@type": "Airline",
            "iataCode": "HV",
            "name": "Transavia",
        },
        "departureAirport": {
            "@type": "Airport",
            "name": "Larnaca",
            "address": "Cyprus",
        },
        "arrivalAirport": {
            "@type": "Airport",
            "name": "Schiphol",
            "address": "Amsterdam",
        },
        "departureTime": "2025-12-30T14:25:00",
    }
