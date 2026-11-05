"""Tests for the John Pye Auctions invoice extractor."""

from __future__ import annotations


def test_new_invoice_subject_carries_amount(run_extractor):
    # The invoice number, amount and currency are all in the subject
    # on the `New Invoice` mail; the body is just a payment link.
    out = run_extractor("john-pye-auctions", "john-pye-auctions-invoice.eml")
    assert set(out) == {"john-pye-auctions-90000003.receipt.json"}
    receipt = out["john-pye-auctions-90000003.receipt.json"]
    assert receipt["merchant"] == "John Pye Auctions"
    assert receipt["orderNumber"] == "90000003"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 112.60,
        "priceCurrency": "GBP",
    }


def test_new_invoice_without_amount(run_extractor):
    # Since late 2026 the subject drops the "for £X GBP" suffix and the
    # body carries no amount either; emit the receipt without a price.
    out = run_extractor("john-pye-auctions", "john-pye-auctions-invoice-no-amount.eml")
    assert out == {
        "john-pye-auctions-90000004.receipt.json": {
            "@context": "https://schema.org",
            "@type": "Order",
            "merchant": "John Pye Auctions",
            "orderNumber": "90000004",
            "orderDate": "2026-10-03",
        }
    }
