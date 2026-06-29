"""Tests for the DocTap GP-appointment extractor."""

from __future__ import annotations


def test_confirmation_emits_event_reservation(run_extractor):
    out = run_extractor("doctap", "doctap-confirmation.eml")
    assert set(out) == {"doctap-2024-07-04T1115.reservation.json"}
    res = out["doctap-2024-07-04T1115.reservation.json"]
    assert res["@type"] == "EventReservation"
    assert res["reservationNumber"] == "doctap-2024-07-04T1115"
    assert res["reservationFor"] == {
        "@type": "Event",
        "name": ("GP appointment, 15 mins with Dr Example"),
        "startDate": "2024-07-04T11:15:00",
        "location": {
            "@type": "Place",
            "name": "Example Clinic, 1 Example Street, London, EC1A 1AA",
        },
    }
