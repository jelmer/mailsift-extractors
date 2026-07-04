# Contributing an extractor

Each extractor turns one incoming email from a particular vendor into
zero or more structured artifacts. Adding one means writing three
things: a `<vendor>.yaml` manifest, an executable `<vendor>.py` script,
and a test that runs the script against a saved example email.

Before you start, read [`extractors/README.md`](extractors/README.md).
It is the authoritative description of the contract: what the manifest
fields mean, what the script gets on stdin, and what filenames it must
write. This file only covers the workflow of adding a new one.

## Look at an existing extractor first

Every extractor in `extractors/` is a worked example. Rather than
starting from a blank file, find one that emits the same kind of
artifact you need and copy its shape:

- Parcel tracking: `royal-mail`, `evri`, `dpd`, `ups`, `postnl`.
- Reservations (flights, trains, hotels, restaurants): `air-france`,
  `eurostar`, `thon-hotels`, `sevenrooms`.
- Receipts and orders: `amazon`, `bol-com`, `uber`.
- Bills: `eon-next`, `kpn-mobiel`, `switch2`.

Read both the `.py` and its `.yaml` together: the manifest's job is to
stop the script from ever running on mail it can't handle, so the two
are designed as a pair. The `_lib/mailsift_extractor` helper (imported
at the top of most scripts) parses the message for you. Lean on it
rather than reimplementing MIME handling.

## Constrain the manifest as tightly as you can

The manifest is a cheap prefilter that runs before your script is even
spawned. A loose manifest means your extractor gets invoked on
unrelated mail, wastes a subprocess, and risks emitting a bogus
artifact from a message that merely looked similar. **Add every
constraint you can justify.** The four categories are ANDed together,
so each one you add narrows the match:

- `from_domains`: pin the exact sending domain(s). Use a wildcard
  (`*.vendor.example`) only if the vendor genuinely sends from
  several subdomains.
- `subject_regex`: anchor it (`^`, `$`) and make it specific to the
  one message shape you handle. Prefer matching a distinctive phrase
  the vendor always uses over a broad keyword. Use `(?i)` for
  case-insensitivity rather than spelling out character classes.
- `requires`: declare the body shape you actually parse: `html`,
  `text`, or a specific `attachment:<type>/<subtype>` /
  `attachment:filename:<pattern>`. If your script reads the HTML part,
  require `html` so it never runs on a text-only variant.
- `require_dkim`: if the vendor DKIM-signs its mail, require it. This
  is the strongest constraint available: it means a spammer can't reach
  your extractor by spoofing the `From:` domain. `shopify-order` routes
  entirely off the DKIM signature; read its manifest for the pattern.

## Add a test and an example email

Every extractor needs a test. Drop a saved message into `tests/corpus/`
as `<vendor>-<scenario>.eml` and assert on the exact artifacts your
script produces. The `run_extractor` fixture (see
`extractors/_tests/conftest.py`) pipes the `.eml` to your script in a
fresh tempdir and hands back a `{filename: parsed_body}` dict. See
`extractors/_tests/test_royal_mail.py` for the pattern.

Assert on the full artifact body, not just one field, so a regression
in any part of the output is caught. If the vendor sends several
message shapes (ordered / shipped / delivered), add a fixture and a
test for each; that's where the awkward edge cases live.

### Scrub every trace of PII from the fixture

The example emails are checked into a public repository, so **strip all
personal information before committing.** Real vendor mail is dense with
it. Replace, don't just truncate:

- Recipient address to `test@example.org`; recipient name to `Test User`.
- Tracking numbers, booking references, order numbers: an obviously
  fake but format-plausible placeholder (the Royal Mail fixtures use
  `OL000000000GB`). Keep the shape so your parser still exercises the
  real code path.
- Postal addresses, phone numbers, seat/room numbers, loyalty IDs.
- Amounts and dates can stay if they're not identifying, but there's no
  need to keep the originals; round them off.
- Unsubscribe / account links and any URL with a token or account id in
  the query string.
- `Message-ID`, `Received:` chains, and marketing tracking headers:
  trim the message down to the headers your manifest and script
  actually use (`From`, `To`, `Subject`, `Date`,
  `Authentication-Results`, `Content-Type`) plus a minimal body.

Read the finished `.eml` through top to bottom before committing and
confirm nothing real is left. When in doubt, delete it; a fixture only
needs enough structure to drive your extractor, not a faithful copy of
the original mail.

## Running the tests

```sh
pip install pytest
pytest extractors/_tests
```

Run the full suite before committing, and make sure your new test
fails without your extractor and passes with it.

## Formatting and type checking

Extractor scripts are ordinary Python and should be PEP 8 clean. Before
committing, run `ruff` and `mypy`:

```sh
ruff format extractors        # format
ruff check extractors         # lint (add --fix to auto-fix)
mypy extractors               # type-check
```

Keep the scripts type-hinted; the `mailsift_extractor` helper is
annotated, so `mypy` catches most mistakes in how you use a parsed
message.
