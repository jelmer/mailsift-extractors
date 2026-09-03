"""Tests for the John Pye Auctions invoice extractor."""

from __future__ import annotations


def test_new_invoice_subject_carries_amount(run_extractor):
    # The invoice number, amount and currency are all in the subject
    # on the `New Invoice` mail; the body is just a payment link.
    out = run_extractor("john-pye-auctions", "john-pye-auctions-invoice.eml")
    assert set(out) == {"john-pye-auctions-91247783.receipt.json"}
    receipt = out["john-pye-auctions-91247783.receipt.json"]
    assert receipt["merchant"] == "John Pye Auctions"
    assert receipt["orderNumber"] == "91247783"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 112.60,
        "priceCurrency": "GBP",
    }
