"""Tests for the Virgin Atlantic e-ticket extractor."""

from __future__ import annotations

CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}
VIRGIN = {"@type": "Airline", "iataCode": "VS", "name": "Virgin Atlantic"}


def reservation(flight: dict) -> dict:
    return {
        "@context": CONTEXT,
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "reservationFor": {"@type": "Flight", "airline": VIRGIN, **flight},
        "underName": {"@type": "Person", "name": "Test User"},
        "ticketNumber": "9320000000002",
    }


def test_eticket_dates_flights_from_the_issue_date(run_extractor):
    out = run_extractor("virgin-atlantic", "virgin-atlantic-eticket.eml")
    assert out == {
        # Overnight: it arrives the next morning.
        "virgin-atlantic-AAAAAA-20441026-VS127.reservation.json": reservation(
            {
                "flightNumber": "127",
                "departureAirport": {"@type": "Airport", "iataCode": "MAN"},
                "arrivalAirport": {"@type": "Airport", "iataCode": "ATL"},
                "departureTime": "2044-10-26T21:55:00",
                "arrivalTime": "2044-10-27T10:45:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "V",
            }
        ),
        "virgin-atlantic-AAAAAA-20441109-VS128.reservation.json": reservation(
            {
                "flightNumber": "128",
                "departureAirport": {"@type": "Airport", "iataCode": "ATL"},
                "arrivalAirport": {"@type": "Airport", "iataCode": "MAN"},
                "departureTime": "2044-11-09T14:00:00",
                "arrivalTime": "2044-11-09T17:55:00",
                "pending:cabinClass": "Upper Class",
                "pending:bookingClass": "G",
            }
        ),
    }
