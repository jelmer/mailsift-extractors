#!/usr/bin/env python3
"""easyJet flight booking confirmations, pre-DKIM (2010-2013).

Thin wrapper around `easyjet.py` that:

- Enforces a message-date cutoff so a spoofer today can't reach the
  no-DKIM legacy code path. easyJet started signing outgoing mail
  with DKIM by 2015; anything genuinely older will pre-date it.
- Reuses the same parser as the modern extractor, so the two paths
  agree byte-for-byte on the output.

The companion manifest `easyjet-legacy.yaml` omits `require_dkim`
(there was nothing to require on pre-DKIM mail) but keeps a tight
`from_domains` + `subject_regex` prefilter.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

_EJ_PATH = Path(__file__).parent / "easyjet.py"
_spec = importlib.util.spec_from_file_location("easyjet", _EJ_PATH)
assert _spec is not None and _spec.loader is not None
easyjet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(easyjet)

# Anything on or after this date must have been DKIM-signed and
# should have reached the main extractor. If it lands here instead,
# treat it as suspicious and refuse.
_CUTOFF = datetime(2015, 1, 1)


def main() -> int:
    return easyjet.extract(easyjet.read_message(), max_message_date=_CUTOFF)


if __name__ == "__main__":
    sys.exit(main())
