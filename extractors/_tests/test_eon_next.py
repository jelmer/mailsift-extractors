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


def test_statement_with_pdf(run_extractor):
    out = run_extractor("eon-next", "eon-next-statement-with-pdf.eml")
    assert set(out) == {
        "eon-next-A-00000000-202608.bill.json",
        "eon-next-A-00000000-202608.bill.pdf",
    }
    bill = out["eon-next-A-00000000-202608.bill.json"]
    assert bill["invoiceNumber"] == "A-00000000-202608"
    assert bill["paymentDueDate"] == "2026-08-03"
    assert bill["totalPaymentDue"]["price"] == 24.12

    pdf = out["eon-next-A-00000000-202608.bill.pdf"]
    assert pdf.startswith(b"%PDF-")
