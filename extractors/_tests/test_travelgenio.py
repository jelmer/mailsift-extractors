"""Tests for the Travelgenio flight booking extractor."""

from __future__ import annotations

CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}
BROKER = {"@type": "Organization", "name": "Travelgenio"}


def test_booking_mail_emits_reservation(run_extractor):
    out = run_extractor("travelgenio", "travelgenio-booking.eml")
    assert out == {
        "travelgenio-AAAAAA-20140102-VN598.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "AAAAAA",
            "broker": BROKER,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "598",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "VN",
                    "name": "Vietnam Airlines",
                },
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Tan Son Nhut International",
                    "iataCode": "SGN",
                    "address": "Ho Chi Minh City",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "Hong Kong International",
                    "iataCode": "HKG",
                    "address": "Hong Kong",
                },
                "departureTime": "2014-01-02T18:30:00",
                "arrivalTime": "2014-01-02T21:55:00",
            },
            "underName": [
                {"@type": "Person", "name": "Test User"},
                {"@type": "Person", "name": "Other Person"},
            ],
        },
    }


def test_eticket_emits_reservation_under_same_slug(run_extractor):
    """The viewtrip e-ticket files under the same booking code and slug
    as the earlier booking mail, so it supersedes it.
    """
    out = run_extractor("travelgenio", "travelgenio-eticket.eml")
    assert out == {
        "travelgenio-AAAAAA-20140102-VN598.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "AAAAAA",
            "broker": BROKER,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "598",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "VN",
                    "name": "Vietnam Airlines Corporation",
                },
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Tan Son Nhut Arpt",
                    "iataCode": "SGN",
                    "address": "Ho Chi Minh City",
                    "alternateName": "Terminal 2",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "Hong Kong Intl",
                    "iataCode": "HKG",
                    "alternateName": "Terminal 1",
                },
                "departureTime": "2014-01-02T18:30:00",
                "arrivalTime": "2014-01-02T21:55:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "H",
            },
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "underName": [
                {"@type": "Person", "name": "TEST USER"},
                {"@type": "Person", "name": "OTHER PERSON"},
            ],
        },
    }
