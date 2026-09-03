"""Tests for the DHL Express shipment extractor."""

from __future__ import annotations


def test_on_its_way_uses_inline_shipper_and_generic_subject(run_extractor):
    # Some DHL notifications carry the generic subject `DHL On Demand
    # Delivery` with the actual status banner inside the body; the
    # extractor recognises it by scanning both subject and body.
    # The `from SHIPPER is on its way` phrase gives us the merchant.
    out = run_extractor("dhl", "dhl-on-its-way.eml")
    assert set(out) == {"dhl-9999999902.parcel.json"}
    parcel = out["dhl-9999999902.parcel.json"]
    assert parcel["trackingNumber"] == "9999999902"
    assert parcel["deliveryStatus"] == "OrderInTransit"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "dhl",
        "name": "DHL Express",
    }
    assert parcel["merchant"] == "EXAMPLE SHIPPER"


def test_delivered_uses_labelled_shipper_panel(run_extractor):
    # Later-status mails carry `Shipper Name\n<name>` in a data panel
    # rather than inline. Extractor picks the labelled form when
    # present.
    out = run_extractor("dhl", "dhl-delivered.eml")
    assert set(out) == {"dhl-9999999901.parcel.json"}
    parcel = out["dhl-9999999901.parcel.json"]
    assert parcel["trackingNumber"] == "9999999901"
    assert parcel["deliveryStatus"] == "OrderDelivered"
    assert parcel["merchant"] == "EXAMPLE SENDER LTD"
