# extractors

This directory contains the per-vendor extractor scripts and their manifests.

Each extractor is a small, standalone program that turns one incoming
RFC822 email into zero or more structured artifacts. The Rust pipeline
(`src/extractor.rs`, `src/artifacts.rs`) discovers extractors at startup
by scanning this directory for `*.yaml` manifests; the rest of the
contract - stdin, cwd, artifact filenames - is documented here.

Files whose names begin with `.` or `_` are skipped during discovery,
so the `_lib/` and `_tests/` directories are invisible to the loader
and free to hold whatever helpers and fixtures are convenient.

## Manifest YAML format

A manifest is named `<extractor-stem>.yaml`. By default it pairs with
a sibling executable script at `<extractor-stem>.py`; the `script:`
field overrides that when the script lives elsewhere or under a
different name.

```yaml
name: my-vendor              # required: unique identifier
order: 50                    # optional: lower runs earlier; default 100
script: my-vendor.py         # optional: defaults to <stem>.py next to the manifest
from_domains:                # optional: dispatch hint, case-insensitive
  - vendor.example
  - "*.vendor.example"       # wildcard matches the bare domain and any subdomain
subject_regex: "(?i)..."     # optional: dispatch hint, full Rust regex syntax
requires:                    # optional: body-shape requirements (all must hold)
  - html                     #   message has a text/html part
  - text                     #   message has a text/plain part
  - "attachment:text/calendar"            # has a part of this MIME type
  - "attachment:filename:*.ics"           # has a part whose filename matches
require_dkim:                # optional: only run if Authentication-Results
  - vendor.example           #   shows a passing DKIM signature from one of
  - ".vendor.example"        #   these domains (leading `.` = suffix match,
                             #   matches subdomains only, not the bare domain)
```

### Fields

| Field            | Type            | Required | Notes |
|------------------|-----------------|----------|-------|
| `name`           | string          | yes      | Unique across all discovered manifests. Used in logs and `seen.db`. |
| `order`          | int             | no       | Default `100`. Lower numbers run earlier; ties break on manifest filename. The generic schema.org extractor is `10`, ICS passthrough is `20`, vendor extractors are `50`. |
| `script`         | string          | no       | Path to the executable, relative to the manifest's directory. Defaults to `<manifest-stem>.py`. Must be `chmod +x`. |
| `from_domains`   | list of strings | no       | Case-insensitive match against the lowercased `From:` domain. `*.example.com` matches `example.com` and any subdomain. Empty list means "no `From:` constraint". |
| `subject_regex`  | string          | no       | A regex (compiled with the Rust `regex` crate) applied to the `Subject:` header. Use `(?i)` for case-insensitive matching. |
| `requires`       | list of strings | no       | Each entry must be satisfied. Supported shapes: `html`, `text`, `attachment:<type>/<subtype>`, `attachment:filename:<pattern>`. Filename patterns accept a single leading or trailing `*` (e.g. `*.ics`, `boarding-*`). |
| `require_dkim`   | list of strings | no       | DKIM signing domains that authorise the message. Plain entries are exact matches; entries with a leading `.` are suffix matches against the signing domain (`.myshopify.com` matches `shop42.myshopify.com` but not `myshopify.com`). |

### Dispatch semantics

All four hint categories (`from_domains`, `subject_regex`, `requires`,
`require_dkim`) act as cheap prefilters. Within one category, *at least
one* entry must match (or none for `requires`, where *every* entry
must match). Across categories, *all* declared categories must match.
An omitted or empty category means "no constraint".

`from_domains`, `subject_regex` and `requires` are evaluated against
parsed headers and (for `requires`) the IMAP `BODYSTRUCTURE` summary,
so they can skip whole classes of messages before the extractor
process is spawned. `require_dkim` consults the topmost
`Authentication-Results` header; messages that lack the header
entirely are skipped (the milter front-end, which sees mail before the
MTA authenticates it, explicitly opts out at run time).

Validate manifests with `cargo run -- lint` - it parses every YAML,
checks for missing or non-executable scripts, bad regexes, unknown
`requires` shapes, and duplicate `name:` fields.

## What an extractor must do

The Rust pipeline invokes an extractor as a subprocess. The full
input/output contract is:

- **stdin**: the raw RFC822 message, unmodified.
- **cwd**: a fresh, empty per-extractor tempdir. The script may write
  whatever it likes into cwd; the pipeline reads it back when the
  process exits.
