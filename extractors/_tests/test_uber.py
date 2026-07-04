"""Tests for the Uber rideshare / Uber Eats receipt extractor."""

from __future__ import annotations


def test_trip_emits_rideshare_receipt(run_extractor):
    out = run_extractor("uber", "uber-trip.eml")
    files = list(out.keys())
    assert len(files) == 1
    name = files[0]
    assert name.startswith("uber-trip-uber-") and name.endswith(".receipt.json")
    receipt = out[name]
    assert receipt["@type"] == "Order"
    assert receipt["merchant"] == {"@type": "Organization", "name": "Uber"}
    assert receipt["broker"] == {"@type": "Organization", "name": "Uber"}
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 9.50,
        "priceCurrency": "EUR",
    }
    assert receipt["orderDate"] == "2026-05-11"


def test_eats_emits_food_receipt(run_extractor):
    out = run_extractor("uber", "uber-eats.eml")
    files = list(out.keys())
    assert len(files) == 1
    name = files[0]
    assert name.startswith("uber-eats-example-sushi-") and name.endswith(
        ".receipt.json"
    )
    receipt = out[name]
    assert receipt["merchant"] == {
        "@type": "Organization",
        "name": "Example Sushi",
    }
    assert receipt["broker"]["name"] == "Uber Eats"
    assert receipt["priceSpecification"]["price"] == 34.60
    assert receipt["priceSpecification"]["priceCurrency"] == "EUR"
    assert receipt["orderDate"] == "2024-07-24"
