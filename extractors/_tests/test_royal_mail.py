"""Tests for the Royal Mail parcel-tracking extractor.

Each Royal Mail mail produces a `.parcel.json`. The "due to be
delivered today" mail carries the time window on the same file
(`expectedArrivalFrom`/`Until`).
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
        "deliveryStatus": "OutForDelivery",
        "merchant": {"@type": "Organization", "name": "Vision Direct"},
        "expectedArrivalFrom": "2024-08-16T09:30:00",
        "expectedArrivalUntil": "2024-08-16T13:30:00",
    }


def test_delivered(run_extractor):
    # Regression: the literal substring "delivered to" inside "delivered
    # today" used to misclassify "due to be delivered today" mails as
    # Delivered. The tightened check requires "delivered to your".
    out = run_extractor("royal-mail", "royal-mail-delivered.eml")
    assert set(out) == {"royalmail-OL000000000GB.parcel.json"}
    assert out["royalmail-OL000000000GB.parcel.json"]["deliveryStatus"] == "Delivered"


def outgoing(tracking: str, status: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {
            "@type": "Organization",
            "@id": "royal-mail",
            "name": "Royal Mail",
        },
        "deliveryStatus": status,
        "mailsift:direction": "outgoing",
    }


def test_locker_drop_off_is_outgoing(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-dropped-off.eml")
    assert out == {
        "royalmail-OM000000001GB.parcel.json": outgoing("OM000000001GB", "OnItsWay")
    }


def test_collection_confirmation_lists_every_item(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-collection-confirmation.eml")
    assert out == {
        "royalmail-OT000000002GB.parcel.json": outgoing("OT000000002GB", "Scheduled"),
        "royalmail-OT000000003GB.parcel.json": outgoing("OT000000003GB", "Scheduled"),
    }


def test_completed_collection_is_on_its_way(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-collection-completed.eml")
    assert out == {
        "royalmail-OS000000004GB.parcel.json": outgoing("OS000000004GB", "OnItsWay")
    }


def test_failed_collection_is_a_problem(run_extractor):
    out = run_extractor("royal-mail", "royal-mail-collection-failed.eml")
    assert out == {
        "royalmail-OT000000002GB.parcel.json": outgoing("OT000000002GB", "OrderProblem")
    }
