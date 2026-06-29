"""Test helpers for extractor pytest modules.

Each test spawns one of the extractor scripts in a fresh tempdir,
pipes a saved `.eml` to its stdin, then reads back whatever files it
produced. The helper returns a mapping `{basename: parsed_body}` so
tests can assert on exact JSON or iCalendar output.

This deliberately mirrors what the Rust pipeline does at runtime: the
extractors' wire contract is "stdin = email, cwd = tempdir, output =
suffix-named files in cwd", and that's exactly what we exercise here.
No Rust binary needed - extractor tests are pure Python.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTORS_DIR = REPO_ROOT / "extractors"
CORPUS_DIR = REPO_ROOT / "tests" / "corpus"


@pytest.fixture
def corpus_dir() -> Path:
    return CORPUS_DIR


def _read_event_stable(text: str) -> str:
    """Strip the wall-clock DTSTAMP line so iCal bodies compare cleanly.

    Mirrors `tests/common::read_event_stable`. Line endings stay as
    `\\r\\n` because RFC 5545 calendars use them and the tests assert on
    full bodies.
    """
    normalised = text.replace("\r\n", "\n")
    kept = [line for line in normalised.split("\n") if not line.startswith("DTSTAMP:")]
    return "\r\n".join(kept).rstrip("\r\n") + "\r\n"


@pytest.fixture
def run_extractor(tmp_path: Path):
    """Return a callable that runs an extractor against an EML.

    Usage:

        out = run_extractor("royal-mail", "royal-mail-out-for-delivery.eml")
        assert out["royalmail-OL000000000GB.parcel.json"]["deliveryStatus"] == "OutForDelivery"

    Returns a dict keyed by output filename. JSON files are parsed; ICS
    files are returned as text with the `DTSTAMP` line stripped so the
    body is deterministic.
    """

    def _run(extractor_name: str, eml_name: str) -> dict[str, Any]:
        eml_path = CORPUS_DIR / eml_name
        if not eml_path.exists():
            raise FileNotFoundError(f"no corpus mail at {eml_path}")
        script = EXTRACTORS_DIR / f"{extractor_name}.py"
        if not script.exists():
            raise FileNotFoundError(f"no extractor at {script}")

        with eml_path.open("rb") as fh:
            subprocess.run(
                [sys.executable, str(script)],
                cwd=tmp_path,
                stdin=fh,
                check=True,
            )

        out: dict[str, Any] = {}
        for child in sorted(tmp_path.iterdir()):
            if not child.is_file():
                continue
            text = child.read_text(encoding="utf-8")
            if child.suffix == ".json":
                out[child.name] = json.loads(text)
            elif child.name.endswith(".ics"):
                out[child.name] = _read_event_stable(text)
            else:
                out[child.name] = text
        return out

    return _run
