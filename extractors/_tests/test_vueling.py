"""Tests for the Vueling booking confirmation extractor."""

from __future__ import annotations


def test_booking_confirmation(run_extractor):
    out = run_extractor("vueling", "vueling.eml")
    assert set(out) == {"vueling-aaaaaa.reservation.json"}
    assert out["vueling-aaaaaa.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationFor": {
            "@type": "Flight",
            "airline": {"@type": "Airline", "name": "Vueling", "iataCode": "VY"},
            "flightNumber": "VY1234",
            "departureTime": "2018-02-24T09:00:00",
            "arrivalTime": "2018-02-24T12:15:00",
            "departureAirport": {"@type": "Airport", "iataCode": "AAA"},
            "arrivalAirport": {"@type": "Airport", "iataCode": "BBB"},
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 91.96,
            "priceCurrency": "GBP",
        },
    }
