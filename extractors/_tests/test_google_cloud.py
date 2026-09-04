"""Tests for the Google Cloud monthly-invoice extractor."""

from __future__ import annotations


def test_monthly_invoice_with_pdf(run_extractor):
    out = run_extractor("google-cloud", "google-cloud-invoice.eml")
    assert set(out) == {
        "google-cloud-0000000000.bill.json",
        "google-cloud-0000000000.bill.pdf",
    }

    bill = out["google-cloud-0000000000.bill.json"]
    assert bill["payee"] == "Google Cloud"
    assert bill["invoiceNumber"] == "0000000000"
    assert bill["issueDate"] == "2026-09-02"

    pdf = out["google-cloud-0000000000.bill.pdf"]
    assert pdf.startswith(b"%PDF-")
