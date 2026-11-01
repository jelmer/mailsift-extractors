#!/usr/bin/env python3
"""KLM booking confirmations from before KLM signed with DKIM.

Thin wrapper around `klm.py` that enforces a message-date cutoff so
a spoofer today can't reach the no-DKIM code path. Every
`noreply@klm.com` confirmation seen (2012 to March 2019) is
unsigned; the first `klm.com`-signed mail seen is from August 2021.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

# Load the sibling `klm.py` by path, matching the other legacy wrappers.
_KLM_PATH = Path(__file__).parent / "klm.py"
_spec = importlib.util.spec_from_file_location("klm", _KLM_PATH)
assert _spec is not None and _spec.loader is not None
klm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(klm)

# Date of the first DKIM-signed `klm.com` mail seen. Anything on or
# after it should have reached the main extractor; if it lands here
# instead, treat it as suspicious and refuse.
_CUTOFF = datetime(2021, 8, 30)


def main() -> int:
    return klm.extract(klm.read_message(), max_message_date=_CUTOFF)


if __name__ == "__main__":
    sys.exit(main())
