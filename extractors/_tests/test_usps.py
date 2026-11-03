"""Tests for the USPS Tracking notification extractor."""

from __future__ import annotations


def test_delivered_to_parcel_locker(run_extractor):
    out = run_extractor("usps", "usps-delivered.eml")
    assert set(out) == {"usps-9400100000000000000002.parcel.json"}
    parcel = out["usps-9400100000000000000002.parcel.json"]
    assert parcel["@type"] == "ParcelDelivery"
    assert parcel["trackingNumber"] == "9400100000000000000002"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "usps",
        "name": "USPS",
    }
    assert parcel["deliveryStatus"] == "Delivered"
    assert parcel["actualDeliveryTime"] == "2026-11-01T13:02:00"
    assert parcel["merchant"] == "EXAMPLE SHOP"
    assert parcel["trackingUrl"].endswith("tLabels=9400100000000000000002")
    # The delivery address stays out of the record.
    assert "HONOLULU" not in str(parcel)


def test_status_from_subject():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "usps.py"
    spec = importlib.util.spec_from_file_location("usps", path)
    usps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(usps)
    assert (
        usps.status_from_subject("USPS® Item Out for Delivery 9400") == "OutForDelivery"
    )
    assert (
        usps.status_from_subject("USPS® Item Delivered, Front Door/Porch 9400")
        == "Delivered"
    )
    assert usps.status_from_subject("USPS® Something new 9400") is None
