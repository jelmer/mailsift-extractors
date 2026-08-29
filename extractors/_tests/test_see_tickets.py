"""Tests for the SEE Tickets event-ticket extractor."""

from __future__ import annotations


def test_eticket_order_emits_reservation_and_ticket_pdf(run_extractor):
    out = run_extractor("see-tickets", "see-tickets-eticket.eml")
    assert set(out) == {
        "see-tickets-12345678.reservation.json",
        "see-tickets-12345678.ticket.pdf",
    }
    assert out["see-tickets-12345678.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "see-tickets-12345678",
        "reservationFor": {
            "@type": "Event",
            "name": "Example Artist",
            "startDate": "2023-04-06T19:30:00",
            "location": {
                "@type": "Place",
                "name": "Example Venue, London",
            },
        },
        "provider": {"@type": "Organization", "name": "See Tickets"},
    }
    ticket = out["see-tickets-12345678.ticket.pdf"]
    assert isinstance(ticket, bytes)
    assert ticket.startswith(b"%PDF")


def test_collect_at_venue_order_emits_only_reservation(run_extractor):
    out = run_extractor("see-tickets", "see-tickets-collect.eml")
    assert set(out) == {"see-tickets-87654321.reservation.json"}
    assert out["see-tickets-87654321.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": "see-tickets-87654321",
        "reservationFor": {
            "@type": "Event",
            "name": "Another Artist",
            "startDate": "2023-11-13T19:30:00",
            "location": {
                "@type": "Place",
                "name": "The Example Club, Camden, London",
            },
            "doorTime": "2023-11-13T19:00:00",
        },
        "provider": {"@type": "Organization", "name": "See Tickets"},
    }
