"""Tests for the Rapha order/dispatch extractor."""

from __future__ import annotations


def test_order_confirmation_emits_receipt(run_extractor):
    out = run_extractor("rapha", "rapha-order.eml")
    assert set(out) == {"rapha-999999999.receipt.json"}
    receipt = out["rapha-999999999.receipt.json"]
    assert receipt["merchant"] == "Rapha"
    assert receipt["orderNumber"] == "999999999"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 109.16,
        "priceCurrency": "GBP",
    }


def test_dispatch_emits_parcel_with_carrier_from_url(run_extractor):
    # Rapha exposes tracking via a carrier-hosted URL (`track.dpd.co.uk`
    # for DPD, etc). The extractor pulls both the tracking number and
    # the carrier id out of that URL.
    out = run_extractor("rapha", "rapha-dispatch.eml")
    assert set(out) == {"rapha-99999999999999.parcel.json"}
    parcel = out["rapha-99999999999999.parcel.json"]
    assert parcel["trackingNumber"] == "99999999999999"
    assert parcel["orderNumber"] == "999999999"
    assert parcel["merchant"] == "Rapha"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "dpd",
        "name": "DPD",
    }
