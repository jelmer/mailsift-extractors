"""Tests for the Travelodge booking confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_booking_confirmation(run_extractor):
    # Travelodge writes its times as `3pm` and `12 noon` rather than a
    # 24-hour clock; both land on the right hour.
    out = run_extractor("travelodge", "travelodge.eml")
    assert set(out) == {"travelodge-12345678.reservation.json"}
    assert out["travelodge-12345678.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": "travelodge-12345678",
        "checkinTime": "2024-10-11T15:00:00",
        "checkoutTime": "2024-10-13T12:00:00",
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": "Travelodge Springfield Central",
            "address": "AA1 7DY",
        },
        "accommodationCategory": "Twin room",
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 169.98,
            "priceCurrency": "GBP",
        },
    }


def test_invoice_mail_produces_nothing(run_extractor):
    # The same address sends a VAT invoice with no check-in or
    # check-out lines; it must not yield a half-filled reservation.
    out = run_extractor("travelodge", "travelodge-invoice.eml")
    assert out == {}


def test_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("travelodge", "travelodge-cancellation.eml")
    assert out == {
        "travelodge-12345679.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "travelodge-12345679",
            "checkinTime": "2046-03-09T15:00:00",
            "checkoutTime": "2046-03-11T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Travelodge Springfield Central",
            },
            "accommodationCategory": "Double Room",
            "reservationStatus": "ReservationCancelled",
        }
    }


def test_modification_replaces_the_booking(run_extractor):
    out = run_extractor("travelodge", "travelodge-modified.eml")
    assert out == {
        "travelodge-12345670.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "travelodge-12345670",
            "checkinTime": "2046-03-09T15:00:00",
            "checkoutTime": "2046-03-11T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Travelodge Springfield Central",
                "address": "AA1 7DY",
            },
            "accommodationCategory": "Double Room",
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 139.98,
                "priceCurrency": "GBP",
            },
        }
    }


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "travelodge.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    assert pattern.search("YOUR TRAVELODGE BOOKING IS CANCELLED")
    assert pattern.search("Your Travelodge booking confirmation")
    assert pattern.search("Your Travelodge booking is modified")
    assert not pattern.search("Your Travelodge Invoice")
