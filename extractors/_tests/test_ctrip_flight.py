"""Tests for the Ctrip flight reservation confirmation extractor."""

from __future__ import annotations

BROKER = {"@type": "Organization", "name": "Ctrip"}
PASSENGER = [{"@type": "Person", "name": "USER/TEST"}]


def test_connection_emits_a_reservation_per_segment(run_extractor):
    # The second segment departs late in the evening and lands the next
    # morning; the mail only names the departure day.
    out = run_extractor("ctrip-flight", "ctrip-flight-confirmation.eml")
    url = (
        "http://english.ctrip.com/flights/vieworder?orderid=1000000002"
        "&accesstoken=" + "0" * 64
    )
    assert out == {
        "ctrip-1000000002-CZ3540.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "1000000002",
            "broker": BROKER,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "3540",
                "airline": {"@type": "Airline", "iataCode": "CZ"},
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "SHA",
                    "name": "Shanghai Hongqiao International Airport",
                    "alternateName": "T2",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "CAN",
                    "name": "Guangzhou Baiyun International Airport",
                },
                "departureTime": "2018-01-14T15:50:00",
                "arrivalTime": "2018-01-14T18:25:00",
            },
            "underName": PASSENGER,
            "url": url,
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 3468.0,
                "priceCurrency": "CNY",
            },
        },
        "ctrip-1000000002-CZ325.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "1000000002",
            "broker": BROKER,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "325",
                "airline": {"@type": "Airline", "iataCode": "CZ"},
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "CAN",
                    "name": "Guangzhou Baiyun International Airport",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "SYD",
                    "name": "Sydney Kingsford Smith Airport",
                    "alternateName": "T1",
                },
                "departureTime": "2018-01-14T21:00:00",
                "arrivalTime": "2018-01-15T09:25:00",
            },
            "underName": PASSENGER,
            "url": url,
        },
    }


def test_codeshare_reports_the_marketing_flight(run_extractor):
    out = run_extractor("ctrip-flight", "ctrip-flight-confirmation-codeshare.eml")
    assert out == {
        "ctrip-1000000001-MU9811.reservation.json": {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": "1000000001",
            "broker": BROKER,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "9811",
                "airline": {"@type": "Airline", "iataCode": "MU"},
                "departureAirport": {
                    "@type": "Airport",
                    "iataCode": "PVG",
                    "name": "Shanghai Pudong International Airport",
                    "alternateName": "T1",
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "iataCode": "HKG",
                    "name": "Hong Kong Hong Kong International Airport",
                    "alternateName": "T1",
                },
                "departureTime": "2018-01-14T09:35:00",
                "arrivalTime": "2018-01-14T12:40:00",
            },
            "underName": PASSENGER,
            "url": (
                "http://english.ctrip.com/flights/ViewOrder?orderid=1000000001"
                "&accesstoken=" + "0" * 64
            ),
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 154.25,
                "priceCurrency": "GBP",
            },
        },
    }
