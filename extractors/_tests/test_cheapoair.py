"""Tests for the CheapOair booking receipt extractor."""

from __future__ import annotations

EXPECTED = {
    "@context": "https://schema.org",
    "@type": "FlightReservation",
    "reservationNumber": "ABCDEF",
    "broker": {"@type": "Organization", "name": "CheapOair"},
    "underName": {"@type": "Person", "name": "Test User"},
    "ticketNumber": "1690000000000",
    "reservationFor": {
        "@type": "Flight",
        "flightNumber": "501",
        "airline": {
            "@type": "Airline",
            "iataCode": "Z8",
            "name": "Linea Aerea Amaszonas",
        },
        "departureAirport": {
            "@type": "Airport",
            "iataCode": "CUZ",
            "address": {"@type": "PostalAddress", "addressLocality": "Cuzco"},
        },
        "arrivalAirport": {
            "@type": "Airport",
            "iataCode": "LPB",
            "address": {"@type": "PostalAddress", "addressLocality": "La Paz"},
        },
        "departureTime": "2015-01-03T10:35:00",
        "arrivalTime": "2015-01-03T12:35:00",
    },
}


def test_eticket(run_extractor):
    out = run_extractor("cheapoair", "cheapoair-eticket.eml")
    assert out == {"cheapoair-10000000-Z8501.reservation.json": EXPECTED}


def test_receipt(run_extractor):
    out = run_extractor("cheapoair", "cheapoair-receipt.eml")
    assert out == {"cheapoair-10000000-Z8501.reservation.json": EXPECTED}
