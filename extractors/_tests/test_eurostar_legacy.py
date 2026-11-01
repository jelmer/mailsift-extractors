"""Tests for the extractor of the 2017-2023 "Your Eurostar Ticket" mails."""

from __future__ import annotations


def person(name: str) -> dict:
    return {"@type": "Person", "name": name}


def ticket(name: str, coach: str, seat: str, number: str) -> dict:
    return {
        "@type": "Ticket",
        "underName": person(name),
        "ticketedSeat": {"@type": "Seat", "seatSection": coach, "seatNumber": seat},
        "ticketNumber": number,
    }


def reservation(slug: str, trip: dict, tickets: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": slug,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            **trip,
        },
        "underName": [t["underName"] for t in tickets],
        "reservedTicket": tickets,
    }


def station(name: str) -> dict:
    return {"@type": "TrainStation", "name": name}


def test_passengers_share_one_reservation_per_direction(run_extractor):
    out = run_extractor("eurostar-legacy", "eurostar-legacy-two-passengers.eml")
    assert out == {
        "eurostar-AAAAAA-outbound.reservation.json": reservation(
            "eurostar-AAAAAA-outbound",
            {
                "departureStation": station("Alpha International"),
                "arrivalStation": station("Beta Nord"),
                "departureTime": "2046-05-12T09:10:00",
                "arrivalTime": "2046-05-12T12:35:00",
            },
            [
                ticket("Other User", "3", "21", "100000001"),
                ticket("Test User", "3", "22", "100000003"),
            ],
        ),
        "eurostar-AAAAAA-return.reservation.json": reservation(
            "eurostar-AAAAAA-return",
            {
                "departureStation": station("Beta Nord"),
                "arrivalStation": station("Alpha International"),
                "departureTime": "2046-05-14T18:01:00",
                "arrivalTime": "2046-05-14T19:30:00",
            },
            [
                ticket("Other User", "7", "41", "100000002"),
                ticket("Test User", "7", "42", "100000004"),
            ],
        ),
    }


def test_train_numbers_and_ticket_number_on_its_own_line(run_extractor):
    out = run_extractor("eurostar-legacy", "eurostar-legacy-train-numbers.eml")
    assert out == {
        "eurostar-BBBBBB-outbound.reservation.json": reservation(
            "eurostar-BBBBBB-outbound",
            {
                "departureStation": station("Alpha International"),
                "arrivalStation": station("Gamma Central"),
                "departureTime": "2051-09-03T10:04:00",
                "arrivalTime": "2051-09-03T14:31:00",
                "trainNumber": "9001",
            },
            [ticket("Test User", "2", "11", "200000001")],
        ),
        "eurostar-BBBBBB-return.reservation.json": reservation(
            "eurostar-BBBBBB-return",
            {
                "departureStation": station("Gamma Central"),
                "arrivalStation": station("Alpha International"),
                "departureTime": "2051-09-11T16:58:00",
                "arrivalTime": "2051-09-11T19:27:00",
                "trainNumber": "9002",
            },
            [ticket("Test User", "8", "30", "200000002")],
        ),
    }
