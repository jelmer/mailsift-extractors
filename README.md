# mailsift-extractors

Per-vendor extractor scripts and tests for [mailsift](https://github.com/jelmer/mailsift).

Each extractor turns one incoming RFC822 email into zero or more
structured artifacts (calendar events, parcel records, receipts,
bills). The mailsift pipeline discovers them at startup by scanning
for `*.yaml` manifests in the configured extractors directory.

The full extractor contract - manifest fields, dispatch semantics,
artifact filenames, debugging recipes - is documented in
[extractors/README.md](extractors/README.md).

## Layout

```
extractors/
  <vendor>.yaml         manifest
  <vendor>.py           script (or whatever language; just be executable)
  _lib/                 shared Python helper module
  _tests/               pytest harness
tests/
  corpus/               saved .eml fixtures
```

## Running the tests

```sh
pip install pytest
pytest extractors/_tests
```

## Available extractors

Run `./list.py` to print the discovered extractors with their `order`
and dispatch hints (`from_domains`, `subject_regex`, `requires`,
`require_dkim`), read straight from the manifests. Pass `--json` for the
raw manifest data. For the full detail of any one extractor, read its
`<extractor>.yaml`.
