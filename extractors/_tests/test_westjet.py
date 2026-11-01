"""Tests for the WestJet itinerary extractor."""

from __future__ import annotations


def test_itinerary_dates_the_flight_from_the_mail(run_extractor):
    out = run_extractor("westjet", "westjet-itinerary.eml")
    assert out == {
        "westjet-AAAAAA-20450809-WS1234.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "AAAAAA",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "1234",
                "airline": {"@type": "Airline", "iataCode": "WS", "name": "WestJet"},
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "YYC",
                    "name": "CALGARY AB, CANADA",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "LAX",
                    "name": "LOS ANGELES, CA",
                },
                "departureTime": "2045-08-09T09:15:00",
                "arrivalTime": "2045-08-09T11:58:00",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketNumber": "8380000000001",
        }
    }
