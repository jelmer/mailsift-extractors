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
        "deliveryStatus": "Delivered",
        "provider": {"@type": "Organization", "@id": "evri", "name": "Evri"},
        "merchant": {"@type": "Organization", "name": "Voorbeeld Webshop"},
    }


def test_got_parcel_with_newer_tracking_number(run_extractor):
    out = run_extractor("evri", "evri-got-parcel.eml")
    assert out == {
        "evri-T00N3A0000000001.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "T00N3A0000000001",
            "deliveryStatus": "OnItsWay",
            "provider": {"@type": "Organization", "@id": "evri", "name": "Evri"},
            "merchant": {"@type": "Organization", "name": "Example Shop"},
        }
    }


def test_expecting_parcel_with_curly_apostrophe(run_extractor):
    out = run_extractor("evri", "evri-expecting-parcel.eml")
    parcel = out["evri-H04EIA0000000002.parcel.json"]
    assert parcel["deliveryStatus"] == "Scheduled"
    assert parcel["merchant"] == {"@type": "Organization", "name": "Example Shop"}


def test_dropped_off_parcel_is_outgoing(run_extractor):
    assert run_extractor("evri", "evri-dropped-off.eml") == {
        "evri-H05QTA0000000003.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "H05QTA0000000003",
            "provider": {"@type": "Organization", "@id": "evri", "name": "Evri"},
            "deliveryStatus": "OnItsWay",
            "mailsift:direction": "outgoing",
        }
    }
