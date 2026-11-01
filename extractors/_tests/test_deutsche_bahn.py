"""Tests for the Deutsche Bahn booking-confirmation extractor."""

from __future__ import annotations

DB = {"@type": "Organization", "name": "Deutsche Bahn"}
PASSENGER = {"@type": "Person", "name": "Test User"}


def station(name: str) -> dict:
    return {"@type": "TrainStation", "name": name}


def seat(section: str, number: str, kind: str = "Seat") -> dict:
    return {
        "@type": "Ticket",
        "ticketedSeat": {
            "@type": "Seat",
            "seatNumber": number,
            "seatingType": kind,
            "seatSection": section,
        },
    }


def leg(
    number: str, train: str, origin: str, destination: str, times, platforms, **extra
) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": number,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": DB,
            "trainNumber": train,
            "departureStation": station(origin),
            "arrivalStation": station(destination),
            "departureTime": times[0],
            "arrivalTime": times[1],
            "departurePlatform": platforms[0],
            "arrivalPlatform": platforms[1],
        },
        **extra,
    }


def test_night_train_with_couchette(run_extractor):
    """The 2012 mail is text-only; the passenger column sits beside the
    timetable rows and the couchette wraps onto two more lines."""
    out = run_extractor("deutsche-bahn", "deutsche-bahn-night-train.eml")
    assert out == {
        "deutsche-bahn-aaaaaa-20400314-cnl1234.reservation.json": leg(
            "AAAAAA-20400314-CNL1234",
            "CNL 1234",
            "Bremen Hbf",
            "Basel Bad Bf",
            ("2040-03-14T21:05:00", "2040-03-15T06:40:00"),
            ("7", "2"),
            underName=PASSENGER,
            reservedTicket=seat("101", "33", "Couchette"),
        ),
        "deutsche-bahn-aaaaaa-20400315-ice271.reservation.json": leg(
            "AAAAAA-20400315-ICE271",
            "ICE 271",
            "Basel Bad Bf",
            "Lübeck Hbf",
            ("2040-03-15T06:52:00", "2040-03-15T07:30:00"),
            ("3", "5"),
            underName=PASSENGER,
        ),
    }


def test_return_across_new_year(run_extractor):
    out = run_extractor("deutsche-bahn", "deutsche-bahn-return.eml")
    assert out == {
        "deutsche-bahn-bbbbbb-20441231-ic2001.reservation.json": leg(
            "BBBBBB-20441231-IC2001",
            "IC 2001",
            "Kiel Hbf",
            "Erfurt Hbf",
            ("2044-12-31T22:10:00", "2045-01-01T04:55:00"),
            ("4", "1"),
            underName=PASSENGER,
            reservedTicket=seat("9", "11 12"),
        ),
        "deutsche-bahn-bbbbbb-20450103-ice1502.reservation.json": leg(
            "BBBBBB-20450103-ICE1502",
            "ICE 1502",
            "Erfurt Hbf",
            "Kiel Hbf",
            ("2045-01-03T09:02:00", "2045-01-03T14:47:00"),
            ("2", "6"),
            underName=PASSENGER,
        ),
    }


def test_one_way_with_separate_reservation_column(run_extractor):
    out = run_extractor("deutsche-bahn", "deutsche-bahn-one-way.eml")
    assert out == {
        "deutsche-bahn-900000000001-20511227-rb12.reservation.json": leg(
            "900000000001-20511227-RB12",
            "RB 12",
            "Rostock Hbf",
            "Schwerin Hbf",
            ("2051-12-27T08:12:00", "2051-12-27T09:20:00"),
            ("2", "4"),
        ),
        "deutsche-bahn-900000000001-20511227-ice803.reservation.json": leg(
            "900000000001-20511227-ICE803",
            "ICE 803",
            "Schwerin Hbf",
            "Mainz Hbf",
            ("2051-12-27T09:41:00", "2051-12-27T15:02:00"),
            ("5", "3"),
            reservedTicket=seat("6", "21"),
        ),
    }
