"""Tests for the Hyperoptic payment-receipt extractor."""

from __future__ import annotations


def test_payment_receipt_with_pdf(run_extractor):
    out = run_extractor("hyperoptic", "hyperoptic-payment-receipt.eml")
    assert set(out) == {
        "hyperoptic-WP000000000000.receipt.json",
        "hyperoptic-WP000000000000.receipt.pdf",
    }

    receipt = out["hyperoptic-WP000000000000.receipt.json"]
    assert receipt["merchant"] == "Hyperoptic"
    assert receipt["orderNumber"] == "WP000000000000"
    assert receipt["orderDate"] == "2026-07-10"

    pdf = out["hyperoptic-WP000000000000.receipt.pdf"]
    assert pdf.startswith(b"%PDF-")
