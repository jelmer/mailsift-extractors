"""Tests for the Eurostar ticket-delivery extractor."""

from __future__ import annotations


def test_single_leg_grounds_the_year_on_the_mail_date(run_extractor):
    # The short date form (`Mon, 30 October`) carries no year.
    out = run_extractor("eurostar-tickets", "eurostar-tickets.eml")
    assert set(out) == {"eurostar-eeeeee-1.reservation.json"}
    assert out["eurostar-eeeeee-1.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": "EEEEEE-1",
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {
                "@type": "TrainStation",
                "name": "Beta Central",
            },
            "arrivalStation": {
                "@type": "TrainStation",
                "name": "Alpha International",
            },
            "departureTime": "2023-10-30T19:28:00",
            "arrivalTime": "2023-10-30T21:57:00",
            "trainNumber": "1001",
        },
        "reservedTicket": {
            "@type": "Ticket",
            "ticketedSeat": {
                "@type": "Seat",
                "seatNumber": "11",
                "seatSection": "4",
            },
        },
    }


def test_connection_emits_one_reservation_per_leg(run_extractor):
    # A journey with a change is numbered `Return (1/2)`, `(2/2)`; each
    # leg is its own reservation.
    out = run_extractor("eurostar-tickets", "eurostar-tickets-connection.eml")
    assert set(out) == {
        "eurostar-ffffff-1.reservation.json",
        "eurostar-ffffff-2.reservation.json",
        "eurostar-ffffff-3.reservation.json",
    }
    second = out["eurostar-ffffff-2.reservation.json"]
    assert second["reservationNumber"] == "FFFFFF-2"
    assert second["reservationFor"]["departureStation"]["name"] == "Beta Central"
    assert second["reservationFor"]["arrivalStation"]["name"] == "Gamma Midi"
    assert second["reservationFor"]["departureTime"] == "2024-11-26T06:58:00"
    assert second["reservationFor"]["arrivalTime"] == "2024-11-26T08:08:00"
    assert second["reservationFor"]["trainNumber"] == "1002"
    assert second["reservedTicket"]["ticketedSeat"] == {
        "@type": "Seat",
        "seatNumber": "13",
        "seatSection": "5",
    }
    third = out["eurostar-ffffff-3.reservation.json"]
    assert third["reservationFor"]["trainNumber"] == "1003"
    assert third["reservationFor"]["departureTime"] == "2024-11-26T08:52:00"


def test_short_date_rolls_into_the_next_year(run_extractor):
    # Booked in December for a February journey: with no year on the
    # date line, grounding on the mail's own year would put the trip
    # ten months in the past.
    out = run_extractor("eurostar-tickets", "eurostar-tickets-year-rollover.eml")
    assert set(out) == {"eurostar-gggggg-1.reservation.json"}
    reservation = out["eurostar-gggggg-1.reservation.json"]
    assert reservation["reservationFor"]["departureTime"] == "2026-02-06T08:01:00"
    assert reservation["reservationFor"]["arrivalTime"] == "2026-02-06T11:30:00"
