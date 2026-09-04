"""Tests for the BahnCard invoice extractor."""

from __future__ import annotations


def test_invoice_with_pdf(run_extractor):
    out = run_extractor("bahncard", "bahncard-invoice.eml")
    assert set(out) == {
        "bahncard-1-0000000E.bill.json",
        "bahncard-1-0000000E.bill.pdf",
    }

    bill = out["bahncard-1-0000000E.bill.json"]
    assert bill["payee"] == "Deutsche Bahn"
    assert bill["invoiceNumber"] == "1-0000000E"
    assert bill["issueDate"] == "2026-07-14"

    pdf = out["bahncard-1-0000000E.bill.pdf"]
    assert pdf.startswith(b"%PDF-")
