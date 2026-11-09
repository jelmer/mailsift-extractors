"""Tests for the British Airways boarding-pass extractor."""

from __future__ import annotations


def test_the_pass_names_its_booking(run_extractor):
    out = run_extractor(
        "british-airways-boarding-pass", "british-airways-boarding-pass.eml"
    )
    assert set(out) == {
        "ba-ba0001-2030-03-04.ticket.pdf",
        "ba-ba0001-2030-03-04.ticket.json",
    }
    assert out["ba-ba0001-2030-03-04.ticket.pdf"].startswith(b"%PDF")
    # The flight comes from the e-ticket receipt; this names its booking.
    assert out["ba-ba0001-2030-03-04.ticket.json"] == {
        "reservationNumber": "ZZZZZZ",
        "provider": "British Airways",
        "date": "2030-03-04",
    }
