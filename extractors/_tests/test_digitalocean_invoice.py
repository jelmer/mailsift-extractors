"""Tests for the DigitalOcean monthly-invoice extractor."""

from __future__ import annotations


def test_monthly_invoice_with_pdf(run_extractor):
    out = run_extractor("digitalocean-invoice", "digitalocean-invoice.eml")
    assert set(out) == {
        "digitalocean-invoice-2026-06.receipt.json",
        "digitalocean-invoice-2026-06.receipt.pdf",
    }

    receipt = out["digitalocean-invoice-2026-06.receipt.json"]
    assert receipt["merchant"] == "DigitalOcean"
    assert receipt["orderNumber"] == "2026-06"
    assert receipt["orderDate"] == "2026-07-01"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 28.8,
        "priceCurrency": "USD",
    }

    pdf = out["digitalocean-invoice-2026-06.receipt.pdf"]
    assert pdf.startswith(b"%PDF-")
