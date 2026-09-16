"""Tests for the Delta Air Lines flight receipt extractor."""

from __future__ import annotations


def test_receipt_takes_the_year_from_the_subject(run_extractor):
    # The body's `Sat, 06MAY` has no year; only the subject's
    # `06MAY17` suffix does. Times are 12-hour with am/pm.
    out = run_extractor("delta", "delta.eml")
    assert set(out) == {"delta-aaaaaa.reservation.json"}
    assert out["delta-aaaaaa.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationFor": {
            "@type": "Flight",
            "airline": {
                "@type": "Airline",
                "name": "Delta Air Lines",
                "iataCode": "DL",
            },
            "flightNumber": "DL4567",
            "departureTime": "2017-05-06T14:13:00",
            "arrivalTime": "2017-05-06T16:27:00",
            "departureAirport": {"@type": "Airport", "name": "ALPHAVILLE, CA"},
            "arrivalAirport": {"@type": "Airport", "name": "SPRINGFIELD"},
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 239.20,
            "priceCurrency": "USD",
        },
    }
