"""Tests for the Amazon orders / shipments extractor."""

from __future__ import annotations


def test_uk_ordered_emits_receipt_and_parcel(run_extractor):
    out = run_extractor("amazon", "amazon-uk-ordered.eml")
    assert set(out) == {
        "amazon-uk-111-1111111-1111111.parcel.json",
        "amazon-uk-111-1111111-1111111.receipt.json",
    }

    parcel = out["amazon-uk-111-1111111-1111111.parcel.json"]
    assert parcel["trackingNumber"] == "111-1111111-1111111"
    assert parcel["provider"]["@id"] == "amazon-uk"
    assert parcel["deliveryStatus"] == "OrderProcessing"

    receipt = out["amazon-uk-111-1111111-1111111.receipt.json"]
    assert receipt["merchant"] == "Amazon"
    assert receipt["orderNumber"] == "111-1111111-1111111"
    assert receipt["orderDate"] == "2026-06-24"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 26.93,
        "priceCurrency": "GBP",
    }
    assert len(receipt["orderedItem"]) == 1
    item = receipt["orderedItem"][0]
    assert item["orderQuantity"] == 1
    assert "Example Gadget X1" in item["orderedItem"]["name"]


def test_uk_dispatched_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-uk-dispatched.eml")
    assert set(out) == {"amazon-uk-111-1111111-1111111.parcel.json"}
    assert (
        out["amazon-uk-111-1111111-1111111.parcel.json"]["deliveryStatus"]
        == "OrderInTransit"
    )


def test_uk_delivered_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-uk-delivered.eml")
    assert set(out) == {"amazon-uk-333-3333333-3333333.parcel.json"}
    assert (
        out["amazon-uk-333-3333333-3333333.parcel.json"]["deliveryStatus"]
        == "OrderDelivered"
    )


def test_de_ordered_emits_receipt_and_parcel(run_extractor):
    out = run_extractor("amazon", "amazon-de-ordered.eml")
    assert set(out) == {
        "amazon-de-222-2222222-2222222.parcel.json",
        "amazon-de-222-2222222-2222222.receipt.json",
    }

    parcel = out["amazon-de-222-2222222-2222222.parcel.json"]
    assert parcel["trackingNumber"] == "222-2222222-2222222"
    assert parcel["provider"]["@id"] == "amazon-de"
    assert parcel["deliveryStatus"] == "OrderProcessing"

    receipt = out["amazon-de-222-2222222-2222222.receipt.json"]
    assert receipt["orderNumber"] == "222-2222222-2222222"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 31.05,
        "priceCurrency": "EUR",
    }


def test_de_dispatched_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-de-dispatched.eml")
    assert set(out) == {"amazon-de-222-2222222-2222222.parcel.json"}
    parcel = out["amazon-de-222-2222222-2222222.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderInTransit"
    assert parcel["provider"]["@id"] == "amazon-de"
