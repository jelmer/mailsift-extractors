#!/usr/bin/env python3
"""Alamo (alamo.nl) booking mails.

Dutch-language mail from `info@alamo.nl`, subject `Uw Alamo
reservering: <number>`. The same subject covers three stages: the
initial request acknowledgement, the booking confirmation
(`Boekingsbevestiging`, with a `FACTUUR_<number>-N.pdf` invoice), and
the voucher (`Autohuur Voucher`, with `VOUCHER_<number>-N.pdf`).

The body carries none of the trip details - no dates, branch or
vehicle; those live only inside the attached PDFs, which we can't
parse. So this extractor preserves each booking-specific document as
its own `.receipt.pdf` + `.receipt.json` pair (mailsift files paired
PDFs beside a same-slug JSON and drops orphans) and does not
synthesise a reservation it can't fill in. The generic `Algemene
voorwaarden` / `Condities ter plaatse` terms attached to every mail
are skipped.

TODO: if the PDFs are ever parsed (pickup/dropoff, branch, vehicle),
emit a RentalCarReservation so these reach the calendar too.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUBJECT_RE = re.compile(r"Uw Alamo reservering:\s*(\d{6,})", re.IGNORECASE)
# Only the documents named after this booking; the rest are boilerplate.
DOCUMENT_RE = re.compile(r"^(FACTUUR|VOUCHER)_(\d{6,})[-_]?\d*\.pdf$", re.IGNORECASE)


def main() -> int:
    mail = read_message()
    match = SUBJECT_RE.search(mail.subject or "")
    if not match:
        return 0
    booking = match.group(1)

    documents = [
        (a, m)
        for a in mail.attachments
        if a.looks_like_pdf()
        and (m := DOCUMENT_RE.match(a.filename or ""))
        and m.group(2) == booking
    ]
    if not documents:
        return 0

    # One receipt record per PDF so each blob has a same-slug JSON
    # sibling. mailsift files the pair together under
    # `<merchant>-<order>` and drops orphan blobs.
    order_date = mail.date.strftime("%Y-%m-%d") if mail.date is not None else None
    for document, document_match in documents:
        kind = document_match.group(1).lower()
        slug = f"alamo-{booking}-{kind}"
        receipt: dict = {
            "@context": "https://schema.org",
            "@type": "Order",
            "merchant": "Alamo",
            "orderNumber": f"{booking}-{kind}",
        }
        if order_date is not None:
            receipt["orderDate"] = order_date
        Path(f"{slug}.receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
        )
        Path(f"{slug}.receipt.pdf").write_bytes(document.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
