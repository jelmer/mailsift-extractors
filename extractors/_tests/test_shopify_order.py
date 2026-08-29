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
    assert parcel["merchant"] == {"@type": "Organization", "name": "Patchplants"}


def test_shipment_records_delivery_status_and_url(run_extractor):
    out = run_extractor("shopify-order", "shopify-patch-shipped.eml")
    parcel = out["patchplants-15000000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "InTransit"
    # Merchant is an Organization on parcels, matching the dedicated
    # carrier extractors.
    assert parcel["merchant"] == {
        "@type": "Organization",
        "name": "Patchplants",
    }


def test_multi_shipment_emits_one_parcel_each(run_extractor):
    out = run_extractor("shopify-order", "shopify-multi-shipment.eml")
    assert set(out) == {
        "patchplants-15000000000010.parcel.json",
        "patchplants-H01ABC-1234567.parcel.json",
    }
    dpd = out["patchplants-15000000000010.parcel.json"]
    assert dpd["provider"]["@id"] == "dpd"
    assert dpd["orderNumber"] == "100003"
    # Hyphenated tracking numbers must survive intact.
    evri = out["patchplants-H01ABC-1234567.parcel.json"]
    assert evri["trackingNumber"] == "H01ABC-1234567"
    assert evri["provider"]["@id"] == "evri"


def test_out_for_delivery_emits_parcel(run_extractor):
    out = run_extractor("shopify-order", "shopify-out-for-delivery.eml")
    assert set(out) == {"thepihut-AB123456789GB.parcel.json"}
    parcel = out["thepihut-AB123456789GB.parcel.json"]
    assert parcel["trackingNumber"] == "AB123456789GB"
    assert parcel["provider"]["@id"] == "royal-mail"
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["orderNumber"] == "100004"
