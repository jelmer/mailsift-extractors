"""Tests for the Yodel parcel-tracking extractor."""

from __future__ import annotations


def test_on_its_way_emits_in_transit(run_extractor):
    out = run_extractor("yodel", "yodel-on-its-way.eml")
    assert set(out) == {"yodel-JD0000000000000000.parcel.json"}
    parcel = out["yodel-JD0000000000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OnItsWay"
    assert parcel["trackingNumber"] == "JD0000000000000000"
    assert parcel["merchant"] == {
        "@type": "Organization",
        "name": "Voorbeeld Webshop",
    }


def test_out_for_delivery_window_and_reservation(run_extractor):
    out = run_extractor("yodel", "yodel-out-for-delivery.eml")
    assert set(out) == {
        "yodel-JD0000000000000000.parcel.json",
        "yodel-delivery-JD0000000000000000.reservation.json",
    }
    parcel = out["yodel-JD0000000000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["merchant"]["name"] == "Voorbeeld Webshop"
    assert parcel["expectedArrivalFrom"] == "2024-10-19T12:04:00"
    assert parcel["expectedArrivalUntil"] == "2024-10-19T14:04:00"

    reservation = out["yodel-delivery-JD0000000000000000.reservation.json"]
    assert reservation["reservationFor"]["startDate"] == "2024-10-19T12:04:00"


def test_delivered_emits_delivered_status(run_extractor):
    out = run_extractor("yodel", "yodel-delivered.eml")
    parcel = out["yodel-JD0000000000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
