"""Tests for the Transavia booking-confirmation extractor."""

from __future__ import annotations


def test_booking_emits_one_reservation_per_leg(run_extractor):
    out = run_extractor("transavia-booking", "transavia-booking.eml")
    assert set(out) == {
        "transavia-aaaaaa-hv6111.reservation.json",
        "transavia-aaaaaa-hv6112.reservation.json",
    }

    outbound = out["transavia-aaaaaa-hv6111.reservation.json"]
    assert outbound["@type"] == "FlightReservation"
    assert outbound["reservationNumber"] == "AAAAAA"
    assert outbound["reservationStatus"] == "https://schema.org/ReservationConfirmed"
    assert outbound["reservationFor"] == {
        "@type": "Flight",
        "flightNumber": "6111",
        "airline": {
            "@type": "Airline",
            "iataCode": "HV",
            "name": "Transavia",
        },
        "departureAirport": {
            "@type": "Airport",
            "name": "Schiphol",
            "address": "Amsterdam",
            "iataCode": "AMS",
        },
        "arrivalAirport": {
            "@type": "Airport",
            "name": "Barcelona",
            "address": "Spanje",
            "iataCode": "BCN",
        },
        "departureTime": "2025-04-04T09:15:00",
        "arrivalTime": "2025-04-04T11:30:00",
    }

    inbound = out["transavia-aaaaaa-hv6112.reservation.json"]
    assert inbound["reservationFor"]["flightNumber"] == "6112"
    assert inbound["reservationFor"]["departureAirport"]["iataCode"] == "BCN"
    assert inbound["reservationFor"]["arrivalAirport"]["iataCode"] == "AMS"
    assert inbound["reservationFor"]["departureTime"] == "2025-04-07T12:00:00"
    assert inbound["reservationFor"]["arrivalTime"] == "2025-04-07T14:20:00"
