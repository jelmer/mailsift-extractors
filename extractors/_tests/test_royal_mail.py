"""Tests for the Royal Mail parcel-tracking extractor.

Each Royal Mail mail produces a `.parcel.json`. The "due to be
delivered today" mail additionally produces a `.reservation.json` for
the time window so the delivery slot lands on the calendar.
"""

from __future__ import annotations


def test_on_its_way(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-on-its-way.eml")
    assert set(out) == {"royalmail-OL000000000GB.parcel.json"}
    assert out["royalmail-OL000000000GB.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "OL000000000GB",
        "provider": {
            "@type": "Organization",
            "@id": "royal-mail",
            "name": "Royal Mail",
        },
        "deliveryStatus": "OnItsWay",
    }


def test_out_for_delivery_today(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-out-for-delivery.eml")
    assert set(out) == {
        "royalmail-OL000000000GB.parcel.json",
        "royalmail-delivery-OL000000000GB.reservation.json",
    }
    assert out["royalmail-OL000000000GB.parcel.json"] == {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": "OL000000000GB",
        "provider": {
            "@type": "Organization",
            "@id": "royal-mail",
            "name": "Royal Mail",
        },
        "deliveryStatus": "OutForDelivery",
        "expectedArrivalFrom": "2024-08-16T09:30:00",
        "expectedArrivalUntil": "2024-08-16T13:30:00",
    }
    assert out["royalmail-delivery-OL000000000GB.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "royalmail-delivery-OL000000000GB",
        "reservationFor": {
            "@type": "Event",
            "name": "Royal Mail delivery",
            "startDate": "2024-08-16T09:30:00",
            "endDate": "2024-08-16T13:30:00",
        },
    }


def test_delivered(run_extractor):
    # Regression: the literal substring "delivered to" inside "delivered
    # today" used to misclassify "due to be delivered today" mails as
    # Delivered. The tightened check requires "delivered to your".
    out = run_extractor("royal-mail", "royal-mail-delivered.eml")
    assert set(out) == {"royalmail-OL000000000GB.parcel.json"}
    assert out["royalmail-OL000000000GB.parcel.json"]["deliveryStatus"] == "Delivered"
