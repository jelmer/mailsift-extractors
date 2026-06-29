"""Tests for the PostNL parcel-tracking extractor."""

from __future__ import annotations


def test_nieuw_emits_scheduled(run_extractor):
    out = run_extractor("postnl", "postnl-nieuw.eml")
    assert set(out) == {"postnl-3SAAAA0000000.parcel.json"}
    parcel = out["postnl-3SAAAA0000000.parcel.json"]
    assert parcel == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "3SAAAA0000000",
        "deliveryStatus": "Scheduled",
        "provider": {
            "@type": "Organization",
            "@id": "postnl",
            "name": "PostNL",
        },
        "merchant": {"@type": "Organization", "name": "Voorbeeld Webshop B.V."},
    }


def test_verstuurd_emits_on_its_way(run_extractor):
    out = run_extractor("postnl", "postnl-verstuurd.eml")
    parcel = out["postnl-3SCCCC000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OnItsWay"
    assert parcel["merchant"] == {
        "@type": "Organization",
        "name": "Voorbeeld Events",
    }


def test_onderweg_emits_out_for_delivery(run_extractor):
    out = run_extractor("postnl", "postnl-onderweg.eml")
    parcel = out["postnl-3SBBBB0000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["merchant"]["name"] == "Voorbeeld Webshop B.V."


def test_afgeleverd_emits_delivered(run_extractor):
    out = run_extractor("postnl", "postnl-afgeleverd.eml")
    parcel = out["postnl-3SBBBB0000000.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
