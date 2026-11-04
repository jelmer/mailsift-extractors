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


def test_modification_replaces_the_booking(run_extractor):
    # The modification repeats the confirmation in the older layout,
    # with the stay written month first and the guests on their own line.
    out = run_extractor("accor", "accor-modification.eml")
    assert out == {
        "accor-YYYYYYYY.reservation.json": {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "LodgingReservation",
            "reservationNumber": "accor-YYYYYYYY",
            "checkinTime": "2046-12-07T15:00:00",
            "checkoutTime": "2046-12-08T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "ibis budget Exampleton",
            },
            "pending:numAdults": 2,
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 40.00,
                "priceCurrency": "GBP",
            },
        }
    }


def test_missing_checkin_policy_gives_dates_only(run_extractor):
    out = run_extractor("accor", "accor-confirmation-no-checkin-policy.eml")
    assert out == {
        "accor-XXXXXXXX.reservation.json": {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "LodgingReservation",
            "reservationNumber": "accor-XXXXXXXX",
            "checkinTime": "2046-07-20",
            "checkoutTime": "2046-07-21",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "ibis Exampleton Centre",
            },
            "pending:numAdults": 3,
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 180.00,
                "priceCurrency": "EUR",
            },
        }
    }


def test_manifest_accepts_cancellations_and_modifications():
    for line in (EXTRACTORS_DIR / "accor.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    assert pattern.search(
        "Cancellation of your reservation: ibis Exampleton Centre No. ZZZZZZZZ"
    )
    assert pattern.search(
        "Modification of your reservation: ibis Exampleton Centre No. ZZZZZZZZ"
    )
    assert not pattern.search("Your online check-in is confirmed: ibis Exampleton")
