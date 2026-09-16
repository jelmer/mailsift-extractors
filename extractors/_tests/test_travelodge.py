"""Tests for the Travelodge booking confirmation extractor."""

from __future__ import annotations


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
