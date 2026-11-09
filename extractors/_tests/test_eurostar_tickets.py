"""Tests for the Eurostar ticket-delivery extractor."""

from __future__ import annotations


def _leg(
    number: str,
    route: tuple[str, str],
    times: tuple[str, str],
    train: str,
    seat: tuple[str, str],
) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": number,
        "mailsift:itineraryComplete": True,
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": route[0]},
            "arrivalStation": {"@type": "TrainStation", "name": route[1]},
            "departureTime": times[0],
            "arrivalTime": times[1],
            "trainNumber": train,
        },
        "reservedTicket": {
            "@type": "Ticket",
            "ticketedSeat": {
                "@type": "Seat",
                "seatNumber": seat[1],
                "seatSection": seat[0],
            },
        },
    }


def test_single_leg_grounds_the_year_on_the_mail_date(run_extractor):
    # The short date form (`Mon, 30 October`) carries no year.
    out = run_extractor("eurostar-tickets", "eurostar-tickets.eml")
    assert out == {
        "eurostar-EEEEEE-outbound-1001.reservation.json": _leg(
            "eurostar-EEEEEE-outbound",
            ("Beta Central", "Alpha International"),
            ("2023-10-30T19:28:00", "2023-10-30T21:57:00"),
            "1001",
            ("4", "11"),
        ),
    }


def test_connection_emits_one_reservation_per_leg(run_extractor):
    # A journey with a change is numbered `Return (1/2)`, `(2/2)`; each
    # leg is its own reservation, told apart from the other legs of
    # that direction by its train number.
    out = run_extractor("eurostar-tickets", "eurostar-tickets-connection.eml")
    assert out == {
        "eurostar-FFFFFF-outbound-1001.reservation.json": _leg(
            "eurostar-FFFFFF-outbound",
            ("Alpha International", "Beta Central"),
            ("2024-11-19T06:04:00", "2024-11-19T10:32:00"),
            "1001",
            ("4", "12"),
        ),
        "eurostar-FFFFFF-return-1002.reservation.json": _leg(
            "eurostar-FFFFFF-return",
            ("Beta Central", "Gamma Midi"),
            ("2024-11-26T06:58:00", "2024-11-26T08:08:00"),
            "1002",
            ("5", "13"),
        ),
        "eurostar-FFFFFF-return-1003.reservation.json": _leg(
            "eurostar-FFFFFF-return",
            ("Gamma Midi", "Alpha International"),
            ("2024-11-26T08:52:00", "2024-11-26T09:57:00"),
            "1003",
            ("6", "14"),
        ),
    }


def test_short_date_rolls_into_the_next_year(run_extractor):
    # Booked in December for a February journey: with no year on the
    # date line, grounding on the mail's own year would put the trip
    # ten months in the past.
    out = run_extractor("eurostar-tickets", "eurostar-tickets-year-rollover.eml")
    assert set(out) == {"eurostar-GGGGGG-outbound-1004.reservation.json"}
    reservation = out["eurostar-GGGGGG-outbound-1004.reservation.json"]
    assert reservation["reservationFor"]["departureTime"] == "2026-02-06T08:01:00"
    assert reservation["reservationFor"]["arrivalTime"] == "2026-02-06T11:30:00"


def test_barcodes_and_wallet_links_land_on_their_legs(run_extractor):
    # The outbound has two passengers, so two tickets; the seat is the
    # first passenger's. The Wallet links come out of SES click tracking.
    out = run_extractor("eurostar-tickets", "eurostar-tickets-barcodes.eml")
    outbound = out["eurostar-GGGGGG-outbound-9001.reservation.json"]
    barcode = "https://ticket.eurostar.com/barcode/GGGGGG/{}?s=c2lnbmF0dXJl%3D"
    assert outbound["reservedTicket"] == [
        {
            "@type": "Ticket",
            "ticketToken": barcode.format("ticket-a"),
            "ticketedSeat": {"@type": "Seat", "seatNumber": "21", "seatSection": "3"},
        },
        {"@type": "Ticket", "ticketToken": barcode.format("ticket-b")},
    ]
    wallet = "https://tickets-api.eurostar.com/{}/tickets/{}"
    assert outbound["potentialAction"] == [
        {
            "@type": "ViewAction",
            "name": "Add to Apple Wallet",
            "url": wallet.format("apple", "ticket-a"),
        },
        {
            "@type": "ViewAction",
            "name": "Add to Google Wallet",
            "url": wallet.format("google", "ticket-a"),
        },
        {
            "@type": "ViewAction",
            "name": "Add to Apple Wallet",
            "url": wallet.format("apple", "ticket-b"),
        },
        {
            "@type": "ViewAction",
            "name": "Add to Google Wallet",
            "url": wallet.format("google", "ticket-b"),
        },
    ]

    inbound = out["eurostar-GGGGGG-return-9002.reservation.json"]
    assert inbound["reservedTicket"] == {
        "@type": "Ticket",
        "ticketToken": barcode.format("ticket-c"),
        "ticketedSeat": {"@type": "Seat", "seatNumber": "41", "seatSection": "5"},
    }
    assert [a["url"] for a in inbound["potentialAction"]] == [
        wallet.format("apple", "ticket-c"),
        wallet.format("google", "ticket-c"),
    ]
