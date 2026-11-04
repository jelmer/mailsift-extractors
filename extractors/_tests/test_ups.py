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


def test_out_for_delivery_includes_window(run_extractor):
    out = run_extractor("ups", "ups-out-for-delivery.eml")
    assert set(out) == {"ups-1Z0000000000000001.parcel.json"}
    parcel = out["ups-1Z0000000000000001.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    assert parcel["expectedArrivalFrom"] == "2026-04-30T08:30:00"
    assert parcel["expectedArrivalUntil"] == "2026-04-30T11:30:00"


def test_delivered_records_actual_time(run_extractor):
    out = run_extractor("ups", "ups-delivered.eml")
    parcel = out["ups-1Z0000000000000001.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
    assert parcel["actualDeliveryTime"] == "2026-04-30T11:13:00"


def test_records_the_sender(run_extractor):
    out = run_extractor("ups", "ups-delivered.eml")
    parcel = out["ups-1Z0000000000000001.parcel.json"]
    assert parcel["merchant"] == {"@type": "Organization", "name": "ACME PARTS CO"}


def test_older_my_choice_has_the_shipper_above_the_tracking_number(run_extractor):
    out = run_extractor("ups", "ups-my-choice-scheduled-2020.eml")
    parcel = out["ups-1Z0000000000000002.parcel.json"]
    assert parcel["merchant"] == {"@type": "Organization", "name": "EXAMPLE MUSIC GMBH"}


def test_quantum_view_delivery_notification(run_extractor):
    out = run_extractor("ups", "ups-quantum-view-delivered.eml")
    parcel = out["ups-1Z0000000000000003.parcel.json"]
    assert parcel["deliveryStatus"] == "Delivered"
    assert "merchant" not in parcel


def test_label_for_a_parcel_being_sent_is_skipped(run_extractor):
    assert run_extractor("ups", "ups-label-delivery.eml") == {}
