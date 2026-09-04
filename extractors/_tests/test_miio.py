"""Tests for the Miio EV charging invoice extractor."""

from __future__ import annotations


def test_invoice_with_pdf(run_extractor):
    out = run_extractor("miio", "miio-invoice.eml")
    assert set(out) == {
        "miio-00000000-0000-0000-0000-000000000000.receipt.json",
        "miio-00000000-0000-0000-0000-000000000000.receipt.pdf",
    }

    receipt = out["miio-00000000-0000-0000-0000-000000000000.receipt.json"]
    assert receipt["merchant"] == "Miio"
    assert receipt["orderNumber"] == "00000000-0000-0000-0000-000000000000"
    # Period pulled from body: "period up to 12/08/2026"
    assert receipt["orderDate"] == "2026-08-12"

    pdf = out["miio-00000000-0000-0000-0000-000000000000.receipt.pdf"]
    assert pdf.startswith(b"%PDF-")
