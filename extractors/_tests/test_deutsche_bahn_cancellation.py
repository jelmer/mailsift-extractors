"""Tests for the Deutsche Bahn cancellation extractor."""

from __future__ import annotations

import email
import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"


def subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "deutsche-bahn-cancellation.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError("no subject_regex")


def test_manifest_accepts_cancellation_subjects():
    for eml in [
        "deutsche-bahn-cancellation.eml",
        "deutsche-bahn-cancellation-nl.eml",
    ]:
        with (CORPUS_DIR / eml).open("rb") as fh:
            subject = email.message_from_binary_file(fh)["Subject"]
        assert subject_regex().search(subject), subject


def test_cancellation_carries_only_the_order(run_extractor):
    out = run_extractor("deutsche-bahn-cancellation", "deutsche-bahn-cancellation.eml")
    assert out == {
        "deutsche-bahn-abc123.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "ABC123",
            "reservationStatus": "ReservationCancelled",
        }
    }


def test_dutch_cancellation(run_extractor):
    out = run_extractor(
        "deutsche-bahn-cancellation", "deutsche-bahn-cancellation-nl.eml"
    )
    assert out == {
        "deutsche-bahn-def456.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "DEF456",
            "reservationStatus": "ReservationCancelled",
        }
    }
