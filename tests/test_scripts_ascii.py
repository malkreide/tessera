#!/usr/bin/env python3
"""PowerShell-Skripte muessen reines ASCII sein — reine stdlib.

Windows PowerShell 5.1 (Standard unter Windows) liest eine .ps1-Datei ohne
BOM als Windows-1252, nicht als UTF-8. Ein UTF-8-Gedankenstrich («—», Bytes
E2 80 94) wird dann zu «â€”», und 0x94 ist dort ein typografisches
Anfuehrungszeichen, das PowerShell als String-Ende liest -> Parse-Fehler.
ASCII ist in jeder Lesart identisch.

Aufruf: python tests/test_scripts_ascii.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_powershell_scripts_are_ascii() -> None:
    scripts = sorted((ROOT / "scripts").glob("*.ps1"))
    assert scripts, "keine .ps1-Skripte gefunden"
    bad = []
    for path in scripts:
        for no, line in enumerate(path.read_bytes().split(b"\n"), start=1):
            if any(b > 0x7F for b in line):
                bad.append(f"{path.relative_to(ROOT)}:{no}: {line.decode('utf-8', 'replace').strip()}")
    assert not bad, "Nicht-ASCII in PowerShell-Skripten (bricht PS 5.1):\n" + "\n".join(bad)


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
