"""Tests for the NS (Nederlandse Spoorwegen) invoice extractor.

Each invoice mail produces both a `.bill.json` (the invoice itself)
and a `.reservation.json` for the direct-debit date, so the user sees
"NS auto-debit (EUR X)" on their calendar.
"""

from __future__ import annotations


def test_invoice_emits_bill_and_calendar_event(run_extractor):
    out = run_extractor("ns", "ns-invoice.eml")
    assert set(out) == {
        "ns-400000000000.bill.json",
        "ns-debit-400000000000.reservation.json",
    }
    assert out["ns-400000000000.bill.json"] == {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Nederlandse Spoorwegen",
        "invoiceNumber": "400000000000",
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": 4.55,
            "priceCurrency": "EUR",
        },
        "paymentDueDate": "2024-12-05",
        "accountName": "0100000000",
    }
    assert out["ns-debit-400000000000.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "ns-debit-400000000000",
        "reservationFor": {
            "@type": "Event",
            "name": "NS auto-debit (€4.55)",
            "startDate": "2024-12-05T00:00:00",
            "endDate": "2024-12-05T23:59:00",
        },
    }
