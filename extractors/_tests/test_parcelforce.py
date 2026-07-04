"""Tests for the Parcelforce delivery-notification extractor."""

from __future__ import annotations


def test_out_for_delivery_window_and_reservation(run_extractor):
    out = run_extractor("parcelforce", "parcelforce-out-for-delivery.eml")
    assert set(out) == {
        "parcelforce-JD0000000.parcel.json",
        "parcelforce-delivery-JD0000000.reservation.json",
    }
    parcel = out["parcelforce-JD0000000.parcel.json"]
    assert parcel == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "JD0000000",
        "deliveryStatus": "OutForDelivery",
        "provider": {
            "@type": "Organization",
            "@id": "parcelforce",
            "name": "Parcelforce",
        },
        "merchant": {"@type": "Organization", "name": "ACME PARTS LTD"},
        "expectedArrivalFrom": "2023-03-31T09:25:00",
        "expectedArrivalUntil": "2023-03-31T10:25:00",
    }
    reservation = out["parcelforce-delivery-JD0000000.reservation.json"]
    assert reservation["reservationFor"]["startDate"] == "2023-03-31T09:25:00"
    assert reservation["reservationFor"]["endDate"] == "2023-03-31T10:25:00"
