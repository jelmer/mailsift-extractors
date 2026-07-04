"""Tests for the FedEx parcel-tracking extractor."""

from __future__ import annotations


def test_on_the_way_emits_parcel_with_eta(run_extractor):
    out = run_extractor("fedex", "fedex-on-the-way.eml")
    assert set(out) == {"fedex-800000000000.parcel.json"}
    parcel = out["fedex-800000000000.parcel.json"]
    assert parcel["trackingNumber"] == "800000000000"
    assert parcel["deliveryStatus"] == "OnItsWay"
    assert parcel["expectedArrivalUntil"] == "2026-02-25"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "fedex",
        "name": "FedEx",
    }


def test_out_for_delivery_window_and_reservation(run_extractor):
    out = run_extractor("fedex", "fedex-out-for-delivery.eml")
    assert set(out) == {
        "fedex-800000000000.parcel.json",
        "fedex-delivery-800000000000.reservation.json",
    }
    parcel = out["fedex-800000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["expectedArrivalFrom"] == "2026-02-25T09:10:00"
    assert parcel["expectedArrivalUntil"] == "2026-02-25T13:10:00"
    reservation = out["fedex-delivery-800000000000.reservation.json"]
    assert reservation["reservationFor"]["startDate"] == "2026-02-25T09:10:00"
    assert reservation["reservationFor"]["endDate"] == "2026-02-25T13:10:00"


def test_delivered_records_actual_time(run_extractor):
    out = run_extractor("fedex", "fedex-delivered.eml")
    parcel = out["fedex-800000000000.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
    assert parcel["actualDeliveryTime"] == "2026-02-25T13:38:00"
