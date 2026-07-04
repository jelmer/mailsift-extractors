"""Tests for the Thon Hotels booking-confirmation extractor."""

from __future__ import annotations


def test_confirmation_emits_reservation(run_extractor):
    out = run_extractor("thon-hotels", "thon-hotels-confirmation.eml")
    assert set(out) == {"thon-400000000.reservation.json"}
    res = out["thon-400000000.reservation.json"]
    assert res["@type"] == "LodgingReservation"
    assert res["reservationNumber"] == "thon-400000000"
    assert res["checkinTime"] == "2026-01-30T12:00:00"
    assert res["checkoutTime"] == "2026-02-01T13:00:00"
    assert res["reservationFor"] == {
        "@type": "LodgingBusiness",
        "name": "Thon Hotel Brussels City Centre",
        "address": "Avenue du Boulevard 17, Brussels, BE",
    }
    assert res["totalPrice"] == {
        "@type": "PriceSpecification",
        "price": 204.00,
        "priceCurrency": "EUR",
    }
