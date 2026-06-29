"""Tests for the Air France booking-confirmation extractor."""

from __future__ import annotations


def test_single_segment_emits_one_reservation(run_extractor):
    out = run_extractor("air-france", "air-france-confirmation.eml")
    assert set(out) == {"af-AAAAAA-AF1511.reservation.json"}
    res = out["af-AAAAAA-AF1511.reservation.json"]
    assert res["reservationNumber"] == "AAAAAA"
    flight = res["reservationFor"]
    assert flight["flightNumber"] == "1511"
    assert flight["airline"] == {
        "@type": "Airline",
        "iataCode": "AF",
        "name": "Air France",
    }
    assert flight["departureAirport"] == {
        "@type": "Airport",
        "name": "Hamburg Airport",
        "iataCode": "HAM",
        "address": "Hamburg",
        "alternateName": "Terminal 1",
    }
    assert flight["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Aeroport Charles de Gaulle",
        "iataCode": "CDG",
        "address": "Paris",
        "alternateName": "Terminal 2F",
    }
    assert flight["departureTime"] == "2023-12-30T18:05:00"
    assert flight["arrivalTime"] == "2023-12-30T19:45:00"
