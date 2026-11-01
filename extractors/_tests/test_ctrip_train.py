"""Tests for the Ctrip China rail "Ticket Issued" extractor."""

from __future__ import annotations

BROKER = {"@type": "Organization", "name": "Ctrip"}
PASSENGERS = [
    {"@type": "Person", "name": "USER TEST"},
    {"@type": "Person", "name": "EXAMPLE OTHER"},
]


def test_ticket_issued_emits_reservation(run_extractor):
    out = run_extractor("ctrip-train", "ctrip-train-ticket-issued.eml")
    assert out == {
        "ctrip-E000000001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "E000000001",
            "broker": BROKER,
            "reservationFor": {
                "@type": "TrainTrip",
                "trainNumber": "G13",
                "departureStation": {"@type": "TrainStation", "name": "Beijing South"},
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": "Shanghai Hongqiao",
                },
                "departureTime": "2018-01-12T10:00:00",
                "arrivalTime": "2018-01-12T14:28:00",
            },
            "underName": PASSENGERS,
            # Two passengers in one carriage: the seat numbers differ,
            # so only the shared carriage is kept.
            "ticketedSeat": {"@type": "Seat", "seatSection": "05"},
            "url": "https://english.ctrip.com/trains/order?orderId=5000000001",
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 1139.0,
                "priceCurrency": "CNY",
            },
        },
    }


def test_station_name_with_hyphen(run_extractor):
    # "Pingyao County High-speed-Beijing West": only the second hyphen
    # separates the stations.
    out = run_extractor(
        "ctrip-train", "ctrip-train-ticket-issued-hyphenated-station.eml"
    )
    assert out == {
        "ctrip-E000000002.reservation.json": {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": "E000000002",
            "broker": BROKER,
            "reservationFor": {
                "@type": "TrainTrip",
                "trainNumber": "D2002",
                "departureStation": {
                    "@type": "TrainStation",
                    "name": "Pingyao County High-speed",
                },
                "arrivalStation": {"@type": "TrainStation", "name": "Beijing West"},
                "departureTime": "2018-01-11T08:41:00",
                "arrivalTime": "2018-01-11T12:52:00",
            },
            "underName": PASSENGERS,
            "ticketedSeat": {"@type": "Seat", "seatSection": "06"},
            "url": "https://english.ctrip.com/trains/order?orderId=5000000002",
            "totalPrice": {
                "@type": "PriceSpecification",
                "price": 524.0,
                "priceCurrency": "CNY",
            },
        },
    }


def test_mail_after_rebrand_is_refused(run_extractor):
    out = run_extractor("ctrip-train", "ctrip-train-ticket-issued-after-cutoff.eml")
    assert out == {}
