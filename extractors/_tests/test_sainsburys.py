"""Tests for the Sainsbury's grocery extractor."""

from __future__ import annotations


def test_delivery_slot(run_extractor):
    out = run_extractor("sainsburys", "sainsburys-delivery.eml")
    assert set(out) == {"sainsburys-9999999999.reservation.json"}
    assert out["sainsburys-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Sainsbury's delivery",
            "startDate": "2026-03-17T11:37:00",
            "endDate": "2026-03-17T12:37:00",
            "location": {"@type": "Place", "address": "EC1A 1AA"},
        },
        "reservationNumber": "sainsburys-9999999999",
    }


def test_order_confirmation(run_extractor):
    out = run_extractor("sainsburys", "sainsburys-order.eml")
    assert set(out) == {
        "sainsburys-9999999999.reservation.json",
        "sainsburys-9999999999.bill.json",
    }
    assert out["sainsburys-9999999999.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Sainsbury's delivery",
            "startDate": "2026-08-17T11:00:00",
            "endDate": "2026-08-17T15:00:00",
            "location": {"@type": "Place", "address": "EC1A 1AA"},
        },
        "reservationNumber": "sainsburys-9999999999",
    }
    assert out["sainsburys-9999999999.bill.json"] == {
        "@context": "https://schema.org",
        "@type": "Invoice",
        "payee": "Sainsbury's",
        "invoiceNumber": "sainsburys-9999999999",
        "totalPaymentDue": {
            "@type": "PriceSpecification",
            "price": 101.70,
            "priceCurrency": "GBP",
        },
        "paymentDueDate": "2026-08-17",
    }


def test_receipt(run_extractor):
    out = run_extractor("sainsburys", "sainsburys-receipt.eml")
    assert set(out) == {"sainsburys-9999999999.receipt.json"}
    assert out["sainsburys-9999999999.receipt.json"] == {
        "@context": "https://schema.org",
        "@type": "Order",
        "orderNumber": "sainsburys-9999999999",
        "merchant": "Sainsbury's",
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": 99.80,
            "priceCurrency": "GBP",
        },
        "orderDate": "2026-08-17",
    }
