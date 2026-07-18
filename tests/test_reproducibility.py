#!/usr/bin/env python3
"""Guard fuer die Reproduzierbarkeits-Pins (Schritt 3). Reine stdlib.

Haelt die «eine Wahrheitsquelle» ehrlich: jedes Paket, das die CI-Crons via
`pip install -c constraints.txt <pakete>` installieren, MUSS in constraints.txt
exakt gepinnt sein. Sonst wuerde ein Cron eine ungepinnte (driftende) Version
ziehen — genau das, was die Lock-Datei verhindern soll.

Aufruf: python tests/test_reproducibility.py — Exit 0 = alle Tests gruen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS = ROOT / "constraints.txt"
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "link-rot.yml",
    ROOT / ".github" / "workflows" / "change-diff.yml",
]

_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.+!-]*)$")
# `pip install ... -c constraints.txt pkg1 pkg2 ...` — die Pakete nach der Referenz.
_INSTALL = re.compile(r"-c\s+constraints\.txt\s+(.+)")


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _PIN.match(line)
        assert m, f"constraints.txt: Zeile ist kein exakter Pin: {line!r}"
        pins[m.group(1).lower()] = m.group(2)
    return pins


def test_constraints_parse_as_exact_pins() -> None:
    pins = _pins()
    assert pins, "constraints.txt enthaelt keine Pins."


def test_workflow_packages_are_all_pinned() -> None:
    pins = _pins()
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        m = _INSTALL.search(text)
        assert m, f"{wf.name}: kein `-c constraints.txt <pakete>`-Install gefunden."
        pkgs = m.group(1).split()
        assert pkgs, f"{wf.name}: leere Paketliste."
        for pkg in pkgs:
            name = re.split(r"[<>=!~ ]", pkg, 1)[0].lower()
            assert name in pins, (
                f"{wf.name}: Paket {name!r} wird installiert, ist aber nicht in "
                "constraints.txt gepinnt (Drift-Risiko)."
            )


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} Tests gruen.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
