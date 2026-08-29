"""Tests for the DICE (dice.fm) event ticket extractor."""

from __future__ import annotations


def test_purchase_confirmation_becomes_event_reservation(run_extractor):
    out = run_extractor("dice", "dice-purchase.eml")
    assert set(out) == {"dice-AAAAAAAAAAAA.reservation.json"}
    assert out["dice-AAAAAAAAAAAA.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Example Band // Support (Co-Headline)",
            "startDate": "2024-03-14T19:00:00",
            "location": {
                "@type": "Place",
                "name": "The Example Venue",
                "address": "1 Example Street, London EX1 1EX",
            },
        },
        "provider": {"@type": "Organization", "name": "DICE"},
        "reservationNumber": "dice-AAAAAAAAAAAA",
        "numSeats": 1,
        "reservedTicket": {
            "@type": "Ticket",
            "ticketToken": "General Admission",
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 32.96,
            "priceCurrency": "GBP",
        },
    }
