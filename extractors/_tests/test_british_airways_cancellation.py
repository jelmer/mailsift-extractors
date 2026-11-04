"""Tests for the British Airways booking cancellation extractor."""

from __future__ import annotations

import email
import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"


def subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "british-airways-cancellation.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError("no subject_regex")


def test_manifest_accepts_cancellation_subjects():
    for eml in [
        "british-airways-cancellation.eml",
        "british-airways-cancellation-2016.eml",
    ]:
        with (CORPUS_DIR / eml).open("rb") as fh:
            subject = email.message_from_binary_file(fh)["Subject"]
        assert subject_regex().search(subject), subject


def test_cancellation_carries_only_the_reference(run_extractor):
    out = run_extractor(
        "british-airways-cancellation", "british-airways-cancellation.eml"
    )
    assert out == {
        "ba-ABC123.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "ABC123",
            "reservationStatus": "ReservationCancelled",
        }
    }


def test_2016_cancellation(run_extractor):
    out = run_extractor(
        "british-airways-cancellation", "british-airways-cancellation-2016.eml"
    )
    assert out == {
        "ba-DEF456.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "DEF456",
            "reservationStatus": "ReservationCancelled",
        }
    }
