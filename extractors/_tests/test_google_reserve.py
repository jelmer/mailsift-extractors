"""Tests for the Google Reserve restaurant-confirmation extractor."""

from __future__ import annotations


def test_food_reservation(run_extractor):
    out = run_extractor("google-reserve", "google-reserve-confirmation.eml")
    assert set(out) == {"google-reserve-0000-0000-0000-0000.reservation.json"}
    assert out["google-reserve-0000-0000-0000-0000.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "startTime": "2026-04-17T19:45:00+01:00",
        "endTime": "2026-04-17T21:15:00+01:00",
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": "The Example Bistro",
            "address": "1 Example Lane, EC1A 1AA, GB",
        },
        "partySize": 2,
        "reservationNumber": "google-reserve-0000-0000-0000-0000",
    }
