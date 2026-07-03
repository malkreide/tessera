"""Vertrags-Konstanten — EINE Wahrheitsquelle, reine stdlib.

Kanonisch ist das Schema im Repo `maschinerie-zuerich`
(`docs/process-data-contract.md`, `schemas/opengov-process-schema.json`). tessera
gleicht sich darauf ab. `SCHEMA_VERSION` ist die Version, die tessera ERZEUGT und
ERWARTET; sie wird von `schema.to_contract` (Ausgabe) und vom Vertrags-Validator
(Pruefung) gemeinsam genutzt, damit beide nie auseinanderlaufen.

Schema-Versionierung / Bump-Prozess (wenn das Ziel-Repo die Version anhebt):
  1. Die kanonische Aenderung im Ziel-Repo lesen (MAJOR = Breaking; Migrationsskript).
  2. `SCHEMA_VERSION` hier nachziehen und die betroffenen Felder in `schema.py`
     und `scripts/validate_contract.py` anpassen.
  3. Fixtures/Tests aktualisieren; `docs/data-contract.md` abgleichen.
  4. Bei Unsicherheit ueber die kanonische Bedeutung: stoppen und fragen
     (Cross-Repo-Grenze; nicht raten).

Der Validator behandelt eine ABWEICHENDE `schema_version` als Hinweis (nicht als
Fehler): eine kanonische Datei aus dem Ziel-Repo darf einer neueren/aelteren
Contract-Generation angehoeren, ohne dass tessera sie faelschlich ablehnt — der
Hinweis signalisiert nur, dass tessera ggf. nachzuziehen ist.
"""
from __future__ import annotations

import re

# Vertragsversion, die tessera erzeugt und erwartet (SemVer). Beim kanonischen
# Bump hier UND in schema.py/validate_contract.py nachziehen (siehe oben).
SCHEMA_VERSION = "0.1.0"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def is_semver(value: object) -> bool:
    return isinstance(value, str) and bool(_SEMVER.match(value))


def major(version: str) -> int | None:
    """MAJOR-Teil einer SemVer (fuer Breaking-Change-Erkennung). None wenn ungueltig."""
    if not is_semver(version):
        return None
    return int(version.split(".", 1)[0])
