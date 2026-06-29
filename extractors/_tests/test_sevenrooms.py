"""Tests for the SevenRooms restaurant-confirmation extractor."""

from __future__ import annotations


def test_food_reservation(run_extractor):
    out = run_extractor("sevenrooms", "sevenrooms-confirmation.eml")
    assert set(out) == {"sevenrooms-GGGGGGGGGGG.reservation.json"}
    assert out["sevenrooms-GGGGGGGGGGG.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "startTime": "2026-04-17T18:45:00Z",
        "endTime": "2026-04-17T20:15:00Z",
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": "The Example Bistro",
            "address": "1 Example Lane",
        },
        "partySize": 2,
        "reservationNumber": "sevenrooms-GGGGGGGGGGG",
    }
