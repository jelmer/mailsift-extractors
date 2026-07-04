"""Tests for the UPS parcel-tracking extractor."""

from __future__ import annotations


def test_shipping_notification_emits_on_its_way(run_extractor):
    out = run_extractor("ups", "ups-shipped.eml")
    assert set(out) == {"ups-1Z0000000000000000.parcel.json"}
    parcel = out["ups-1Z0000000000000000.parcel.json"]
    assert parcel["@type"] == "ParcelDelivery"
    assert parcel["trackingNumber"] == "1Z0000000000000000"
    assert parcel["deliveryStatus"] == "OnItsWay"
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "ups",
        "name": "UPS",
    }
    assert parcel["expectedArrivalUntil"] == "2026-01-09"


def test_out_for_delivery_includes_window_and_reservation(run_extractor):
    out = run_extractor("ups", "ups-out-for-delivery.eml")
    assert set(out) == {
        "ups-1Z0000000000000001.parcel.json",
        "ups-delivery-1Z0000000000000001.reservation.json",
    }
    parcel = out["ups-1Z0000000000000001.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["expectedArrivalFrom"] == "2026-04-30T08:30:00"
    assert parcel["expectedArrivalUntil"] == "2026-04-30T11:30:00"

    reservation = out["ups-delivery-1Z0000000000000001.reservation.json"]
    assert reservation == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "ups-delivery-1Z0000000000000001",
        "reservationFor": {
            "@type": "Event",
            "name": "UPS delivery",
            "startDate": "2026-04-30T08:30:00",
            "endDate": "2026-04-30T11:30:00",
        },
    }


def test_delivered_records_actual_time(run_extractor):
    out = run_extractor("ups", "ups-delivered.eml")
    parcel = out["ups-1Z0000000000000001.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
    assert parcel["actualDeliveryTime"] == "2026-04-30T11:13:00"
