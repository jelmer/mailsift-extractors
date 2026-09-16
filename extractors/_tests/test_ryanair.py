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
