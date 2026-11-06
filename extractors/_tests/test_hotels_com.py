"""Tests for the Hotels.com travel-confirmation extractor."""

from __future__ import annotations


def test_hotel_booking_emits_lodging_reservation(run_extractor):
    out = run_extractor("hotels-com", "hotels-com-confirmation.eml")
    assert set(out) == {"hotels-com-00000000000000.reservation.json"}

    reservation = out["hotels-com-00000000000000.reservation.json"]
    assert reservation["reservationNumber"] == "00000000000000"
    assert reservation["checkinTime"] == "2023-08-27"
    assert reservation["checkoutTime"] == "2023-08-29"
    assert reservation["bookingAgent"] == {
        "@type": "Organization",
        "name": "Hotels.com",
    }
    assert reservation["reservationFor"] == {
        "@type": "LodgingBusiness",
        "name": "Hotel MANI by AMANO",
        "address": {"@type": "PostalAddress", "addressLocality": "Berlin"},
    }