- **stdout / stderr**: captured to logs. **Not used** for artifact
  discovery - write files, not JSON.
- **exit code**: `0` for success (an empty cwd is fine and means
  "nothing to extract"); non-zero means "this extractor failed", which
  is logged at WARN and does not affect any other extractor.
- **timeout**: per-extractor, default 10s. Killed on timeout.

A typical Python extractor opens like:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))
from mailsift_extractor import read_message

mail = read_message()            # parses sys.stdin

mail.from_address                # "noreply@vendor.example"
mail.subject, mail.date          # parsed for you
mail.text, mail.html             # decoded bodies, or None
mail.ld_json                     # parsed application/ld+json blocks
mail.attachments                 # [Attachment(filename, mime_type, bytes, ...)]

Path("flight-fr1234.event.ics").write_bytes(cal.to_ical())
```

The `mailsift_extractor` helper is a convenience for Python extractors.
Scripts in other languages are equally welcome; they just have to parse
the RFC822 themselves.

### Artifact filenames

The pipeline classifies every file in cwd by its suffix:

| Suffix                  | Kind           | Required content                                                                                       |
|-------------------------|----------------|--------------------------------------------------------------------------------------------------------|
| `<slug>.event.ics`      | `event`        | A valid iCalendar file. `UID` inside is the dedup key. Multiple `VEVENT`s in one file are split.       |
| `<slug>.reservation.json` | `reservation` | A schema.org-style reservation object (`FlightReservation`, `TrainReservation`, `LodgingReservation`, `EventReservation`, `FoodEstablishmentReservation`, `BusReservation`). The Rust side converts it to a calendar event. |
| `<slug>.parcel.json`    | `parcel`       | Loose schema.org `ParcelDelivery` JSON. Must include `trackingNumber` (the dedup key). Merged with any prior file for the same tracking number. |
| `<slug>.receipt.json`   | `receipt`      | Loose schema.org `Order` / `Invoice` JSON. Must include `orderNumber` (or `identifier`) and a merchant/seller name. |
| `<slug>.bill.json`      | `bill`         | JSON with `payee`, `amount`, `dueDate`, `invoiceNumber`.                                               |
| `<slug>.subscription.json` | `subscription` | Schema.org-ish JSON carrying at minimum `subscriptionDuration`. Downstream tooling synthesises renewal reminders from it. |
| `<slug>.ticket.<ext>`   | `ticket`       | Any binary blob (PDF, pkpass, image, ...). Dedup is by content hash; `<ext>` is taken literally as the on-disk extension. |

The `<slug>` part is the extractor's choice and becomes the default
filename when filed on disk. Dotfiles and `_*` files (notably the
optional `_manifest.json`) are skipped silently; any other unrecognised
filename in cwd is logged at WARN.

Bills, parcels and subscriptions are **not** auto-synthesised into
calendar events. If you want the bill due date on the calendar, emit
both a `.bill.json` *and* a `.event.ics` from the same extractor -
explicit beats clever.

### Optional `_manifest.json`

An extractor may drop a `_manifest.json` in cwd with `notes` and
per-file `annotations`. It is purely informational: the pipeline still
discovers artifacts by scanning cwd, and the manifest can neither add
nor remove them.

```jsonc
{
  "notes": ["matched ld+json FlightReservation for FR1234"],
  "annotations": {
    "flight-fr1234.reservation.json": { "confidence": "high", "source": "ld+json" }
  }
}
```

### Dedup is the Rust side's job

Extractors do not deal with `seen.db`, CalDAV, the on-disk layout, or
duplicate detection. They just need to produce stable identifiers
*inside* the artifacts (the `UID` in an `.ics`, `trackingNumber` in a
parcel, `orderNumber` in a receipt, `invoiceNumber` in a bill); the
Rust side derives the dedup key from there.

### Debugging

Because the contract is "stdin in, files out", running an extractor
by hand is one line:

```sh
mkdir /tmp/run && cd /tmp/run && cat saved-message.eml | /path/to/extractors/my-vendor.py
ls
```

Each `_tests/test_<extractor>.py` exercises the script the same way
against canned messages.

## Available extractors

`order` shown in the first column. Where a vendor is covered by a
narrow extractor, the generic `schema-ld` (order 10) may also fire on
the same message; that's fine - duplicate artifacts with the same
dedup key collapse downstream.

### Generic (order 10-20)

| Extractor         | Order | Trigger                                                              | Emits                  |
|-------------------|-------|----------------------------------------------------------------------|------------------------|
| `schema-ld`       | 10    | Any message with an HTML body. Walks every `application/ld+json` block. | `reservation`, `subscription` |
| `ics-passthrough` | 20    | Message has a `text/calendar` part or a `*.ics` attachment.          | `event`                |

### Vendors (order 50)

| Extractor                  | Sender domain(s)                                            | Emits                       |
|----------------------------|-------------------------------------------------------------|-----------------------------|
| `air-france`               | `service-airfrance.com`                                     | `reservation`               |
| `amazon`                   | `amazon.{co.uk,de,nl,fr,it,es,com}`                         | `parcel`, `receipt`         |
| `bol-com`                  | `bol.com`                                                   | `parcel`, `receipt`         |
| `booking-com`              | `booking.com`, `*.booking.com`                              | `reservation`               |
| `british-airways`          | `email.ba.com`                                              | `reservation`               |
| `deliveroo`                | `deliveroo.com`, `*.deliveroo.com`, `t.deliveroo.com`       | `receipt`, `reservation`    |
| `doctap`                   | `doctap.co.uk`                                              | `reservation`               |
| `dpd`                      | `dpd.co.uk`, `*.dpd.co.uk`                                  | `parcel`, `reservation`     |
| `easyjet`                  | `easyjet.com`, `*.easyjet.com`                              | `reservation`               |
| `eon-next`                 | `eonnext.com`                                               | `bill`                      |
| `eurostar`                 | `eurostar.com`, `*.eurostar.com`                            | `reservation`               |
| `evri`                     | `evri.com`, `*.evri.com`                                    | `parcel`                    |
| `fedex`                    | `fedex.com`, `*.fedex.com`                                  | `parcel`, `reservation`     |
| `google-play`              | `google.com` (Google Play receipts)                         | `receipt`                   |
| `google-reserve`           | `google.com` (Reserve with Google)                          | `reservation`               |
| `klm`                      | `klm.com`                                                   | `reservation`               |
| `kpn-mobiel`               | `kpn.com`                                                   | `bill`                      |
| `kwalitaria`               | `kwalitaria.nl`                                             | `receipt`                   |
| `norwegian`                | `norwegian.com`                                             | `reservation`               |
| `ns`                       | `ns.nl`, `*.ns.nl`                                          | `bill`, `reservation`       |
| `ns-international`         | `confirmation.nsinternational.nl`                           | `reservation`               |
| `parcelforce`              | `parcelforce.co.uk`, `*.parcelforce.co.uk`                  | `parcel`, `reservation`     |
| `postnl`                   | `*.postnl.nl`, `edm.postnl.nl`                              | `parcel`                    |
| `restaurant-information`   | `restaurant-information.com`                                | `reservation`               |
| `royal-mail`               | `royalmail.com`, `*.royalmail.com`                          | `parcel`, `reservation`     |
| `sainsburys`               | `sainsburys.co.uk`, `*.sainsburys.co.uk`, `mail.sainsburys.co.uk` | `reservation`         |
| `sevenrooms`               | `sevenrooms.com`, `*.sevenrooms.com`                        | `reservation`               |
| `shopify-order`            | any sender DKIM-signed by `*.myshopify.com`                 | `parcel`, `receipt`         |
| `stena-line`               | `stenaline.com`                                             | `reservation`               |
| `swiftqueue`               | `swiftqueue.com`                                            | `reservation`               |
| `switch2`                  | `switch2.co.uk`                                             | `bill`                      |
| `thon-hotels`              | `thonhotels.no`, `e.thonhotels.no`                          | `reservation`               |
| `transavia-delay`          | `transavia.com`                                             | `reservation`               |
| `uber`                     | `uber.com`, `*.uber.com`                                    | `receipt`                   |
| `ups`                      | `ups.com`, `*.ups.com`                                      | `parcel`, `reservation`     |
| `yodel`                    | `yodel.co.uk`, `*.yodel.co.uk`                              | `parcel`, `reservation`     |

For the exact subject regex, body requirements, and DKIM constraints,
read the matching `<extractor>.yaml`.
