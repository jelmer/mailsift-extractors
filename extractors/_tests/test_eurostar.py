"""Tests for the Eurostar booking-confirmation extractor.

Booking confirmations cover both legs of a return trip; each leg
becomes its own TrainReservation.
"""

from __future__ import annotations


def test_return_trip(run_extractor):
    out = run_extractor("eurostar", "eurostar-confirmation.eml")
    assert set(out) == {
        "eurostar-EEEEEE-outbound.reservation.json",
        "eurostar-EEEEEE-return.reservation.json",
    }
    assert out["eurostar-EEEEEE-outbound.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": "eurostar-EEEEEE-outbound",
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {
                "@type": "TrainStation",
                "name": "London St Pancras Int'l",
            },
            "arrivalStation": {
                "@type": "TrainStation",
                "name": "Rotterdam Centraal",
            },
            "departureTime": "2026-06-10T18:04:00",
            "arrivalTime": "2026-06-10T22:32:00",
        },
    }
    ret = out["eurostar-EEEEEE-return.reservation.json"]
    assert ret["reservationNumber"] == "eurostar-EEEEEE-return"
    assert ret["reservationFor"]["departureStation"]["name"] == "Rotterdam Centraal"
    assert ret["reservationFor"]["arrivalStation"]["name"] == "London St Pancras Int'l"
    assert ret["reservationFor"]["departureTime"] == "2026-06-22T19:28:00"
    assert ret["reservationFor"]["arrivalTime"] == "2026-06-22T21:57:00"
