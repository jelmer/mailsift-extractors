"""Tests for the pre-DKIM Amadeus itinerary / e-ticket extractor."""

from __future__ import annotations

PENDING_CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}

KLM = {"@type": "Airline", "iataCode": "KL", "name": "KLM Royal Dutch Airlines"}


def _airport(iata=None, name=None, city=None):
    airport = {"@type": "Airport"}
    if name:
        airport["name"] = name
    if iata:
        airport["iataCode"] = iata
    if city:
        airport["address"] = {"@type": "PostalAddress", "addressLocality": city}
    return airport


def test_klm_eticket_rolls_over_into_next_year(run_extractor):
    out = run_extractor("amadeus-legacy", "amadeus-klm-eticket.eml")
    assert out == {
        "amadeus-AB1CDE-KL743.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "AB1CDE",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "743",
                "airline": KLM,
                "departureAirport": _airport("AMS", city="Amsterdam"),
                "arrivalAirport": _airport("LIM", city="Lima"),
                "departureTime": "2014-12-17T12:25:00",
                "arrivalTime": "2014-12-17T19:15:00",
                "pending:bookingClass": "N",
            },
            "underName": {"@type": "Person", "name": "TEST USER"},
            "ticketNumber": "0740000000001",
        },
        "amadeus-AB1CDE-KL744.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "AB1CDE",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "744",
                "airline": KLM,
                "departureAirport": _airport("LIM", city="Lima"),
                "arrivalAirport": _airport("AMS", city="Amsterdam"),
                "departureTime": "2015-01-07T21:15:00",
                "arrivalTime": "2015-01-08T15:30:00",
                "pending:bookingClass": "N",
            },
            "underName": {"@type": "Person", "name": "TEST USER"},
            "ticketNumber": "0740000000001",
        },
    }


def test_klm_eticket_dutch(run_extractor):
    out = run_extractor("amadeus-legacy", "amadeus-klm-eticket-dutch.eml")
    assert out == {
        "amadeus-FG2HIJ-KL605.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "FG2HIJ",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "605",
                "airline": KLM,
                "departureAirport": _airport("AMS", city="Amsterdam"),
                "arrivalAirport": _airport("SFO", city="San Francisco"),
                "departureTime": "2012-10-19T09:50:00",
                "arrivalTime": "2012-10-19T11:50:00",
                "pending:bookingClass": "N",
            },
            "underName": {"@type": "Person", "name": "TEST USER"},
            "ticketNumber": "0740000000002",
        },
        "amadeus-FG2HIJ-KL606.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "FG2HIJ",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "606",
                "airline": KLM,
                "departureAirport": _airport("SFO", city="San Francisco"),
                "arrivalAirport": _airport("AMS", city="Amsterdam"),
                "departureTime": "2012-10-22T14:00:00",
                "arrivalTime": "2012-10-23T09:15:00",
                "pending:bookingClass": "N",
            },
            "underName": {"@type": "Person", "name": "TEST USER"},
            "ticketNumber": "0740000000002",
        },
    }


def test_check_my_trip_itinerary(run_extractor):
    out = run_extractor("amadeus-legacy", "amadeus-itinerary.eml")
    china_southern = {
        "@type": "Airline",
        "iataCode": "CZ",
        "name": "China Southern Airlines",
    }
    canton = _airport("CAN", "Baiyun Intl", "Guangzhou")
    assert out == {
        "amadeus-KL3MNO-CZ302.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "KL3MNO",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "302",
                "airline": china_southern,
                "departureAirport": _airport("SYD", "Kingsford Smith", "Sydney"),
                "arrivalAirport": canton,
                "departureTime": "2018-01-31T22:15:00",
                "arrivalTime": "2018-02-01T05:00:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "E",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketNumber": "7840000000003",
        },
        "amadeus-KL3MNO-CZ303.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "KL3MNO",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "303",
                "airline": china_southern,
                "departureAirport": canton,
                "arrivalAirport": _airport("LHR", "Heathrow", "London"),
                "departureTime": "2018-02-01T09:30:00",
                "arrivalTime": "2018-02-01T14:30:00",
                "pending:cabinClass": "Economy",
                "pending:bookingClass": "E",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketNumber": "7840000000003",
        },
    }


def test_finnair_confirmation(run_extractor):
    out = run_extractor("amadeus-legacy", "amadeus-finnair-confirmation.eml")
    finnair = {"@type": "Airline", "iataCode": "AY", "name": "Finnair"}
    assert out == {
        "amadeus-UV5WXY-AY2918.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "UV5WXY",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "2918",
                "airline": finnair,
                "departureAirport": _airport(city="Berlin"),
                "arrivalAirport": _airport(city="Helsinki"),
                "departureTime": "2013-01-04T19:10:00",
                "arrivalTime": "2013-01-04T22:05:00",
                "pending:bookingClass": "L",
                "pending:cabinClass": "Economy",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketedSeat": {"@type": "Seat", "seatNumber": "12A"},
        },
        "amadeus-UV5WXY-AY845.reservation.json": {
            "@context": PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "UV5WXY",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "845",
                "airline": finnair,
                "departureAirport": _airport(city="Helsinki"),
                "arrivalAirport": _airport(city="Amsterdam"),
                "departureTime": "2013-01-14T16:40:00",
                "arrivalTime": "2013-01-14T18:15:00",
                "pending:bookingClass": "Z",
                "pending:cabinClass": "Economy",
            },
            "underName": {"@type": "Person", "name": "Test User"},
            "ticketedSeat": {"@type": "Seat", "seatNumber": "14C"},
        },
    }
