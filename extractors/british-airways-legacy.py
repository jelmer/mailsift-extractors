#!/usr/bin/env python3
"""British Airways e-ticket receipts, pre-DKIM (2013-era).

Thin wrapper around `british-airways.py` that:

- Enforces a message-date cutoff so a spoofer today can't reach the
  no-DKIM legacy code path. BA started signing outgoing mail with
  DKIM by 2018; anything genuinely older will pre-date the cutoff.
- Reuses the same parser as the modern extractor, so the two paths
  agree byte-for-byte on the output.

The companion manifest `british-airways-legacy.yaml` omits
`require_dkim` (there was nothing to require on pre-DKIM mail) but
keeps a tight `from_domains` + `subject_regex` prefilter.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

# Load the sibling `british-airways.py` via its file path because the
# hyphenated stem isn't a valid Python identifier for a plain import.
_BA_PATH = Path(__file__).parent / "british-airways.py"
_spec = importlib.util.spec_from_file_location("british_airways", _BA_PATH)
assert _spec is not None and _spec.loader is not None
british_airways = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(british_airways)

# Anything on or after this date must have been DKIM-signed and
# should have gone through the DKIM-enforcing main extractor. If
# it reached us here, treat it as suspicious and refuse to file.
_CUTOFF = datetime(2018, 1, 1)


def main() -> int:
    return british_airways.extract(
        british_airways.read_message(), max_message_date=_CUTOFF
    )


if __name__ == "__main__":
    sys.exit(main())
