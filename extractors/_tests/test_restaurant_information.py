"""Tests for the restaurant-information.com booking-confirmation extractor."""

from __future__ import annotations


def test_confirmation_emits_reservation(run_extractor):
    out = run_extractor(
        "restaurant-information", "restaurant-information-confirmation.eml"
    )
    assert set(out) == {
        "restaurant-information-00000000-0000-0000-0000-000000000000.reservation.json"
    }
    res = out[
        "restaurant-information-00000000-0000-0000-0000-000000000000.reservation.json"
    ]
    assert res["@type"] == "FoodEstablishmentReservation"
    assert (
        res["reservationNumber"]
        == "restaurant-information-00000000-0000-0000-0000-000000000000"
    )
    # Mail sent 2026-03-18; booking date "Thursday, 19 Mar" -> 2026-03-19.
    assert res["startTime"] == "2026-03-19T18:30:00"
    assert res["endTime"] == "2026-03-19T20:30:00"
    assert res["partySize"] == 2
    assert res["reservationFor"] == {
        "@type": "FoodEstablishment",
        "name": "Example Restaurant",
    }
