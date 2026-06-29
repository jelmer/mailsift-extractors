"""Tests for the Norwegian Air booking-confirmation extractor."""

from __future__ import annotations


def test_two_segment_confirmation_emits_two_reservations(run_extractor):
    out = run_extractor("norwegian", "norwegian-confirmation.eml")
    assert set(out) == {
        "norwegian-CCCCCC-DY1303.reservation.json",
        "norwegian-CCCCCC-DY1312.reservation.json",
    }
    outbound = out["norwegian-CCCCCC-DY1303.reservation.json"]
    assert outbound["reservationNumber"] == "CCCCCC"
    assert outbound["reservationFor"]["flightNumber"] == "1303"
    assert outbound["reservationFor"]["airline"] == {
        "@type": "Airline",
        "iataCode": "DY",
        "name": "Norwegian",
    }
    assert outbound["reservationFor"]["departureAirport"] == {
        "@type": "Airport",
        "name": "London-Gatwick",
    }
    assert outbound["reservationFor"]["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Oslo-Gardermoen",
    }
    assert outbound["reservationFor"]["departureTime"] == "2025-06-10T09:20:00"
    assert outbound["reservationFor"]["arrivalTime"] == "2025-06-10T12:25:00"

    inbound = out["norwegian-CCCCCC-DY1312.reservation.json"]
    assert inbound["reservationFor"]["departureTime"] == "2025-06-15T14:25:00"
    assert inbound["reservationFor"]["arrivalTime"] == "2025-06-15T15:45:00"
