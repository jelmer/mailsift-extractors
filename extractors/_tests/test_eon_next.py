"""Tests for the E.ON Next energy statement extractor."""

from __future__ import annotations


def test_statement(run_extractor):
    out = run_extractor("eon-next", "eon-next-statement.eml")
    assert set(out) == {"eon-next-A-00000000-202606.bill.json"}
    assert out["eon-next-A-00000000-202606.bill.json"] == {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "E.ON Next",
        "invoiceNumber": "A-00000000-202606",
        "accountName": "A-00000000",
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": 24.12,
            "priceCurrency": "GBP",
        },
        "paymentDueDate": "2026-06-01",
    }
