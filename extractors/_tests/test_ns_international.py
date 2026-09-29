"""Tests for the NS International train booking extractor."""

from __future__ import annotations


def test_summary_only_confirmation_emits_a_single_leg(run_extractor):
    """The oldest fixture: mail body carries only the direction
    summary (`Outward` / origin / dest / dep / arr) with no
    Routedetails table. Falls back to one segment per direction.
    """
    out = run_extractor("ns-international", "ns-international-confirmation.eml")
    assert set(out) == {"ns-intl-HHHHHHH-outward-1.reservation.json"}
    res = out["ns-intl-HHHHHHH-outward-1.reservation.json"]
    assert res["@type"] == "TrainReservation"
    assert res["reservationNumber"] == "HHHHHHH-outward-1"
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


def test_modern_layout_emits_one_reservation_per_train(run_extractor):
    """Modern international layout: each train has a block with a
    departure time, station, track, train number, arrival time,
    station, track. We emit one `TrainReservation` per train, keyed by
    the train number.
    """
    out = run_extractor("ns-international", "ns-international-multi-train.eml")
    assert set(out) == {
        "ns-intl-MULTI01-outward-TGV8606.reservation.json",
        "ns-intl-MULTI01-outward-EST9339.reservation.json",
        "ns-intl-MULTI01-outward-IC2855.reservation.json",
    }
    first = out["ns-intl-MULTI01-outward-TGV8606.reservation.json"]
    assert first["reservationNumber"] == "MULTI01-outward-TGV8606"
    assert first["reservationFor"]["trainNumber"] == "TGV8606"
    assert first["reservationFor"]["departureStation"]["name"] == "Alphaville"
    assert first["reservationFor"]["arrivalStation"]["name"] == "Brookfield"
    assert first["reservationFor"]["departureTime"] == "2025-07-19T07:22:00"
    assert first["reservationFor"]["arrivalTime"] == "2025-07-19T11:07:00"
    # Only the first train we write carries the booking total.
    assert first["totalPrice"] == {
        "@type": "PriceSpecification",
        "price": 224.70,
        "priceCurrency": "EUR",
    }

    second = out["ns-intl-MULTI01-outward-EST9339.reservation.json"]
    assert second["reservationFor"]["trainNumber"] == "EST9339"
    assert second["reservationFor"]["arrivalPlatform"] == "13"
    assert "totalPrice" not in second

    third = out["ns-intl-MULTI01-outward-IC2855.reservation.json"]
    assert third["reservationFor"]["trainNumber"] == "IC2855"
    assert third["reservationFor"]["departurePlatform"] == "14"
    assert third["reservationFor"]["arrivalPlatform"] == "12"
    assert third["reservationFor"]["arrivalTime"] == "2025-07-19T15:57:00"


def test_legacy_layout_uses_routedetails_table(run_extractor):
    """Legacy layout: a summary block followed by a `Routedetails`
    table with per-stop V/D/A rows. The mail carries no train numbers,
    so segments are keyed by leg index (1, 2, 3).
    """
    out = run_extractor("ns-international", "ns-international-routedetails.eml")
    assert set(out) == {
        "ns-intl-RTDET02-outward-1.reservation.json",
        "ns-intl-RTDET02-outward-2.reservation.json",
        "ns-intl-RTDET02-outward-3.reservation.json",
    }
    first = out["ns-intl-RTDET02-outward-1.reservation.json"]
    assert first["reservationNumber"] == "RTDET02-outward-1"
    # Legacy mails don't carry train numbers.
    assert "trainNumber" not in first["reservationFor"]
    assert first["reservationFor"]["departureStation"]["name"] == "Alphaville"
    assert first["reservationFor"]["arrivalStation"]["name"] == "Midtown"
    assert first["reservationFor"]["departureTime"] == "2026-02-02T18:27:00"
    assert first["reservationFor"]["arrivalTime"] == "2026-02-02T19:23:00"
    # The class captured from the summary applies to every leg of the
    # direction.
    assert first["reservationFor"]["trainName"] == "Standard Class"
    assert first["totalPrice"]["price"] == 60.60

    second = out["ns-intl-RTDET02-outward-2.reservation.json"]
    assert second["reservationFor"]["departureStation"]["name"] == "Midtown"
    assert second["reservationFor"]["arrivalStation"]["name"] == "Newton Central"
    assert second["reservationFor"]["departureTime"] == "2026-02-02T19:35:00"
    assert "totalPrice" not in second

    third = out["ns-intl-RTDET02-outward-3.reservation.json"]
    assert third["reservationFor"]["departureStation"]["name"] == "Newton Central"
    assert third["reservationFor"]["arrivalStation"]["name"] == "Endpoint Centraal"
    assert third["reservationFor"]["arrivalTime"] == "2026-02-02T21:14:00"
