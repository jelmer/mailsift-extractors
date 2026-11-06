"""Tests for the Amtrak eTicket + receipt extractor."""

from __future__ import annotations


def test_roundtrip_emits_two_reservations_receipt_and_ticket(run_extractor):
    out = run_extractor("amtrak", "amtrak-roundtrip-confirmation.eml")
    assert set(out) == {
        "amtrak-AAABBB-170.reservation.json",
        "amtrak-AAABBB-2175.reservation.json",
        "amtrak-0000000000000.receipt.json",
        "amtrak-AAABBB.ticket.pdf",
    }
    outbound = out["amtrak-AAABBB-2175.reservation.json"]
    assert outbound["reservationNumber"] == "AAABBB"
    trip = outbound["reservationFor"]
    assert trip["trainNumber"] == "2175"
    assert trip["provider"] == {"@type": "Organization", "name": "Amtrak"}
    assert trip["departureStation"] == {
        "@type": "TrainStation",
        "name": "BOSTON (SOUTH STATION)",
        "address": "MA",
    }
    assert trip["arrivalStation"] == {
        "@type": "TrainStation",
        "name": "NEW YORK (PENN STATION)",
        "address": "NY",
    }
    assert trip["departureTime"] == "2020-02-21T17:20:00"

    return_leg = out["amtrak-AAABBB-170.reservation.json"]
    assert return_leg["reservationFor"]["trainNumber"] == "170"
    assert return_leg["reservationFor"]["departureTime"] == "2020-02-24T08:30:00"

    receipt = out["amtrak-0000000000000.receipt.json"]
    assert receipt["merchant"] == "Amtrak"
    assert receipt["orderNumber"] == "0000000000000"
    assert receipt["price"] == "315.00"
    assert receipt["priceCurrency"] == "USD"

    assert out["amtrak-AAABBB.ticket.pdf"].startswith(b"%PDF")
