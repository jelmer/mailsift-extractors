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
    # The order-placed mail names the item between the order number
    # and the seller line.
    assert parcel["itemShipped"] == {
        "@type": "Product",
        "name": "Example Product",
    }

    receipt = out["bol-C000000000.receipt.json"]
    assert receipt["orderNumber"] == "C000000000"
    assert receipt["merchant"] == "bol"
    assert receipt["seller"] == "ExampleAudio.com"
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
    assert parcel["itemShipped"]["name"] == "Example Product"


def test_delivered_emits_parcel_only(run_extractor):
    out = run_extractor("bol-com", "bol-com-delivered.eml")
    assert set(out) == {"bol-C000000000.parcel.json"}
    parcel = out["bol-C000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderDelivered"
    assert parcel["itemShipped"]["name"] == "Example Product"


def test_neighbours_emits_parcel_only(run_extractor):
    out = run_extractor("bol-com", "bol-com-neighbours.eml")
    assert set(out) == {"bol-C000000000.parcel.json"}
    parcel = out["bol-C000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderDelivered"
    # The neighbours-drop template only carries an address, not the
    # item name -- no false itemShipped.
    assert "itemShipped" not in parcel


def test_legacy_2012_bestelling_emits_receipt_and_parcel(run_extractor):
    # Pre-2015 bol mail came from `noreply@bol.com`, used formal
    # `Bevestiging van uw bestelling <NNN>` subjects, and had bare
    # 10-digit order numbers (no `[AC]000` prefix).
    out = run_extractor("bol-com", "bol-com-legacy-ordered.eml")
    assert set(out) == {
        "bol-9999999900.parcel.json",
        "bol-9999999900.receipt.json",
    }
    parcel = out["bol-9999999900.parcel.json"]
    assert parcel["orderNumber"] == "9999999900"
    assert parcel["deliveryStatus"] == "OrderProcessing"
    assert parcel["itemShipped"]["name"] == "Letters To A Young Contrarian"
    receipt = out["bol-9999999900.receipt.json"]
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 14.99,
        "priceCurrency": "EUR",
    }
