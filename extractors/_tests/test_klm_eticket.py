"""Tests for the KLM e-ticket ("Ticket voor uw reis") extractor."""

from __future__ import annotations


def test_four_segment_eticket_emits_four_reservations(run_extractor):
    out = run_extractor("klm-eticket", "klm-eticket.eml")
    assert set(out) == {
        "klm-AAAAAA-KL1012.reservation.json",
        "klm-AAAAAA-KL1155.reservation.json",
        "klm-AAAAAA-KL1154.reservation.json",
        "klm-AAAAAA-KL1017.reservation.json",
    }

    leg1 = out["klm-AAAAAA-KL1012.reservation.json"]
    assert leg1["@context"] == {
        "@vocab": "https://schema.org/",
        "pending": "https://pending.schema.org/",
    }
    assert leg1["reservationNumber"] == "AAAAAA"
    assert leg1["ticketNumber"] == "0740000000000"
    assert leg1["underName"] == {"@type": "Person", "name": "Joe Example"}
    flight1 = leg1["reservationFor"]
    assert flight1["flightNumber"] == "1012"
    assert flight1["airline"] == {
        "@type": "Airline",
        "iataCode": "KL",
        "name": "KLM Royal Dutch Airlines",
    }
    assert flight1["departureAirport"] == {
        "@type": "Airport",
        "name": "Heathrow Airport",
        "iataCode": "LHR",
        "address": "Londen",
    }
    assert flight1["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Schiphol Airport",
        "iataCode": "AMS",
        "address": "Amsterdam",
    }
    assert flight1["departureTime"] == "2026-09-21T17:10:00"
    assert flight1["arrivalTime"] == "2026-09-21T19:30:00"
    assert flight1["pending:cabinClass"] == "Economy Class"
    assert flight1["pending:bookingClass"] == "Q"


def test_eticket_captures_per_segment_cabin_and_booking_class(run_extractor):
    """Segment 3 is Business / J while the others are Economy: the
    parser must read the cabin + booking-class lines from each segment
    rather than cache the first hit.
    """
    out = run_extractor("klm-eticket", "klm-eticket.eml")
    leg3 = out["klm-AAAAAA-KL1154.reservation.json"]
    flight3 = leg3["reservationFor"]
    assert flight3["pending:cabinClass"] == "Business Class"
    assert flight3["pending:bookingClass"] == "J"
    assert flight3["departureAirport"]["iataCode"] == "TRD"
    assert flight3["arrivalAirport"]["iataCode"] == "AMS"
    assert flight3["departureTime"] == "2026-09-28T17:10:00"
    assert flight3["arrivalTime"] == "2026-09-28T19:25:00"
