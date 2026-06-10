#!/usr/bin/env python3
"""Self-Test fuer den Vertrags-Validator — dependency-frei (nur stdlib).

Konvention: Fixtures in examples/ deren Name mit `invalid-` beginnt, MUESSEN den
Validator scheitern lassen; alle uebrigen MUESSEN gueltig sein. So dient der
intentional-ungueltige Fall als positiver Nachweis, dass der Check greift.

Aufruf:
    python tests/run_checks.py
Exit-Code 0 = alle Erwartungen erfuellt, 1 = mindestens eine Abweichung.
Geeignet als CI-Schritt.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from validate_contract import validate_file  # noqa: E402


def main() -> int:
    fixtures = sorted((ROOT / "examples").glob("*.json"))
    if not fixtures:
        print("Keine Fixtures in examples/ gefunden.", file=sys.stderr)
        return 1

    failures = 0
    for path in fixtures:
        expect_valid = not path.name.startswith("invalid-")
        rep = validate_file(path)
        if rep.ok == expect_valid:
            print(f"[PASS] {path.name} (erwartet {'gueltig' if expect_valid else 'ungueltig'})")
        else:
            failures += 1
            got = "gueltig" if rep.ok else "ungueltig"
            want = "gueltig" if expect_valid else "ungueltig"
            print(f"[FAIL] {path.name}: erwartet {want}, war {got}")
            for e in rep.errors:
                print(f"       ! {e}")

    print(f"\n{len(fixtures) - failures}/{len(fixtures)} Erwartung(en) erfuellt.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
