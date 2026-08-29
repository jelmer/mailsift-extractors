"""Tests for the Eventbrite order-confirmation and cancellation extractor."""

from __future__ import annotations


def test_order_confirmation_emits_event_reservation(run_extractor):
    out = run_extractor("eventbrite", "eventbrite-order-confirmation.eml")
    assert set(out) == {"eventbrite-9999999999.reservation.json"}
    assert out["eventbrite-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "eventbrite-9999999999",
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "reservationFor": {
            "@type": "Event",
            "name": "Example Event Title",
            "startDate": "2023-06-29T19:00:00",
            "endDate": "2023-06-29T21:00:00",
            "location": {
                "@type": "Place",
                "name": "Example Venue",
                "address": "Example Venue 1 Example Street London",
            },
        },
        "provider": {"@type": "Organization", "name": "Eventbrite"},
    }


def test_order_cancellation_flags_reservation_cancelled(run_extractor):
    out = run_extractor("eventbrite", "eventbrite-order-cancellation.eml")
    assert set(out) == {"eventbrite-9999999999.reservation.json"}
    assert out["eventbrite-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "eventbrite-9999999999",
        "reservationStatus": "https://schema.org/ReservationCancelled",
        "reservationFor": {
            "@type": "Event",
            "name": "Example Event Title",
            "startDate": "2023-06-29T19:00:00",
            "endDate": "2023-06-29T21:00:00",
        },
        "provider": {"@type": "Organization", "name": "Eventbrite"},
    }
