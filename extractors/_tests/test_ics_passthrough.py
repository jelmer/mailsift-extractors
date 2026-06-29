"""Tests for the ics-passthrough extractor.

When a mail has a `text/calendar` attachment, this extractor copies it
straight through as a `.event.ics` artifact. The Rust pipeline then
parses it, splits per VEVENT, and files via the event sink.
"""

from __future__ import annotations


def test_attached_ics_is_copied(run_extractor):
    out = run_extractor("ics-passthrough", "ics-attached.eml")
    assert set(out) == {"reservation.event.ics"}
    # The body comes through unchanged (modulo our DTSTAMP-strip helper,
    # but the source iCal here has no DTSTAMP so this is byte-for-byte).
    assert out["reservation.event.ics"] == (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Example//Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:reservation-abc123@example.com\r\n"
        "SUMMARY:Test reservation\r\n"
        "DTSTART:20260720T180000Z\r\n"
        "DTEND:20260720T200000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def test_dentist_booking_ics_handled(run_extractor):
    # The dental practice attaches "Add Appointment.ics" with
    # `application/octet-stream` to its booking and reminder mails. We
    # recognise these by the `.ics` filename and pass them through.
    out = run_extractor("ics-passthrough", "dentist-booking.eml")
    assert set(out) == {"Add-Appointment.event.ics"}
    body = out["Add-Appointment.event.ics"]
    assert "UID:dentist-cgw01-2025-10-27-1120@exampledental.example" in body
    assert "METHOD:PUBLISH" in body


def test_dentist_cancellation_ics_preserves_method(run_extractor):
    # The cancellation mail attaches "Cancel Appointment.ics" with
    # `METHOD:CANCEL`. The Rust pipeline relies on the METHOD to file
    # the cancel against the existing calendar event, so the passthrough
    # must preserve it.
    out = run_extractor("ics-passthrough", "dentist-cancellation.eml")
    assert set(out) == {"Cancel-Appointment.event.ics"}
    body = out["Cancel-Appointment.event.ics"]
    assert "METHOD:CANCEL" in body
    assert "STATUS:CANCELLED" in body
    # Same UID as the booking - that's what lets the CANCEL match.
    assert "UID:dentist-cgw01-2025-10-27-1120@exampledental.example" in body


def test_ics_with_text_plain_mimetype_still_handled(run_extractor):
    # Deutsche Bahn attaches .ics files with `Content-Type: text/plain`
    # rather than `text/calendar`. We recognise these by the .ics
    # filename suffix so the calendar event still flows through.
    out = run_extractor("ics-passthrough", "deutsche-bahn-confirmation.eml")
    assert set(out) == {"BAHN_2024-12-27_Hinrueckfahrt_.event.ics"}
    body = out["BAHN_2024-12-27_Hinrueckfahrt_.event.ics"]
    assert body == (
        "BEGIN:VCALENDAR\r\n"
        "X-LOTUS-CHARSET:UTF-8\r\n"
        "VERSION:2.0\r\n"
        "PRODID:http://www.bahn.de\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:db-600000000000-hin@bahn.de\r\n"
        "SUMMARY:Utrecht Centraal -> Hamburg Hbf\r\n"
        "DTSTART:20241227T101400\r\n"
        "DTEND:20241227T161200\r\n"
        "LOCATION:Utrecht Centraal\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
