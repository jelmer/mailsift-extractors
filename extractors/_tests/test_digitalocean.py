"""Tests for the DigitalOcean payment-receipt extractor."""

from __future__ import annotations


def test_monthly_payment_receipt(run_extractor):
    out = run_extractor("digitalocean", "digitalocean-payment.eml")
    assert set(out) == {"digitalocean-2025-09-01.receipt.json"}
    receipt = out["digitalocean-2025-09-01.receipt.json"]
    assert receipt["merchant"] == "DigitalOcean"
    # No invoice id in the body; the receipt date is the identifier.
    assert receipt["orderNumber"] == "2025-09-01"
    assert receipt["orderDate"] == "2025-09-01"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 28.8,
        "priceCurrency": "USD",
    }
