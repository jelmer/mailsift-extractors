"""Tests for the Airbnb receipt and cancellation extractor.

Airbnb `Reservation confirmed for ...` mails have schema.org
`LodgingReservation` markup and land via the generic `schema-ld`
extractor; this extractor covers the receipts and host cancellations,
which have no ld+json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_receipt_emits_order_with_confirmation_link(run_extractor):
    out = run_extractor("airbnb", "airbnb-receipt.eml")
    assert set(out) == {"airbnb-RCTESTID42.receipt.json"}
    receipt = out["airbnb-RCTESTID42.receipt.json"]
    assert receipt["merchant"] == "Airbnb"
    assert receipt["orderNumber"] == "RCTESTID42"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 834.50,
        "priceCurrency": "GBP",
    }
    # Confirmation code carries over so a reader can join the
    # receipt to the reservation schema-ld emitted from the
    # matching `Reservation confirmed` mail.
    assert receipt["confirmationNumber"] == "HMTESTCODE"
    assert receipt["orderDate"] == "2021-03-12"


def test_host_cancellation_replaces_the_booking(run_extractor):
    out = run_extractor("airbnb", "airbnb-cancelled-by-host.eml")
    assert out == {
        "airbnb-HMTESTCANC.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationStatus": "ReservationCancelled",
            "reservationNumber": "HMTESTCANC",
            "checkinTime": "2044-05-13",
            "checkoutTime": "2044-05-20",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Garden Studio (EX1)",
            },
        }
    }


def test_manifest_accepts_cancellations():
    for line in (EXTRACTORS_DIR / "airbnb.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            pattern = re.compile(json.loads(line.removeprefix("subject_regex: ")))
            break
    for subject in [
        "Your 2044-05-13 reservation was cancelled",
        "Your 2044-05-13 reservation was canceled",
    ]:
        assert pattern.search(subject), subject
    assert not pattern.search("Your 2044-05-13 reservation was cancelled - reply")
