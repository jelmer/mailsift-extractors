"""Tests for the bol.com extractor."""

from __future__ import annotations


def test_ordered_emits_receipt_and_parcel(run_extractor):
    out = run_extractor("bol-com", "bol-com-ordered.eml")
    assert set(out) == {
        "bol-C000000000.parcel.json",
        "bol-C000000000.receipt.json",
    }

    parcel = out["bol-C000000000.parcel.json"]
    assert parcel["trackingNumber"] == "bol-C000000000"
    assert parcel["orderNumber"] == "C000000000"
    assert parcel["provider"]["@id"] == "bol"
    assert parcel["deliveryStatus"] == "OrderProcessing"

    receipt = out["bol-C000000000.receipt.json"]
    assert receipt["orderNumber"] == "C000000000"
    assert receipt["merchant"] == {"@type": "Organization", "name": "bol"}
    assert receipt["seller"] == {
        "@type": "Organization",
        "name": "ExampleAudio.com",
    }
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 11.00,
        "priceCurrency": "EUR",
    }
    assert receipt["orderDate"] == "2026-05-28"


def test_shipped_emits_parcel_only(run_extractor):
    out = run_extractor("bol-com", "bol-com-shipped.eml")
    assert set(out) == {"bol-C000000000.parcel.json"}
    parcel = out["bol-C000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderInTransit"
    assert parcel["orderNumber"] == "C000000000"


def test_delivered_emits_parcel_only(run_extractor):
    out = run_extractor("bol-com", "bol-com-delivered.eml")
    assert set(out) == {"bol-C000000000.parcel.json"}
    assert out["bol-C000000000.parcel.json"]["deliveryStatus"] == "OrderDelivered"


def test_neighbours_emits_parcel_only(run_extractor):
    out = run_extractor("bol-com", "bol-com-neighbours.eml")
    assert set(out) == {"bol-C000000000.parcel.json"}
    assert out["bol-C000000000.parcel.json"]["deliveryStatus"] == "OrderDelivered"
