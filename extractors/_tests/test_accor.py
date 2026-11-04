"""Tests for the Accor (ibis, Novotel, Mercure) reservation extractor."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_reservation_takes_times_from_the_policy_lines(run_extractor):
    # Accor states check-in and check-out only in the policy
    # paragraphs, and the total appears after the nightly rate.
    out = run_extractor("accor", "accor.eml")
    assert set(out) == {"accor-AAAAAAAA.reservation.json"}
    assert out["accor-AAAAAAAA.reservation.json"] == {
        "@context": {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        },
        "@type": "LodgingReservation",
        "reservationNumber": "accor-AAAAAAAA",
        "checkinTime": "2023-12-01T15:00:00",
        "checkoutTime": "2023-12-03T12:00:00",
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": "ibis budget Alphaville",
        },
        "pending:numAdults": 1,
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 106.20,
            "priceCurrency": "GBP",
        },
    }


def test_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("accor", "accor-cancellation.eml")
    assert out == {
        "accor-ZZZZZZZZ.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationStatus": "ReservationCancelled",
            "reservationNumber": "accor-ZZZZZZZZ",
            "checkinTime": "2046-07-20",
            "checkoutTime": "2046-07-22",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "ibis Exampleton Centre",
            },
        }
    }


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "accor.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    assert pattern.search(
        "Cancellation of your reservation: ibis Exampleton Centre No. ZZZZZZZZ"
    )
    assert not pattern.search(
        "Modification of your reservation: ibis Exampleton Centre No. ZZZZZZZZ"
    )
