"""Tests for the LAN Airlines extractor."""

from __future__ import annotations

_STUB_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def test_eticket_confirmation_emits_reservation(run_extractor):
    out = run_extractor("lan", "lan-eticket.eml")
    assert out == {
        "lan-AAAAAA-LA2096.reservation.json": {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "FlightReservation",
            "reservationNumber": "AAAAAA",
            "underName": {"@type": "Person", "name": "Test User"},
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "2096",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "LA",
                    "name": "LAN Airlines",
                },
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Juliaca",
                    "iataCode": "JUL",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "Lima",
                    "iataCode": "LIM",
                },
                "departureTime": "2015-01-07T13:15:00",
                "arrivalTime": "2015-01-07T14:55:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "L",
            },
        }
    }


def test_boarding_pass_emits_reservation_from_subject(run_extractor):
    out = run_extractor("lan", "lan-boarding-pass.eml")
    assert out == {
        "lan-LA7735-20181215.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "underName": {"@type": "Person", "name": "TEST USER"},
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "7735",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "LA",
                    "name": "LAN Airlines",
                },
                "departureAirport": {"@type": "Airport", "name": "El Calafate"},
                "arrivalAirport": {"@type": "Airport", "name": "Buenos Aires"},
                "departureTime": "2018-12-15",
            },
        },
        "lan-LA7735-20181215.ticket.pdf": _STUB_PDF,
    }
