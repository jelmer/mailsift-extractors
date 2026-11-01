"""Tests for the Aer Lingus booking confirmation extractor."""

from __future__ import annotations

CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}
AER_LINGUS = {"@type": "Airline", "iataCode": "EI", "name": "Aer Lingus"}
COPENHAGEN = {"@type": "Airport", "name": "Copenhagen", "iataCode": "CPH"}
CORK = {"@type": "Airport", "name": "Cork", "iataCode": "ORK"}


def reservation(flight: dict) -> dict:
    return {
        "@context": CONTEXT,
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationFor": {"@type": "Flight", "airline": AER_LINGUS, **flight},
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "underName": {"@type": "Person", "name": "Test User"},
        "ticketNumber": "0530000000000",
    }


def test_confirmation_emits_one_reservation_per_flight(run_extractor):
    out = run_extractor("aer-lingus", "aer-lingus-confirmation.eml")
    assert out == {
        # "Cork-Terminal 1 (ORK)" names the terminal.
        "aer-lingus-AAAAAA-20390215-EI712.reservation.json": reservation(
            {
                "flightNumber": "712",
                "departureAirport": COPENHAGEN,
                "arrivalAirport": CORK,
                "departureTime": "2039-02-15T15:10:00",
                "arrivalTime": "2039-02-15T15:50:00",
                "arrivalTerminal": "1",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "W",
            }
        ),
        "aer-lingus-AAAAAA-20390216-EI713.reservation.json": reservation(
            {
                "flightNumber": "713",
                "departureAirport": CORK,
                "arrivalAirport": COPENHAGEN,
                "departureTime": "2039-02-16T13:45:00",
                "arrivalTime": "2039-02-16T16:20:00",
                "departureTerminal": "1",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "A",
            }
        ),
    }
