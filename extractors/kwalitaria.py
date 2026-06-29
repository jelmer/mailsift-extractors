#!/usr/bin/env python3
"""Kwalitaria online-order confirmations.

Kwalitaria is a Dutch takeaway franchise that uses the e-food.nl
platform for online orders. Every shop sends its confirmation from
no-reply@kwalitaria.nl with the same HTML template:

    Subject: Kwalitaria <shop name> bestelling <order-id>
    Body has shop name in "Je hebt besteld bij <name>." and the order
    summary as a table with `<qty>x <name> ... <line total>` rows and a
    final "Totaal € <amount>" row.

We emit an Order receipt with line items, line totals, and the grand
total.
"""

from __future__ import annotations

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


SUBJECT_RE = re.compile(r"Kwalitaria\s+(.+?)\s+bestelling\s+(\d+)", re.I)
SHOP_RE = re.compile(r"Je hebt besteld bij\s+(.+?)\.\s")
TOTAL_RE = re.compile(r"Totaal\s*€\s*([0-9]+[.,][0-9]{2})")


class _Rows(HTMLParser):
    """Walk the order table and capture (qty, name, line_total) tuples.

    The template is regular enough that we can drive everything off
    `<tr>`/`<td>` events alone: each item row has three cells -
    `<qty>x`, the product name (with optional `<br/>+ option` lines),
    and the line total `€ X,YY`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current: list[str] = []
        self.cell_parts: list[str] = []
        self.in_cell = False
        self.in_row = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self.in_row = True
            self.current = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.cell_parts = []
        elif tag == "br" and self.in_cell:
            self.cell_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_cell:
            cell = re.sub(r"[ \t]+", " ", "".join(self.cell_parts)).strip()
            self.current.append(cell)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current:
                self.rows.append(self.current)
            self.in_row = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)


def parse_price_eur(text: str) -> float | None:
    """Parse `€ 22,05`-style values into a float."""
    m = re.search(r"€\s*([0-9]+[.,][0-9]{2})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def parse_qty(cell: str) -> int | None:
    m = re.match(r"(\d+)\s*x\b", cell)
    if not m:
        return None
    return int(m.group(1))


def strip_html_text(body: str) -> str:
    text = re.sub(r"<[^>]+>", " ", body)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    subj_match = SUBJECT_RE.search(mail.subject)
    if not subj_match:
        return 0
    shop_short, order_id = subj_match.group(1).strip(), subj_match.group(2)

    flat = strip_html_text(mail.html)
    # The body's "Je hebt besteld bij X." names the shop without the
    # "Kwalitaria" prefix in some templates and with it in others, so
    # strip a leading "Kwalitaria " to make the joined name consistent.
    shop_full = shop_short
    if (m := SHOP_RE.search(flat)) is not None:
        shop_full = re.sub(r"^Kwalitaria\s+", "", m.group(1).strip(), flags=re.I)

    parser = _Rows()
    parser.feed(mail.html)

    items: list[dict] = []
    line_total_skipped: set[str] = {"leverkosten", "btw", "totaal"}
    for row in parser.rows:
        if len(row) < 3:
            continue
        qty = parse_qty(row[0])
        if qty is None:
            continue
        name_cell = row[1]
        # First line is the product, subsequent `+ option` lines are
        # modifiers. Keep them in `description` so downstream tooling
        # can show them, but pull the first line out as the name.
        lines = [ln.strip() for ln in name_cell.splitlines() if ln.strip()]
        if not lines:
            continue
        name = lines[0]
        if name.lower() in line_total_skipped:
            continue
        price = parse_price_eur(row[2])
        if price is None:
            continue
        item: dict = {
            "@type": "OrderItem",
            "orderQuantity": qty,
            "orderedItem": {"@type": "Product", "name": name},
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": price,
                "priceCurrency": "EUR",
            },
        }
        if len(lines) > 1:
            item["orderedItem"]["description"] = "; ".join(lines[1:])
        items.append(item)

    total = None
    if (m := TOTAL_RE.search(flat)) is not None:
        total = float(m.group(1).replace(",", "."))

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "orderNumber": f"kwalitaria-{order_id}",
        "merchant": f"Kwalitaria {shop_full}",
    }
    if items:
        receipt["orderedItem"] = items
    if total is not None:
        receipt["priceSpecification"] = {
            "@type": "PriceSpecification",
            "price": total,
            "priceCurrency": "EUR",
        }

    Path(f"kwalitaria-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
