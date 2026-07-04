#!/usr/bin/env python3
"""List the discovered extractors and their dispatch hints.

Scans this directory for `*.yaml` manifests the same way the pipeline
does - files whose names start with `.` or `_` are skipped - and prints
what each manifest declares: name, order, and the `from_domains`,
`subject_regex`, `requires` and `require_dkim` hints.

By default it prints a table sorted by `order` then name. Pass `--json`
for the raw manifest data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = Path(__file__).resolve().parent / "extractors"


def discover(directory: Path) -> list[dict[str, Any]]:
    """Load every manifest in `directory`, mirroring loader discovery rules."""
    manifests = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith((".", "_")):
            continue
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: manifest is not a mapping")
        if "name" not in data:
            raise ValueError(f"{path.name}: manifest has no 'name'")
        manifests.append(data)
    manifests.sort(key=lambda m: (m.get("order", 100), m["name"]))
    return manifests


def _hints(manifest: dict[str, Any]) -> str:
    parts = []
    domains = manifest.get("from_domains")
    if domains:
        parts.append(", ".join(domains))
    subject = manifest.get("subject_regex")
    if subject:
        parts.append(f"subject: {subject}")
    requires = manifest.get("requires")
    if requires:
        parts.append(f"requires: {', '.join(requires)}")
    dkim = manifest.get("require_dkim")
    if dkim:
        parts.append(f"dkim: {', '.join(dkim)}")
    return "; ".join(parts)


def _print_table(manifests: list[dict[str, Any]]) -> None:
    rows = [(m["name"], str(m.get("order", 100)), _hints(m)) for m in manifests]
    headers = ("Extractor", "Order", "Dispatch hints")
    if not rows:
        print("no extractors found")
        return
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(3)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row).rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List discovered extractors.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the raw manifest data as JSON instead of a table",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=MANIFEST_DIR,
        help="directory to scan for manifests (default: this directory)",
    )
    args = parser.parse_args(argv)

    manifests = discover(args.dir)
    if args.json:
        json.dump(manifests, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(manifests)
    return 0


if __name__ == "__main__":
    sys.exit(main())
