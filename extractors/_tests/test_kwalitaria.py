"""Tests for the Kwalitaria order-confirmation extractor."""

from __future__ import annotations


def test_confirmation_emits_receipt(run_extractor):
    out = run_extractor("kwalitaria", "kwalitaria-confirmation.eml")
    assert set(out) == {"kwalitaria-20000000.receipt.json"}
    receipt = out["kwalitaria-20000000.receipt.json"]
    assert receipt["@type"] == "Order"
    assert receipt["orderNumber"] == "kwalitaria-20000000"
    assert receipt["merchant"] == "Kwalitaria Example"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 22.05,
        "priceCurrency": "EUR",
    }
    assert receipt["orderedItem"] == [
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {
                "@type": "Product",
                "name": "2 porties",
                "description": "+ Frietsaus beker; + Normale friet",
            },
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 9.30,
                "priceCurrency": "EUR",
            },
        },
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {
                "@type": "Product",
                "name": "Kroket vega",
                "description": "+ Zacht bolletje wit",
            },
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 4.40,
                "priceCurrency": "EUR",
            },
        },
        {
            "@type": "OrderItem",
            "orderQuantity": 1,
            "orderedItem": {
                "@type": "Product",
                "name": "Frikandel vega",
                "description": "+ Ui/frietsaus/pindasaus; + Zacht bolletje wit",
            },
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 5.40,
                "priceCurrency": "EUR",
            },
        },
    ]
