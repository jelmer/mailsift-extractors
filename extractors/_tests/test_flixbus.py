"""Tests for the FlixBus payment-proof extractor."""

from __future__ import annotations


def test_payment_proof_with_pdf(run_extractor):
    out = run_extractor("flixbus", "flixbus-payment-proof.eml")
    assert set(out) == {
        "flixbus-0000000000.receipt.json",
        "flixbus-0000000000.receipt.pdf",
    }

    receipt = out["flixbus-0000000000.receipt.json"]
    assert receipt["merchant"] == "FlixBus"
    assert receipt["orderNumber"] == "0000000000"
    assert receipt["orderDate"] == "2026-08-15"

    pdf = out["flixbus-0000000000.receipt.pdf"]
    assert pdf.startswith(b"%PDF-")
