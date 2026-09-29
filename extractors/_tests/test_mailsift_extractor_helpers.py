"""Tests for the shared HTML/Unicode helpers in `_lib/mailsift_extractor.py`.

These helpers are load-bearing for the individual extractors: a change
that broke `strip_html` or `normalize_unicode` would silently degrade
every regex-driven extractor at once, so cover the interesting edge
cases here rather than leaving it to the per-vendor tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))

from io import BytesIO

from mailsift_extractor import normalize_unicode, read_message, strip_html


class TestNormalizeUnicode:
    def test_drops_zero_width_chars(self) -> None:
        assert normalize_unicode("Order\u200b#12345") == "Order#12345"
        assert normalize_unicode("Or‌der‍#1") == "Order#1"
        assert normalize_unicode("A⁠B﻿C") == "ABC"

    def test_drops_soft_hyphen(self) -> None:
        assert normalize_unicode("Trans­avia") == "Transavia"

    def test_converts_non_breaking_space_to_space(self) -> None:
        assert normalize_unicode("Order #123") == "Order #123"

    def test_converts_thin_and_narrow_spaces(self) -> None:
        assert normalize_unicode("€ 12,34") == "€ 12,34"
        assert normalize_unicode("1 000") == "1 000"

    def test_nfkc_folds_compatibility_forms(self) -> None:
        # Full-width digits (from some Asian receipt templates) fold
        # to ASCII so regex `\d+` matches them.
        assert normalize_unicode("１２３") == "123"

    def test_is_idempotent(self) -> None:
        s = "Order #12\u200b345"
        assert normalize_unicode(normalize_unicode(s)) == normalize_unicode(s)


class TestStripHtml:
    def test_drops_style_and_script(self) -> None:
        html = (
            "<html><head><style>body{color:red}</style></head>"
            "<body><script>alert(1)</script>hello</body></html>"
        )
        assert strip_html(html) == "hello"

    def test_decodes_html_entities(self) -> None:
        assert strip_html("Order&nbsp;#12&amp;34") == "Order #12&34"

    def test_collapses_whitespace_by_default(self) -> None:
        html = "<p>one</p>  <p>two</p>\n\n<p>three</p>"
        assert strip_html(html) == "one two three"

    def test_normalizes_unicode(self) -> None:
        # nbsp, zero-width joiner, soft hyphen: all cleaned in one pass.
        html = "<p>Trans­avia\u200b flight HV5315</p>"
        assert strip_html(html) == "Transavia flight HV5315"

    def test_block_tags_preserves_line_structure(self) -> None:
        html = "<h1>Booking</h1><p>Line one</p><p>Line two</p>"
        assert strip_html(html, block_tags=True) == "Booking\nLine one\nLine two"

    def test_block_tags_collapses_multiple_blank_lines(self) -> None:
        html = "<p>a</p><br/><br/><br/><p>b</p>"
        # More than one consecutive break collapses to a single blank line.
        assert strip_html(html, block_tags=True) == "a\n\nb"

    def test_block_tags_treats_br_and_tr(self) -> None:
        html = "<div>row<br/>next</div>"
        assert strip_html(html, block_tags=True) == "row\nnext"

    def test_block_tags_between_table_rows(self) -> None:
        # A table cell is its own block, so consecutive rows separate.
        # The exact number of blank lines between is not something the
        # extractors care about; only that the tokens don't fuse.
        html = "<tr>x</tr><tr>y</tr>"
        assert "x" in strip_html(html, block_tags=True).splitlines()
        assert "y" in strip_html(html, block_tags=True).splitlines()

    def test_handles_nested_style_and_script(self) -> None:
        # Neither <body> nor <script>/<style> is a block tag, so text
        # either side fuses into one token in the default mode. That's
        # the extractors' expected behaviour: whitespace becomes one
        # space, tag boundaries do not.
        html = "<body>keep<script>drop<style>drop2</style>drop3</script>keep2</body>"
        assert strip_html(html) == "keepkeep2"


class TestReadMessage:
    def test_from_with_crlf_in_encoded_word(self) -> None:
        # Python 3.14's strict address parser raises ValueError when a
        # From header's display name decodes to CR/LF (a broken encoded
        # word from a real sender). We fall back to raw parsing so the
        # address is still extracted.
        raw = (
            b"From: =?utf-8?Q?a=0D=0Ab?= <sender@example.com>\r\n"
            b"To: dest@example.com\r\n"
            b"Subject: Hi\r\n"
            b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"body\r\n"
        )
        mail = read_message(BytesIO(raw))
        assert mail.from_address == "sender@example.com"
        assert mail.from_domain == "example.com"
