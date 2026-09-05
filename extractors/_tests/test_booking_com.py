"""Tests for the Booking.com hotel-confirmation extractor."""

from __future__ import annotations


def test_lodging_reservation(run_extractor):
    out = run_extractor("booking-com", "booking-com-confirmation.eml")
    assert set(out) == {"booking-com-9999999999.reservation.json"}
    assert out["booking-com-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "checkinTime": "2024-07-19T15:00:00",
        "checkoutTime": "2024-07-21T11:00:00",
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": "Example Hotel Amsterdam",
            "address": "1 Example Street, Amsterdam, 1011 AB, Netherlands",
        },
        "reservationNumber": "booking-com-9999999999",
    }


def test_confirmation_number_label(run_extractor):
    # Newer Booking.com bodies use `Confirmation number: NNN` (and
    # `Booking number NNN` further down) instead of the older bare
    # `Confirmation: NNN`. Both must be recognised or the
    # reservation drops the number and the file can't be filed.
    out = run_extractor("booking-com", "booking-com-confirmation-number-label.eml")
    assert set(out) == {"booking-com-8888888888.reservation.json"}
    assert (
        out["booking-com-8888888888.reservation.json"]["reservationNumber"]
        == "booking-com-8888888888"
    )
