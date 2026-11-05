"""Tests for the DFDS ferry booking extractor."""

from __future__ import annotations


def test_return_booking_emits_a_reservation_per_crossing(run_extractor):
    out = run_extractor("dfds", "dfds.eml")
    assert set(out) == {
        "dfds-90000001-outward.reservation.json",
        "dfds-90000001-return.reservation.json",
    }
    outward = out["dfds-90000001-outward.reservation.json"]
    assert outward["reservationNumber"] == "90000001-outward"
    assert outward["reservationFor"]["departureTime"] == "2023-07-21T19:30:00"
    assert outward["reservationFor"]["departureBoatTerminal"]["name"] == "Alphaville"
    assert outward["reservationFor"]["arrivalBoatTerminal"]["name"] == "Springfield"
    assert outward["numSeats"] == 1

    ret = out["dfds-90000001-return.reservation.json"]
    assert ret["reservationNumber"] == "90000001-return"
    assert ret["reservationFor"]["departureTime"] == "2023-07-28T08:15:00"
    assert ret["reservationFor"]["departureBoatTerminal"]["name"] == "Springfield"
    # DFDS puts the arrival time on the linked PDF, not in the body.
    assert "arrivalTime" not in ret["reservationFor"]
