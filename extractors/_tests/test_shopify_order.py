"""Tests for the generic Shopify-templated order/shipment extractor."""

from __future__ import annotations


def test_confirmation_emits_receipt(run_extractor):
    out = run_extractor("shopify-order", "shopify-pihut-confirmed.eml")
    assert set(out) == {"thepihut-100002.receipt.json"}
    receipt = out["thepihut-100002.receipt.json"]
    # Merchant name comes from the sender's domain, not a hardcoded
    # vendor list - any Shopify-templated shop works.
    assert receipt["merchant"] == "Thepihut"
    assert receipt["orderNumber"] == "100002"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 42.30,
        "priceCurrency": "GBP",
    }
    assert len(receipt["orderedItem"]) == 1
    item = receipt["orderedItem"][0]
    assert item["orderQuantity"] == 1
    assert "Example Gadget" in item["orderedItem"]["name"]
    assert item["orderItemSubtotal"]["price"] == 38.40


def test_shipment_emits_parcel(run_extractor):
    out = run_extractor("shopify-order", "shopify-patch-shipped.eml")
    assert set(out) == {"patchplants-15000000000000.parcel.json"}
    parcel = out["patchplants-15000000000000.parcel.json"]
    assert parcel["trackingNumber"] == "15000000000000"
    # Carrier name is parsed out of the body, not assumed.
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "dpd",
        "name": "DPD",
    }
    assert parcel["orderNumber"] == "100001"
    assert parcel["merchant"] == "Patchplants"
