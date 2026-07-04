"""Tests for the Deliveroo order-confirmation extractor."""

from __future__ import annotations


def test_accepted_emits_receipt_and_eta(run_extractor):
    out = run_extractor("deliveroo", "deliveroo-accepted.eml")
    assert set(out) == {
        "deliveroo-50000000000.receipt.json",
        "deliveroo-delivery-50000000000.reservation.json",
    }
    receipt = out["deliveroo-50000000000.receipt.json"]
    assert receipt["@type"] == "Order"
    assert receipt["orderNumber"] == "deliveroo-50000000000"
    assert receipt["merchant"] == {"@type": "Organization", "name": "The Example Grill"}
    assert receipt["broker"] == {"@type": "Organization", "name": "Deliveroo"}
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 42.19,
        "priceCurrency": "GBP",
    }
    assert receipt["orderDate"] == "2025-09-14"
    assert receipt["orderedItem"] == [
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {"@type": "Product", "name": "Mixed Salad"},
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 6.90,
                "priceCurrency": "GBP",
            },
        },
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {"@type": "Product", "name": "Hummus"},
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 6.90,
                "priceCurrency": "GBP",
            },
        },
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {"@type": "Product", "name": "Grilled Halloumi"},
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 8.15,
                "priceCurrency": "GBP",
            },
        },
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {"@type": "Product", "name": "Shish Taouk"},
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 17.25,
                "priceCurrency": "GBP",
            },
        },
    ]

    reservation = out["deliveroo-delivery-50000000000.reservation.json"]
    assert reservation["reservationFor"]["name"] == "Deliveroo: The Example Grill"
    assert reservation["reservationFor"]["startDate"] == "2025-09-14T22:30:00"
    assert reservation["reservationFor"]["endDate"] == "2025-09-14T23:00:00"
