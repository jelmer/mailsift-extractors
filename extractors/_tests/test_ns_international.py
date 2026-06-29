"""Tests for the NS International train booking extractor."""

from __future__ import annotations


def test_outward_only_emits_one_reservation(run_extractor):
    out = run_extractor("ns-international", "ns-international-confirmation.eml")
    assert set(out) == {"ns-intl-HHHHHHH-outward.reservation.json"}
    res = out["ns-intl-HHHHHHH-outward.reservation.json"]
    assert res["@type"] == "TrainReservation"
    assert res["reservationNumber"] == "HHHHHHH-outward"
    assert res["reservationFor"] == {
        "@type": "TrainTrip",
        "provider": {"@type": "Organization", "name": "NS International"},
        "departureStation": {
            "@type": "TrainStation",
            "name": "Gent St Pieters",
        },
        "arrivalStation": {
            "@type": "TrainStation",
            "name": "Utrecht Centraal",
        },
        "departureTime": "2026-02-02T18:27:00",
        "arrivalTime": "2026-02-02T21:14:00",
        "trainName": "Standard Class",
    }
    assert res["totalPrice"] == {
        "@type": "PriceSpecification",
        "price": 60.60,
        "priceCurrency": "EUR",
    }
