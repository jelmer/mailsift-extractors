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


def test_handles_split_line_html_format(run_extractor):
    # Newer Air France HTML puts each word on its own line, so a
    # single "18h05 Hamburg Airport - Terminal 1" / "Flight AF1511 - Operated
    # by Air France" segment is scattered across ten lines. The extractor
    # has to merge continuation lines back together to parse it.
    out = run_extractor("air-france", "air-france-split-lines.eml")
    assert set(out) == {
        "af-CCCCCC-AF1380.reservation.json",
        "af-CCCCCC-AF1511.reservation.json",
    }
    outbound = out["af-CCCCCC-AF1511.reservation.json"]
    assert outbound["reservationNumber"] == "CCCCCC"
    flight = outbound["reservationFor"]
    assert flight["flightNumber"] == "1511"
    assert flight["departureAirport"] == {
        "@type": "Airport",
        "name": "Hamburg Airport",
        "iataCode": "HAM",
        "address": "Hamburg",
        "alternateName": "Terminal 1",
    }
    assert flight["departureTime"] == "2023-12-30T18:05:00"
    assert flight["arrivalTime"] == "2023-12-30T19:45:00"
    onward = out["af-CCCCCC-AF1380.reservation.json"]
    assert onward["reservationFor"]["flightNumber"] == "1380"
    assert onward["reservationFor"]["departureAirport"]["iataCode"] == "CDG"
    assert onward["reservationFor"]["arrivalAirport"]["iataCode"] == "LHR"


def test_overnight_arrival_rolls_over_the_month(run_extractor):
    out = run_extractor("air-france", "air-france-overnight-month-end.eml")
    assert out == {
        "af-BBBBBB-AF218.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "BBBBBB",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "218",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "AF",
                    "name": "Air France",
                },
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Aeroport Charles de Gaulle",
                    "iataCode": "CDG",
                    "address": "Paris",
                    "alternateName": "Terminal 2E",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "Chhatrapati Shivaji Maharaj International Airport",
                    "iataCode": "BOM",
                    "address": "Mumbai",
                    "alternateName": "Terminal 2",
                },
                "departureTime": "2023-09-30T22:30:00",
                "arrivalTime": "2023-10-01T10:55:00",
            },
        }
    }
