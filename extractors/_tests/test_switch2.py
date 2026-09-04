"""Tests for the Switch2 energy-statement extractor."""

from __future__ import annotations


def test_payment(run_extractor):
    out = run_extractor("switch2", "switch2-payment.eml")
    assert set(out) == {"switch2-00000000000000000000000000000000.bill.json"}
    assert out["switch2-00000000000000000000000000000000.bill.json"] == {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Switch2 Energy",
        "invoiceNumber": "00000000000000000000000000000000",
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": 70.81,
            "priceCurrency": "GBP",
        },
        "paymentDueDate": "2026-06-04",
    }
