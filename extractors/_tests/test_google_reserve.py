"""Tests for the Google Reserve restaurant-confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_food_reservation(run_extractor):
    out = run_extractor("google-reserve", "google-reserve-confirmation.eml")
    assert set(out) == {"google-reserve-0000-0000-0000-0000.reservation.json"}
    assert out["google-reserve-0000-0000-0000-0000.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "startTime": "2026-04-17T19:45:00+01:00",
        "endTime": "2026-04-17T21:15:00+01:00",
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": "The Example Bistro",
            "address": "1 Example Lane, EC1A 1AA, GB",
        },
        "partySize": 2,
        "reservationNumber": "google-reserve-0000-0000-0000-0000",
    }


def test_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("google-reserve", "google-reserve-cancelled.eml")
    assert out == {
        "google-reserve-0000-0000-0000-0001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FoodEstablishmentReservation",
            "startTime": "2046-10-20T13:00:00+02:00",
            "endTime": "2046-10-20T15:30:00+02:00",
            "reservationFor": {
                "@type": "FoodEstablishment",
                "name": "The Example Bistro",
                "address": "1 Example Lane, Exampleton, 0000 AA, NL",
            },
            "partySize": 3,
            "reservationStatus": "ReservationCancelled",
            "reservationNumber": "google-reserve-0000-0000-0000-0001",
        }
    }


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "google-reserve.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    for subject in [
        "Your reservation at The Example Bistro is canceled",
        "Your reservation at The Example Bistro has been cancelled",
        "Your reservation at The Example Bistro is confirmed",
    ]:
        assert pattern.search(subject), subject
