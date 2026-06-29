"""Tests for the DPD parcel-tracking extractor.

DPD tracking numbers come space-separated in the body
("1500 0000 000 000"); the extractor strips the spaces so the parcels
target keys on a single token.
"""

from __future__ import annotations


def test_expecting(run_extractor):
    out = run_extractor("dpd", "dpd-expecting.eml")
    assert set(out) == {"dpd-15000000000000.parcel.json"}
    assert out["dpd-15000000000000.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "15000000000000",
        "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
        "deliveryStatus": "Scheduled",
    }


def test_out_for_delivery_today(run_extractor):
    out = run_extractor("dpd", "dpd-out-for-delivery.eml")
    assert set(out) == {
        "dpd-15000000000000.parcel.json",
        "dpd-delivery-15000000000000.reservation.json",
    }
    assert out["dpd-15000000000000.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "15000000000000",
        "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
        "deliveryStatus": "OutForDelivery",
        "expectedArrivalFrom": "2026-02-09T13:40:00",
        "expectedArrivalUntil": "2026-02-09T14:40:00",
    }
    assert out["dpd-delivery-15000000000000.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "dpd-delivery-15000000000000",
        "reservationFor": {
            "@type": "Event",
            "name": "DPD delivery",
            "startDate": "2026-02-09T13:40:00",
            "endDate": "2026-02-09T14:40:00",
        },
    }
