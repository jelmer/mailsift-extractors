"""Tests for the Sainsbury's grocery delivery-slot extractor."""

from __future__ import annotations


def test_delivery_slot(run_extractor):
    out = run_extractor("sainsburys", "sainsburys-delivery.eml")
    assert set(out) == {"sainsburys-9999999999.reservation.json"}
    assert out["sainsburys-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Sainsbury's delivery",
            "startDate": "2026-03-17T11:37:00",
            "endDate": "2026-03-17T12:37:00",
            "location": {"@type": "Place", "address": "EC1A 1AA"},
        },
        "reservationNumber": "sainsburys-9999999999",
    }
