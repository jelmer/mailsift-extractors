"""Tests for the Swiftqueue NHS appointment extractor."""

from __future__ import annotations


def test_blood_test_confirmation_emits_event_reservation(run_extractor):
    out = run_extractor("swiftqueue", "swiftqueue-confirmation.eml")
    assert set(out) == {"swiftqueue-2024-12-06T0845.reservation.json"}
    res = out["swiftqueue-2024-12-06T0845.reservation.json"]
    assert res["@type"] == "EventReservation"
    assert res["reservationNumber"] == "swiftqueue-2024-12-06T0845"
    assert res["reservationFor"] == {
        "@type": "Event",
        "name": "Example Community Clinic",
        "startDate": "2024-12-06T08:45:00",
        "location": {
            "@type": "Place",
            "name": (
                "Example Community Clinic, 1 Example Street, London, EC1A 1AA, UK"
            ),
        },
    }
