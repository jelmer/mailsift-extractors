"""Tests for the Google Play receipt extractor."""

from __future__ import annotations


def test_subscription_renewal(run_extractor):
    out = run_extractor("google-play", "google-play-receipt.eml")
    assert set(out) == {"google-play-GPA-0000-0000-0000-00000-3.receipt.json"}
    receipt = out["google-play-GPA-0000-0000-0000-00000-3.receipt.json"]
    assert receipt["merchant"] == "Google Play"
    assert receipt["orderNumber"] == "GPA.0000-0000-0000-00000..3"
    assert receipt["orderDate"] == "2026-06-19"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 1.59,
        "priceCurrency": "GBP",
    }
