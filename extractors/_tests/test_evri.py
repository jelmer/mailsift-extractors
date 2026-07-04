"""Tests for the Evri parcel-tracking extractor."""

from __future__ import annotations


def test_collected_emits_parcel_with_merchant(run_extractor):
    out = run_extractor("evri", "evri-collected.eml")
    assert set(out) == {"evri-H0000A0000000000.parcel.json"}
    parcel = out["evri-H0000A0000000000.parcel.json"]
    assert parcel == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "H0000A0000000000",
        "deliveryStatus": "InTransit",
        "provider": {"@type": "Organization", "@id": "evri", "name": "Evri"},
        "merchant": {"@type": "Organization", "name": "Voorbeeld Webshop"},
    }
