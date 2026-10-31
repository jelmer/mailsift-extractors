"""Tests for the Expedia flight confirmation extractor."""

from __future__ import annotations

CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}
BROKER = {"@type": "Organization", "name": "Expedia"}
PEGASUS = {"@type": "Airline", "name": "Pegasus Airlines", "iataCode": "PC"}
CHINA_SOUTHERN = {"@type": "Airline", "name": "China Southern Airlines"}


def test_eticket_emits_one_reservation_per_leg(run_extractor):
    out = run_extractor("expedia", "expedia-eticket.eml")
    assert out == {
        "expedia-AAAAAA-20150221-502.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": BROKER,
            "reservationNumber": "AAAAAA",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "502",
                "airline": PEGASUS,
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "STN",
                    "address": "London",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "SAW",
                    "address": "Istanbul",
                },
                "departureTime": "2015-02-21T13:10:00",
                "arrivalTime": "2015-02-21T18:45:00",
                "pending:cabinClass": "Economy / Coach",
                "pending:bookingClass": "V",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketNumber": "6240000000000",
        },
        "expedia-AAAAAA-20150223-779.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": BROKER,
            "reservationNumber": "AAAAAA",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "779",
                "airline": PEGASUS,
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "SAW",
                    "address": "Istanbul",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "TLV",
                    "address": "Tel Aviv",
                },
                "departureTime": "2015-02-23T21:20:00",
                "arrivalTime": "2015-02-23T23:20:00",
                "pending:cabinClass": "Economy / Coach",
                "pending:bookingClass": "V",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketNumber": "6240000000000",
        },
    }


def test_confirmation_with_overnight_connection(run_extractor):
    """The first segment lands the next day ("+1 day"); the connection
    departs on that arrival date even though the leg header only names
    the first day.
    """
    out = run_extractor("expedia", "expedia-confirmation.eml")
    assert out == {
        "expedia-CCCCCC-20180201-302.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": BROKER,
            "reservationNumber": "CCCCCC",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "302",
                "airline": CHINA_SOUTHERN,
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "SYD",
                    "address": "Sydney",
                    "alternateName": "Terminal 1",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "CAN",
                    "address": "Guangzhou",
                },
                "departureTime": "2018-02-01T22:15:00",
                "arrivalTime": "2018-02-02T05:00:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "V",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketedSeat": {"@type": "Seat", "seatNumber": "10A"},
        },
        "expedia-CCCCCC-20180202-303.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": BROKER,
            "reservationNumber": "CCCCCC",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "303",
                "airline": CHINA_SOUTHERN,
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "CAN",
                    "address": "Guangzhou",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "LHR",
                    "address": "London",
                    "alternateName": "Terminal 4",
                },
                "departureTime": "2018-02-02T09:30:00",
                "arrivalTime": "2018-02-02T14:30:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "V",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketedSeat": {"@type": "Seat", "seatNumber": "20C"},
        },
    }
