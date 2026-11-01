"""Tests for the BudgetAir.co.uk booking verification extractor."""

from __future__ import annotations

PASSENGERS = [
    {"@type": "Person", "name": "Other User"},
    {"@type": "Person", "name": "Test User"},
]


def reservation(
    airline: str, number: str, origin: str, destination: str, departs: str, arrives: str
) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "broker": {"@type": "Organization", "name": "BudgetAir.co.uk"},
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": number,
            "airline": {"@type": "Airline", "iataCode": airline},
            "departureAirport": {"@type": "Airport", "name": origin},
            "arrivalAirport": {"@type": "Airport", "name": destination},
            "departureTime": departs,
            "arrivalTime": arrives,
        },
        "underName": PASSENGERS,
    }


BERGEN = "Bergen (Flesland)"
STAVANGER = "Stavanger (Sola)"
TROMSO = "Tromso (Langnes)"


def test_booking_verification_emits_one_reservation_per_flight(run_extractor):
    out = run_extractor("budgetair", "budgetair-booking-verification.eml")
    assert out == {
        "budgetair-AAAAAA-20440315-D81234.reservation.json": reservation(
            "D8",
            "1234",
            BERGEN,
            STAVANGER,
            "2044-03-15T07:10:00",
            "2044-03-15T08:15:00",
        ),
        "budgetair-AAAAAA-20440316-DY456.reservation.json": reservation(
            "DY", "456", STAVANGER, TROMSO, "2044-03-16T11:30:00", "2044-03-16T13:10:00"
        ),
        "budgetair-AAAAAA-20440324-DY457.reservation.json": reservation(
            "DY", "457", TROMSO, STAVANGER, "2044-03-24T06:45:00", "2044-03-24T08:20:00"
        ),
        # The second flight of the day has no date line of its own.
        "budgetair-AAAAAA-20440324-D81235.reservation.json": reservation(
            "D8",
            "1235",
            STAVANGER,
            BERGEN,
            "2044-03-24T15:05:00",
            "2044-03-24T16:10:00",
        ),
    }
