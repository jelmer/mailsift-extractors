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


def test_legacy_label_variant(run_extractor):
    # Older Norwegian mail (~2014) uses the label
    # `YOUR BOOKING REFERENCE IS:` with the reference on the next
    # line. Newer templates use the inline `Booking reference: X`.
    # The extractor recognises both.
    out = run_extractor("norwegian", "norwegian-legacy-confirmation.eml")
    assert set(out) == {"norwegian-LEGACY-DY5407.reservation.json"}
    r = out["norwegian-LEGACY-DY5407.reservation.json"]
    assert r["reservationNumber"] == "LEGACY"
    assert r["reservationFor"]["flightNumber"] == "5407"
    assert r["reservationFor"]["departureTime"] == "2014-11-20T20:15:00"
