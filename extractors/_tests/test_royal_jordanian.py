"""Tests for the Royal Jordanian extractor."""

from __future__ import annotations

_AIRLINE = {"@type": "Airline", "iataCode": "RJ", "name": "Royal Jordanian"}

_HKG = {
    "@type": "Airport",
    "name": "Hong Kong International",
    "alternateName": "Terminal 1",
    "address": {
        "@type": "PostalAddress",
        "addressLocality": "Hong Kong",
        "addressCountry": "Hong Kong (SAR of China)",
    },
}
_AMM = {
    "@type": "Airport",
    "name": "Queen Alia",
    "address": {
        "@type": "PostalAddress",
        "addressLocality": "Amman",
        "addressCountry": "Jordan",
    },
}
_AMS = {
    "@type": "Airport",
    "name": "Schiphol",
    "address": {
        "@type": "PostalAddress",
        "addressLocality": "Amsterdam",
        "addressCountry": "Netherlands",
    },
}


def _html_reservation(flight: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "ticketNumber": "512-0000000000",
        "underName": {"@type": "Person", "name": "Test User"},
        "reservationFor": {"@type": "Flight", "airline": _AIRLINE, **flight},
    }


def test_confirmation_emits_one_reservation_per_flight(run_extractor):
    out = run_extractor("royal-jordanian", "royal-jordanian-confirmation.eml")
    assert out == {
        "rj-AAAAAA-RJ183.reservation.json": _html_reservation(
            {
                "flightNumber": "183",
                "departureAirport": _HKG,
                "arrivalAirport": _AMM,
                "departureTime": "2014-01-09T21:25:00",
                "arrivalTime": "2014-01-10T06:15:00",
            }
        ),
        "rj-AAAAAA-RJ151.reservation.json": _html_reservation(
            {
                "flightNumber": "151",
                "departureAirport": _AMM,
                "arrivalAirport": _AMS,
                "departureTime": "2014-01-10T08:35:00",
                "arrivalTime": "2014-01-10T11:55:00",
            }
        ),
    }


def test_schedule_change_emits_retimed_flights(run_extractor):
    """Same template and filenames as the confirmation, with the new
    times, so it replaces the earlier reservations.
    """
    out = run_extractor("royal-jordanian", "royal-jordanian-schedule-change.eml")
    assert out == {
        "rj-AAAAAA-RJ183.reservation.json": _html_reservation(
            {
                "flightNumber": "183",
                "departureAirport": _HKG,
                "arrivalAirport": _AMM,
                "departureTime": "2014-01-09T21:25:00",
                "arrivalTime": "2014-01-10T05:15:00",
            }
        ),
        "rj-AAAAAA-RJ151.reservation.json": _html_reservation(
            {
                "flightNumber": "151",
                "departureAirport": _AMM,
                "arrivalAirport": _AMS,
                "departureTime": "2014-01-10T07:35:00",
                "arrivalTime": "2014-01-10T11:55:00",
            }
        ),
    }


def _receipt_reservation(flight: dict) -> dict:
    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        },
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "ticketNumber": "512-0000000000",
        "underName": {"@type": "Person", "name": "TEST USER"},
        "reservationFor": {
            "@type": "Flight",
            "airline": _AIRLINE,
            "pending:bookingClass": "Q",
            **flight,
        },
    }


def test_itinerary_receipt_infers_year_and_overnight_arrival(run_extractor):
    """The receipt is issued in December 2013 for flights on 09JAN and
    10JAN, so those are in 2014; RJ183 lands the next morning.
    """
    out = run_extractor("royal-jordanian", "royal-jordanian-eticket.eml")
    assert out == {
        "rj-AAAAAA-RJ183.reservation.json": _receipt_reservation(
            {
                "flightNumber": "183",
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Hong Kong",
                    "alternateName": "Terminal 1",
                },
                "arrivalAirport": {"@type": "Airport", "name": "Amman"},
                "departureTime": "2014-01-09T21:25:00",
                "arrivalTime": "2014-01-10T06:15:00",
            }
        ),
        "rj-AAAAAA-RJ151.reservation.json": _receipt_reservation(
            {
                "flightNumber": "151",
                "departureAirport": {"@type": "Airport", "name": "Amman"},
                "arrivalAirport": {"@type": "Airport", "name": "Amsterdam"},
                "departureTime": "2014-01-10T08:35:00",
                "arrivalTime": "2014-01-10T11:55:00",
            }
        ),
    }
