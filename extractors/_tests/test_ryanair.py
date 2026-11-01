"""Tests for the Ryanair travel itinerary extractor."""

from __future__ import annotations


def test_itinerary_carries_iata_codes_and_the_receipt_total(run_extractor):
    # Ryanair writes the year with two digits, which resolves via %y.
    out = run_extractor("ryanair", "ryanair.eml")
    assert set(out) == {"ryanair-aaaaaa.reservation.json"}
    assert out["ryanair-aaaaaa.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationFor": {
            "@type": "Flight",
            "airline": {"@type": "Airline", "name": "Ryanair", "iataCode": "FR"},
            "flightNumber": "FR1234",
            "departureTime": "2020-01-06T22:15:00",
            "arrivalTime": "2020-01-06T23:10:00",
            "departureAirport": {"@type": "Airport", "iataCode": "AAA"},
            "arrivalAirport": {"@type": "Airport", "iataCode": "BBB"},
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 277.68,
            "priceCurrency": "EUR",
        },
    }


def flight(
    number: str, origin: str, destination: str, departs: str, arrives: str
) -> dict:
    return {
        "@type": "Flight",
        "airline": {"@type": "Airline", "name": "Ryanair", "iataCode": "FR"},
        "flightNumber": number,
        "departureTime": departs,
        "arrivalTime": arrives,
        "departureAirport": {"@type": "Airport", "iataCode": origin},
        "arrivalAirport": {"@type": "Airport", "iataCode": destination},
    }


def booking(reference: str, leg: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": reference,
        "reservationFor": leg,
    }


def test_2018_layout_splits_the_return_flights(run_extractor):
    out = run_extractor("ryanair", "ryanair-legacy-2018.eml")
    assert out == {
        "ryanair-cccccc-1.reservation.json": booking(
            "CCCCCC",
            flight(
                "FR4321", "BRS", "ORK", "2046-04-16T18:30:00", "2046-04-16T19:55:00"
            ),
        ),
        "ryanair-cccccc-2.reservation.json": booking(
            "CCCCCC",
            flight(
                "FR4322", "ORK", "BRS", "2046-04-23T20:20:00", "2046-04-23T21:40:00"
            ),
        ),
    }


def test_2015_layout(run_extractor):
    out = run_extractor("ryanair", "ryanair-legacy-2015.eml")
    assert out == {
        "ryanair-bbbbbb.reservation.json": booking(
            "BBBBBB",
            flight(
                "FR1022", "GDN", "DUB", "2043-01-26T21:45:00", "2043-01-26T23:15:00"
            ),
        ),
    }


def test_2011_layout(run_extractor):
    # One line per flight, with a date like "30May39".
    out = run_extractor("ryanair", "ryanair-legacy-2011.eml")
    assert out == {
        "ryanair-aaaaaa.reservation.json": booking(
            "AAAAAA",
            flight(
                "FR3124", "FAO", "BRE", "2039-05-30T16:45:00", "2039-05-30T19:50:00"
            ),
        ),
    }
