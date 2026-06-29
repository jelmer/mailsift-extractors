"""Tests for the KPN Mobiel invoice extractor."""

from __future__ import annotations


def test_invoice(run_extractor):
    out = run_extractor("kpn-mobiel", "kpn-mobiel-invoice.eml")
    assert set(out) == {"kpn-mobiel-10000000000-202508.bill.json"}
    assert out["kpn-mobiel-10000000000-202508.bill.json"] == {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "KPN Mobiel",
        "invoiceNumber": "10000000000-202508",
        "accountName": "10000000000",
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": 16.95,
            "priceCurrency": "EUR",
        },
        "paymentDueDate": "2025-08-26",
    }
