"""Tests for the OEBB (Austrian Rail) booking-confirmation extractor."""

from __future__ import annotations


def test_one_way_booking_emits_reservation_and_bill(run_extractor):
    out = run_extractor("oebb", "oebb-booking.eml")
    assert set(out) == {
        "oebb-0990000000000000.reservation.json",
        "oebb-536000000000000000.bill.json",
        "oebb-536000000000000000.bill.pdf",
    }

    reservation = out["oebb-0990000000000000.reservation.json"]
    assert reservation["reservationNumber"] == "0990000000000000"
    trip = reservation["reservationFor"]
    assert trip["provider"] == {"@type": "Organization", "name": "ÖBB"}
    assert trip["departureStation"] == {
        "@type": "TrainStation",
        "name": "Villach Hbf",
    }
    # The "Gl.5-10" platform tail is stripped.
    assert trip["arrivalStation"] == {
        "@type": "TrainStation",
        "name": "München Hbf",
    }
    assert trip["departureDay"] == "2023-08-01"

    bill = out["oebb-536000000000000000.bill.json"]
    assert bill["accountId"] == "0990000000000000"
    assert bill["identifier"] == "536000000000000000"
    assert bill["provider"] == {"@type": "Organization", "name": "ÖBB"}
    assert bill["billingDate"] == "2023-08-01"

    assert out["oebb-536000000000000000.bill.pdf"].startswith(b"%PDF")
