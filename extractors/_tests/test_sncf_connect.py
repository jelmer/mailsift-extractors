"""Tests for the SNCF Connect trip receipt extractor."""

from __future__ import annotations


def test_trip_emits_receipt(run_extractor):
    out = run_extractor("sncf-connect", "sncf-connect-trip.eml")
    assert set(out) == {"sncf-connect-TESTPN.receipt.json"}
    receipt = out["sncf-connect-TESTPN.receipt.json"]
    assert receipt["merchant"] == "SNCF Connect"
    assert receipt["orderNumber"] == "TESTPN"
    # Origin - destination taken from the subject (the body has no
    # station labels, only station-referenced payment metadata).
    assert receipt["description"] == "Bordeaux-Saint-Jean - Paris Montparnasse"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 104.00,
        "priceCurrency": "EUR",
    }
    assert receipt["orderDate"] == "2025-08-16"
