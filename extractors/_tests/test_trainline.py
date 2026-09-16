"""Tests for the Trainline booking confirmation extractor."""

from __future__ import annotations


def test_single_leg_carries_the_operator_and_total(run_extractor):
    out = run_extractor("trainline", "trainline.eml")
    assert set(out) == {"trainline-945825428411.reservation.json"}
    assert out["trainline-945825428411.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": "945825428411",
        "reservationFor": {
            "@type": "TrainTrip",
            "departureStation": {"@type": "TrainStation", "name": "Alphaville"},
            "arrivalStation": {"@type": "TrainStation", "name": "Springfield"},
            "departureTime": "2024-04-14T13:30:00",
            "arrivalTime": "2024-04-14T14:30:00",
            "provider": {"@type": "Organization", "name": "Northern Vale Railway"},
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 32.5,
            "priceCurrency": "GBP",
        },
    }


def test_return_emits_a_reservation_per_leg(run_extractor):
    # The inbound leg runs past midnight, so its arrival lands on the
    # day after the one the heading names.
    out = run_extractor("trainline", "trainline-return.eml")
    assert set(out) == {
        "trainline-768577223529-1.reservation.json",
        "trainline-768577223529-2.reservation.json",
    }
    outbound = out["trainline-768577223529-1.reservation.json"]
    assert outbound["reservationFor"]["departureTime"] == "2025-05-03T09:20:00"
    assert outbound["reservationFor"]["arrivalTime"] == "2025-05-03T10:30:00"

    inbound = out["trainline-768577223529-2.reservation.json"]
    assert inbound["reservationFor"]["departureTime"] == "2025-05-05T23:40:00"
    assert inbound["reservationFor"]["arrivalTime"] == "2025-05-06T00:55:00"
    # Only the first leg carries the price; a return would otherwise
    # count the fare twice.
    assert "totalPrice" not in inbound
