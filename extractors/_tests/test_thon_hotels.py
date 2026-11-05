"""Tests for the Thon Hotels booking-confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


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
    assert res["wayfare:numRooms"] == 1
    assert res["@context"] == {
        "@vocab": "https://schema.org/",
        "pending": "https://pending.schema.org/",
        "wayfare": "https://jelmer.github.io/wayfare/ns#",
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


def test_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("thon-hotels", "thon-hotels-cancellation.eml")
    assert out == {
        "thon-400000001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationStatus": "ReservationCancelled",
            "reservationNumber": "thon-400000001",
            "checkinTime": "2046-06-15",
            "checkoutTime": "2046-06-17",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Thon Hotel Eksempel",
            },
        }
    }


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "thon-hotels.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    assert pattern.search("Your reservation at Thon Hotel Eksempel has been cancelled")
    assert pattern.search("Booking Confirmation Thon Hotel Eksempel")


def test_2026_layout(run_extractor):
    # "Ref.:" with a colon, date and check-in time in cells of their
    # own, and the address on the "Address" line.
    out = run_extractor("thon-hotels", "thon-hotels-2026.eml")
    assert out == {
        "thon-400000002.reservation.json": {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
                "wayfare": "https://jelmer.github.io/wayfare/ns#",
            },
            "@type": "LodgingReservation",
            "reservationNumber": "thon-400000002",
            "checkinTime": "2047-01-29T15:00:00",
            "checkoutTime": "2047-01-31T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Thon Hotel Eksempel",
                "address": "Eksempelgata 1, Eksempelby, NO",
            },
            "pending:numAdults": 1,
            "wayfare:numRooms": 1,
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 252.0,
                "priceCurrency": "EUR",
            },
        }
    }
