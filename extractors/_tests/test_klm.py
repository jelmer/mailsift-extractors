"""Tests for the KLM booking-confirmation extractor."""

from __future__ import annotations


def test_two_segment_booking_emits_two_reservations(run_extractor):
    out = run_extractor("klm", "klm-confirmation.eml")
    assert set(out) == {
        "klm-P00000-KL1000.reservation.json",
        "klm-P00000-KL0605.reservation.json",
    }
    leg1 = out["klm-P00000-KL1000.reservation.json"]
    assert leg1["reservationNumber"] == "P00000"
    assert leg1["reservationFor"]["flightNumber"] == "1000"
    assert leg1["reservationFor"]["departureTime"] == "2019-02-19T06:30:00"
    assert leg1["reservationFor"]["arrivalTime"] == "2019-02-19T09:00:00"
    assert leg1["reservationFor"]["departureAirport"] == {
        "@type": "Airport",
        "name": "Heathrow Airport",
        "address": "London",
    }
    assert leg1["reservationFor"]["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Schiphol",
        "address": "Amsterdam",
    }

    leg2 = out["klm-P00000-KL0605.reservation.json"]
    assert leg2["reservationFor"]["flightNumber"] == "605"
    assert leg2["reservationFor"]["departureTime"] == "2019-02-19T10:25:00"
    assert leg2["reservationFor"]["arrivalTime"] == "2019-02-19T12:25:00"
    assert leg2["reservationFor"]["arrivalAirport"]["name"] == ("San Francisco Intl.")
