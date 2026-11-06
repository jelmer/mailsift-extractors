"""Tests for the LNER rail-booking extractor."""

from __future__ import annotations


def test_return_booking_emits_two_reservations_and_ticket(run_extractor):
    out = run_extractor("lner", "lner-return-booking.eml")
    assert set(out) == {
        "lner-aaabbbcc11-outward.reservation.json",
        "lner-aaabbbcc11-return.reservation.json",
        "eticket-aaabbbcc11-1-std-1-0.ticket.pdf",
    }

    outward = out["lner-aaabbbcc11-outward.reservation.json"]
    assert outward["reservationNumber"] == "AAABBBCC11"
    trip = outward["reservationFor"]
    assert trip["provider"] == {"@type": "Organization", "name": "LNER"}
    assert trip["departureStation"] == {
        "@type": "TrainStation",
        "name": "London Kings Cross",
    }
    assert trip["arrivalStation"] == {
        "@type": "TrainStation",
        "name": "Doncaster",
    }
    assert trip["departureTime"] == "2022-06-02T19:03:00"
    assert trip["arrivalTime"] == "2022-06-02T20:40:00"

    ret = out["lner-aaabbbcc11-return.reservation.json"]
    ret_trip = ret["reservationFor"]
    assert ret_trip["departureStation"]["name"] == "Doncaster"
    assert ret_trip["arrivalStation"]["name"] == "London Kings Cross"
    assert ret_trip["departureTime"] == "2022-06-06T14:27:00"
    assert ret_trip["arrivalTime"] == "2022-06-06T16:22:00"

    assert out["eticket-aaabbbcc11-1-std-1-0.ticket.pdf"].startswith(b"%PDF")
