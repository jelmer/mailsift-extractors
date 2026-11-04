"""Tests for the Booking.com hotel-confirmation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


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


def test_number_from_property_mailto(run_extractor):
    out = run_extractor("booking-com", "booking-com-property-mailto.eml")
    assert set(out) == {"booking-com-7777777777.reservation.json"}
    assert (
        out["booking-com-7777777777.reservation.json"]["reservationNumber"]
        == "booking-com-7777777777"
    )


def test_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("booking-com", "booking-com-cancelled.eml")
    assert out == {
        "booking-com-9999999998.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationStatus": "ReservationCancelled",
            "reservationNumber": "booking-com-9999999998",
            "checkinTime": "2046-11-08",
            "checkoutTime": "2046-11-09",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Hotel Central",
                "address": "1 Example Square, Exampleton, EX1 1AA, United Kingdom",
            },
        }
    }


def test_cancellation_with_markup_is_left_to_schema_ld(run_extractor):
    assert run_extractor("booking-com", "booking-com-cancelled-ld-json.eml") == {}


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "booking-com.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    for subject in [
        "Booking cancelled for Example Hotel Central",
        "Booking canceled for Example Hotel Central",
    ]:
        assert pattern.search(subject), subject
