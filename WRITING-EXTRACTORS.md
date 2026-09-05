# Writing an extractor: a walkthrough

Roughly what you'd do to go from "I have a forwarded booking email" to
a merged extractor in about twenty minutes. It assumes you have this
repository checked out and `pytest` on your `PATH`.

For the underlying contract - what the manifest fields mean, what the
script gets on stdin, what filenames it must write - see
[`extractors/README.md`](extractors/README.md). For the general shape
of a contribution (PII scrub, formatting, running tests), see
[`CONTRIBUTING.md`](CONTRIBUTING.md). This file threads those together
into a step-by-step recipe.

Throughout, substitute `myvendor` with the vendor's slug. Keep it
lowercase, hyphen-separated, and roughly matching how the vendor
brands itself (`booking-com`, `air-france`, `sncf-connect`).

## 1. Save a corpus fixture and scrub the PII

Every extractor needs at least one real message to test against. Save
one from your mail client as `myvendor-<what-it-is>.eml` (for example
`myvendor-confirmation.eml`, `myvendor-cancellation.eml`) under
`tests/corpus/`. Use "Show original" in Gmail, "View source" in
Thunderbird, or `.eml` export from most desktop clients: you want the
raw RFC822 with headers intact, not the rendered body.

The corpus is public. See
[`CONTRIBUTING.md`'s "Scrub every trace of PII"](CONTRIBUTING.md#scrub-every-trace-of-pii-from-the-fixture)
section for what to replace and how; a few extras that matter
specifically for a first pass:

- Booking references, order numbers, tracking numbers, ticket tokens,
  receipt IDs: replace with a same-length placeholder like `XXXXXX` or
  `TESTID42` so length-based regexes still match.
- Dates and times: usually keep them. A lot of extractors do
  weekday/date arithmetic (see `dice.py` for an example) and shifting
  the date can break the resolution. If you must shift, shift the
  `Date:` header and the body dates by the same offset and re-check
  the day of week.
- Keep the DKIM signature and `Authentication-Results:` header
  verbatim even after scrubbing the body. `require_dkim` reads them
  at replay time and a broken signature is fine (the pipeline doesn't
  re-verify), but the header shape needs to be recognisable.

If in doubt, `grep` the scrubbed file for your own name, postcode, and
any real reference numbers before committing.

## 2. Copy the smallest representative extractor

Rather than starting from a blank file, copy an existing pair that
matches the shape of what you're building. Two good starting points
for single-artifact extractors:

- `dice.py` / `dice.yaml`: emits one `.reservation.json` from an
  HTML-only mail with no schema.org markup. Good template for event
  tickets and any parse-the-body-yourself vendor.
- `airbnb.py` / `airbnb.yaml`: emits one `.receipt.json` from an HTML
  body. Good template for payment receipts and orders.

For attachment-driven extractors (the vendor mails a PDF and the body
is boilerplate), `hyperoptic.py` is the smallest example.

Copy both files:

```sh
cp extractors/dice.py    extractors/myvendor.py
cp extractors/dice.yaml  extractors/myvendor.yaml
chmod +x extractors/myvendor.py
```

The script needs to be executable; mailsift `exec`s it directly.

## 3. Adjust the manifest

Open `extractors/myvendor.yaml`. Every field is documented in
[`extractors/README.md`](extractors/README.md); the settings that
matter for a new extractor:

```yaml
name: myvendor
order: 50
from_domains:
  - myvendor.example
subject_regex: "(?i)^Your booking confirmation"
requires:
  - html
require_dkim:
  - myvendor.example
```

Conservative defaults are the point. `CONTRIBUTING.md`'s
["Constrain the manifest as tightly as you can"](CONTRIBUTING.md#constrain-the-manifest-as-tightly-as-you-can)
section is the guide; the quick rules:

- `name` must be unique across the whole `extractors_dir`. Convention
  is to match the filename stem.
- `from_domains` accepts wildcards (`*.myvendor.example`) for vendors
  who send from several subdomains. Case is ignored.
- `subject_regex` should exclude marketing mail. Anchor with `^` when
  the vendor has a stable subject prefix. Always use `(?i)` for
  case-insensitivity unless the vendor is fussy about case.
- `requires` gates on the MIME shape. `html`, `text`,
  `attachment:application/pdf`, or `attachment:filename:*.pdf`.
- `require_dkim` is the strongest guarantee that the message is really
  from the vendor. Set it to the domain the vendor signs from; leave
  it out only if the vendor genuinely doesn't sign (rare in 2026),
  and document why in a comment.

`order: 50` runs earlier than the default `100`; use it when your
extractor should take precedence over the generic `schema-ld`
fallback. Otherwise leave it at the default.

Validate:

```sh
mailsift lint --extractors extractors
```

`lint` compiles every regex, walks the `requires:` shapes, checks the
script exists and is executable, and reports every problem at once.
Fix anything it complains about before moving on.

## 4. Adjust the Python script

Open `extractors/myvendor.py`. The wire contract is in
[`extractors/README.md`](extractors/README.md): stdin is the raw
message, cwd is a fresh tempdir, output is `<slug>.<kind>.<ext>` files
in cwd. The `_lib/mailsift_extractor.py` helper hands you a parsed
`Mail` with `.from_address`, `.subject`, `.date`, `.text`, `.html`,
`.ld_json`, and `.attachments`; use it or parse the message yourself,
whichever fits. Shared `strip_html()` and `normalize_unicode()`
helpers live in the same module.

Decide up front which artifact kind you're producing. The
"Artifact filenames" table in `extractors/README.md` is the source of
truth; the required-field summary:

- `.reservation.json` needs a schema.org reservation type
  (`FlightReservation`, `TrainReservation`, `LodgingReservation`,
  `EventReservation`, `FoodEstablishmentReservation`, ...) and ideally
  a `reservationNumber` so dedup works.
- `.receipt.json` needs at least a merchant name and an `orderNumber`
  (or `identifier`).
- `.parcel.json` needs a `trackingNumber`.
- `.bill.json` needs `payee`, `amount`, `dueDate`, `invoiceNumber`.
- `.ticket.<ext>` is an opaque blob; pair it with a
  `.reservation.json` in the same run so the meta sidecar can link the
  two.

Pick a stable slug. `dice.py` uses `dice-<order_id>`; use something
similar so the tempdir filenames are readable in logs. The slug is
what shows up in the meta sidecar for tickets.

Exit 0 when you're done, even if you wrote nothing: an empty cwd just
means "not for me". Only exit non-zero on real, unexpected failures;
those get logged.

## 5. Add a pytest test

The test harness in `extractors/_tests/conftest.py` runs your
extractor in a tempdir and returns a `{filename: parsed_body}` dict.
Test files follow the pattern `test_<vendor with hyphens replaced by
underscores>.py` (so `myvendor` stays `test_myvendor.py`, but
`air-france` becomes `test_air_france.py`).

```python
"""Tests for the MyVendor booking extractor."""

from __future__ import annotations


def test_confirmation_emits_reservation(run_extractor):
    out = run_extractor("myvendor", "myvendor-confirmation.eml")
    assert set(out) == {"myvendor-XXXXXX.reservation.json"}
    reservation = out["myvendor-XXXXXX.reservation.json"]
    assert reservation["@type"] == "EventReservation"
    assert reservation["reservationNumber"] == "myvendor-XXXXXX"
```

The first argument to `run_extractor` is the extractor name (matches
`<name>.py` under `extractors/`); the second is the eml filename under
`tests/corpus/`. JSON artifacts come back as parsed dicts. iCalendar
files come back as strings with the volatile `DTSTAMP` line stripped
so the body compares stably. Binary blobs (tickets, receipt-file
sidecars) come back as raw `bytes`.

Assert on the full artifact where you can (`assert reservation ==
{...}`) rather than picking off individual keys; a full-body assertion
catches regressions in fields you didn't think to check.

## 6. Run the tests

```sh
pytest extractors/_tests/test_myvendor.py -v
```

Iterate on the extractor until it passes. Then run the whole suite so
you're sure you haven't disturbed anyone else's dispatch:

```sh
pytest extractors/_tests
```

A test that fails on JSON keys usually means either your slug changed
(the `set(out)` assertion catches this) or a field you're extracting
has moved in the source HTML: re-check the scrubbed fixture and adjust
the parser.

## 7. Verify against the pipeline end to end

The pytest harness runs your extractor in isolation. To confirm that
mailsift itself dispatches to it (that the manifest hints match and no
earlier extractor claims the message first), replay the fixture
through mailsift with a dry run:

```sh
mailsift replay tests/corpus/myvendor-confirmation.eml \
    --extractors extractors --dry-run --explain
```

The `--explain` table lists every extractor, whether it matched or was
prefiltered out and why, and what each producing extractor emitted. If
`myvendor` isn't in the "matched" column, the manifest hints are
wrong: check the `From:` domain, the DKIM domain, and the subject
regex against the fixture. `--dry-run` prevents the run from actually
filing anything to your local event / bill / parcel directories.

To see the raw files your extractor drops in cwd (the single-message
invocation without the pipeline), see the "Testing and debugging"
section in [`extractors/README.md`](extractors/README.md).

## 8. Commit checklist

Before opening the PR:

- `ruff format extractors/myvendor.py extractors/_tests/test_myvendor.py`
- `ruff check extractors/myvendor.py extractors/_tests/test_myvendor.py`
- `pytest extractors/_tests` passes
- `mailsift lint --extractors extractors` is clean
- `mailsift replay tests/corpus/myvendor-*.eml --extractors extractors --dry-run --explain`
  shows your extractor matching and emitting the expected artifact
- The corpus fixtures under `tests/corpus/` have been scrubbed of
  personal data (names, addresses, real booking references, personal
  email addresses)
- The artifact filenames follow the `<slug>.<kind>.<ext>` scheme from
  the "Artifact filenames" table

That's the whole loop. Once the first extractor is in, adding
neighbours (the vendor's cancellation mail, refund mail, itinerary
update) is a matter of a new corpus fixture and a new branch in the
existing script.
