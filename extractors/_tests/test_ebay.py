"""Tests for the eBay purchase / update extractor."""

from __future__ import annotations


def test_order_confirmed_emits_receipt(run_extractor):
    out = run_extractor("ebay", "ebay-order-confirmed.eml")
    assert set(out) == {"ebay-42-99999-88888.receipt.json"}
    receipt = out["ebay-42-99999-88888.receipt.json"]
    assert receipt["merchant"] == "eBay"
    assert receipt["orderNumber"] == "42-99999-88888"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 12.34,
        "priceCurrency": "GBP",
    }
    assert receipt["orderedItem"] == [
        {
            "@type": "OrderItem",
            "orderedItem": {
                "@type": "Product",
                "name": "Example Widget for testing purposes only",
            },
            "orderQuantity": 1,
        }
    ]


def test_order_update_emits_parcel_with_tracking(run_extractor):
    # `Order update` mails carry a Tracking number but don't name the
    # carrier in the visible body. Record the provider as `ebay` so a
    # downstream tracker sink can look up the carrier from the number.
    out = run_extractor("ebay", "ebay-order-update.eml")
    assert set(out) == {"ebay-ABC123456789.parcel.json"}
    parcel = out["ebay-ABC123456789.parcel.json"]
    assert parcel["trackingNumber"] == "ABC123456789"
    assert parcel["orderNumber"] == "42-99999-88888"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "ebay",
        "name": "eBay",
    }
