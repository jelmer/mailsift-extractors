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
    assert res["pending:numAdults"] == 1
    assert res["tripmate:numRooms"] == 1
    assert res["@context"] == {
        "@vocab": "https://schema.org/",
        "pending": "https://pending.schema.org/",
        "tripmate": "https://jelmer.github.io/tripmate/ns#",
    }


def test_norwegian_locale_variant(run_extractor):
    # Thon's Norwegian-locale template uses `.` as the time separator
    # (`12.00`) and non-breaking spaces between labels and values
    # (`Check-in from&nbsp;12.00`). The extractor accepts both time
    # separators and treats nbsp as whitespace.
    out = run_extractor("thon-hotels", "thon-hotels-norwegian-locale.eml")
    assert set(out) == {"thon-999999999.reservation.json"}
    r = out["thon-999999999.reservation.json"]
    assert r["reservationNumber"] == "thon-999999999"
    assert r["checkinTime"] == "2025-01-31T12:00:00"
    assert r["checkoutTime"] == "2025-02-02T13:00:00"
    assert r["reservationFor"]["name"] == "Thon Hotel Brussels City Centre"
    assert r["totalPrice"] == {
        "@type": "PriceSpecification",
        "price": 192.0,
        "priceCurrency": "EUR",
    }
