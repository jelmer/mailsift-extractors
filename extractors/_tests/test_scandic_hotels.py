"""Tests for the Scandic Hotels post-stay receipt extractor."""

from __future__ import annotations


def test_bilingual_receipt_emits_bill_and_pdf(run_extractor):
    out = run_extractor("scandic-hotels", "scandic-hotels-receipt.eml")
    assert set(out) == {
        "scandic-12345678.bill.json",
        "scandic-12345678.bill.pdf",
    }

    bill = out["scandic-12345678.bill.json"]
    assert bill["identifier"] == "12345678"
    assert bill["accountId"] == "12345678"
    assert bill["provider"] == {"@type": "Organization", "name": "Scandic Hotels"}
    assert bill["description"] == "Scandic Helsfyr, Oslo"
    assert bill["billingDate"] == "2025-06-15"

    assert out["scandic-12345678.bill.pdf"].startswith(b"%PDF")
