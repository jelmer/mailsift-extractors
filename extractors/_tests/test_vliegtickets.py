"""Tests for the Vliegtickets.nl e-ticket extractor."""

from __future__ import annotations

BROKER = {"@type": "Organization", "name": "Vliegtickets.nl"}
PASSENGER = {"@type": "Person", "name": "Test User"}


def reservation(locator: str, flight: dict, **extra) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": locator,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "broker": BROKER,
        "reservationFor": {"@type": "Flight", **flight},
        "underName": PASSENGER,
        **extra,
    }


def airport(name: str) -> dict:
    return {"@type": "Airport", "name": name}


def test_eticket_emits_one_reservation_per_segment(run_extractor):
    out = run_extractor("vliegtickets", "vliegtickets-eticket.eml")
    lufthansa = {"@type": "Airline", "iataCode": "LH", "name": "Lufthansa"}
    ticket = {"ticketNumber": "0740000000000"}
    assert out == {
        "vliegtickets-AAAAAA-20381022-LH1009.reservation.json": reservation(
            "BBBBBB",
            {
                "flightNumber": "1009",
                "airline": lufthansa,
                "departureAirport": airport("Brussels Airport"),
                "arrivalAirport": airport("Frankfurt International Airport"),
                "departureTime": "2038-10-22T08:00:00",
                "arrivalTime": "2038-10-22T09:25:00",
                "arrivalTerminal": "1",
            },
            **ticket,
        ),
        "vliegtickets-AAAAAA-20381022-LH422.reservation.json": reservation(
            "BBBBBB",
            {
                "flightNumber": "422",
                "airline": lufthansa,
                "departureAirport": airport("Frankfurt International Airport"),
                "arrivalAirport": airport("Boston Logan Int'l Airport"),
                "departureTime": "2038-10-22T10:40:00",
                "arrivalTime": "2038-10-22T12:50:00",
                "departureTerminal": "2",
                "arrivalTerminal": "E",
            },
            **ticket,
            ticketedSeat={"@type": "Seat", "seatNumber": "48-L"},
        ),
        # Lands the morning after ("Volgende dag").
        "vliegtickets-AAAAAA-20381028-DL135.reservation.json": reservation(
            "CCCCCC",
            {
                "flightNumber": "135",
                "airline": {"@type": "Airline", "iataCode": "DL", "name": "Delta"},
                "departureAirport": airport("Boston Logan Int'l Airport"),
                "arrivalAirport": airport("Brussels Airport"),
                "departureTime": "2038-10-28T08:40:00",
                "arrivalTime": "2038-10-29T06:35:00",
                "departureTerminal": "E",
            },
            **ticket,
            ticketedSeat={"@type": "Seat", "seatNumber": "43-F / 41-J"},
        ),
    }


def test_eticket_without_airline_names(run_extractor):
    """The 2009 template leaves the airline name before "- Vlucht"
    empty and issues a conjunction ticket."""
    out = run_extractor("vliegtickets", "vliegtickets-eticket-2009.eml")
    assert sorted(out) == [
        "vliegtickets-DDDDDD-20371021-UA1520.reservation.json",
        "vliegtickets-DDDDDD-20371021-UA950.reservation.json",
        "vliegtickets-DDDDDD-20371026-UA412.reservation.json",
        "vliegtickets-DDDDDD-20371026-UA688.reservation.json",
        "vliegtickets-DDDDDD-20371026-UA951.reservation.json",
    ]
    assert out["vliegtickets-DDDDDD-20371021-UA950.reservation.json"] == reservation(
        "EEEEEE",
        {
            "flightNumber": "950",
            "airline": {"@type": "Airline", "iataCode": "UA"},
            "departureAirport": airport("Brussels Airport"),
            "arrivalAirport": airport("Newark Liberty Int'l Airport"),
            "departureTime": "2037-10-21T11:15:00",
            "arrivalTime": "2037-10-21T13:20:00",
            "arrivalTerminal": "B",
        },
        ticketNumber="0160000000000-001",
    )
