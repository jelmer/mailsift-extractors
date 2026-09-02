"""Tests for the Airbnb payment-receipt extractor.

Airbnb `Reservation confirmed for ...` mails have schema.org
`LodgingReservation` markup and land via the generic `schema-ld`
extractor; this extractor covers the receipts, which have no
ld+json.
"""

from __future__ import annotations


def test_receipt_emits_order_with_confirmation_link(run_extractor):
    out = run_extractor("airbnb", "airbnb-receipt.eml")
    assert set(out) == {"airbnb-RCTESTID42.receipt.json"}
    receipt = out["airbnb-RCTESTID42.receipt.json"]
    assert receipt["merchant"] == "Airbnb"
    assert receipt["orderNumber"] == "RCTESTID42"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 834.50,
        "priceCurrency": "GBP",
    }
    # Confirmation code carries over so a reader can join the
    # receipt to the reservation schema-ld emitted from the
    # matching `Reservation confirmed` mail.
    assert receipt["confirmationNumber"] == "HMTESTCODE"
    assert receipt["orderDate"] == "2021-03-12"
