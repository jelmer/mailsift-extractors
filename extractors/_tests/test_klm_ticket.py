"""Tests for the KLM e-ticket delivery extractor."""

from __future__ import annotations


def test_return_trip_emits_both_legs_and_the_ticket_pdf(run_extractor):
    out = run_extractor("klm-ticket", "klm-ticket.eml")
    assert set(out) == {
        "klm-aaaaaa-1.reservation.json",
        "klm-aaaaaa-2.reservation.json",
        "klm-aaaaaa.ticket.pdf",
    }
    assert out["klm-aaaaaa-1.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "AAAAAA",
        "reservationFor": {
            "@type": "Flight",
            "airline": {"@type": "Airline", "name": "KLM", "iataCode": "KL"},
            "departureAirport": {
                "@type": "Airport",
                "name": "Alphaville",
                "iataCode": "AAA",
            },
            "arrivalAirport": {
                "@type": "Airport",
                "name": "Springfield",
                "iataCode": "BBB",
            },
            "departureTime": "2017-05-12T08:40:00",
        },
    }
    assert out["klm-aaaaaa-2.reservation.json"]["reservationFor"][
        "departureAirport"
    ] == {"@type": "Airport", "name": "Springfield", "iataCode": "BBB"}
    assert (
        out["klm-aaaaaa-2.reservation.json"]["reservationFor"]["departureTime"]
        == "2017-05-22T03:00:00"
    )
    ticket = out["klm-aaaaaa.ticket.pdf"]
    assert isinstance(ticket, bytes)
    assert ticket.startswith(b"%PDF")


def test_dutch_single_leg_keeps_the_bare_reference(run_extractor):
    # Dutch mail labels the reference `Boekingscode`, writes `om`
    # rather than `at`, and localises the month and day names.
    out = run_extractor("klm-ticket", "klm-ticket-dutch.eml")
    assert set(out) == {
        "klm-bbbbbb.reservation.json",
        "klm-bbbbbb.ticket.pdf",
    }
    reservation = out["klm-bbbbbb.reservation.json"]
    assert reservation["reservationNumber"] == "BBBBBB"
    assert reservation["reservationFor"]["departureAirport"] == {
        "@type": "Airport",
        "name": "Alphaville",
        "iataCode": "AAA",
    }
    assert reservation["reservationFor"]["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Voorbeeldstad",
        "iataCode": "CCC",
    }
    assert reservation["reservationFor"]["departureTime"] == "2019-09-08T17:25:00"
