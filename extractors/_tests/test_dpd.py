"""Tests for the DPD parcel-tracking extractor.

DPD tracking numbers come space-separated in the body
("1500 0000 000 000"); the extractor strips the spaces so the parcels
target keys on a single token.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def test_expecting(run_extractor):
    out = run_extractor("dpd", "dpd-expecting.eml")
    assert set(out) == {"dpd-15000000000000.parcel.json"}
    assert out["dpd-15000000000000.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "15000000000000",
        "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
        "merchant": {"@type": "Organization", "name": "IKEA"},
        "deliveryStatus": "Scheduled",
    }


def test_out_for_delivery_today(run_extractor):
    out = run_extractor("dpd", "dpd-out-for-delivery.eml")
    assert set(out) == {"dpd-15000000000000.parcel.json"}
    assert out["dpd-15000000000000.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "15000000000000",
        "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
        "merchant": {"@type": "Organization", "name": "IKEA"},
        "deliveryStatus": "OutForDelivery",
        "expectedArrivalFrom": "2026-02-09T13:40:00",
        "expectedArrivalUntil": "2026-02-09T14:40:00",
    }


def test_out_for_delivery_takes_the_postcode_from_the_ics(run_extractor):
    out = run_extractor("dpd", "dpd-out-for-delivery-with-ics.eml")
    assert out == {
        "dpd-15000000000000.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "15000000000000",
            "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
            "merchant": {"@type": "Organization", "name": "IKEA"},
            "deliveryStatus": "OutForDelivery",
            "deliveryPostalCode": "CB1 2AB",
            "expectedArrivalFrom": "2026-02-09T13:40:00",
            "expectedArrivalUntil": "2026-02-09T14:40:00",
        }
    }


def test_delivered(run_extractor):
    out = run_extractor("dpd", "dpd-delivered.eml")
    assert out == {
        "dpd-15000000000000.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "15000000000000",
            "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
            "merchant": {"@type": "Organization", "name": "IKEA"},
            "deliveryStatus": "Delivered",
        }
    }


def test_ready_to_collect_counts_as_out_for_delivery(run_extractor):
    out = run_extractor("dpd", "dpd-ready-to-collect.eml")
    assert out["dpd-15000000000000.parcel.json"]["deliveryStatus"] == "OutForDelivery"


def test_missed_delivery_is_a_problem(run_extractor):
    out = run_extractor("dpd", "dpd-missed-you.eml")
    assert out["dpd-15000000000000.parcel.json"]["deliveryStatus"] == "OrderProblem"


@pytest.mark.parametrize(
    "subject",
    [
        "Your IKEA parcel is ready for you to collect from Example Store",
        "Your IKEA parcel is waiting for you at Example Store",
        "Act now - your IKEA parcel at Example Store will be returned unless collected",
        "Sorry we missed you",
        "We'll deliver your IKEA parcel on 5th July 2021",
    ],
)
def test_manifest_accepts(subject):
    for line in (EXTRACTORS_DIR / "dpd.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            assert re.search(json.loads(line.removeprefix("subject_regex: ")), subject)
            return
    raise AssertionError("dpd.yaml has no subject_regex")
