"""Tests for the InPost sender-side extractor."""

from __future__ import annotations

PROVIDER = {"@type": "Organization", "@id": "inpost", "name": "InPost"}


def test_qr_code_ready_is_a_scheduled_outgoing_parcel(run_extractor):
    assert run_extractor("inpost", "inpost-qr-code-ready.eml") == {
        "inpost-JJD0000000000000000007.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "JJD0000000000000000007",
            "provider": PROVIDER,
            "deliveryStatus": "Scheduled",
            "mailsift:direction": "outgoing",
        }
    }


def test_waiting_in_their_locker_is_out_for_delivery(run_extractor):
    out = run_extractor("inpost", "inpost-ready-for-them.eml")
    parcel = out["inpost-JJD0000000000000000007.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"


def test_collected_carries_the_collection_time(run_extractor):
    assert run_extractor("inpost", "inpost-collected.eml") == {
        "inpost-JJD0000000000000000007.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "JJD0000000000000000007",
            "provider": PROVIDER,
            "deliveryStatus": "Delivered",
            "mailsift:direction": "outgoing",
            "actualDeliveryTime": "2026-07-12T20:46:00",
        }
    }
