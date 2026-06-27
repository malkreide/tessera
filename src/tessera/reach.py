"""Tri-State-Erreichbarkeit: tot != blockiert != netzfehler. Reine stdlib.

Lektion aus der Praxis: umgebungsbedingte Fehler duerfen nicht wie Datenfehler
aussehen. Eine 404/410 ist ein echter, gespeicherter-Link-ist-tot-Befund (Daten);
ein 403/Policy-Block oder ein Verbindungsfehler liegt an der Ausfuehrungsumgebung
(Netz-Policy, kein Browser durch den Proxy) — nicht an den Daten. Wer beides
zusammenwirft, loest Re-Discovery aus, wo nur die Umgebung klemmt, oder uebersieht
echten Link-Rot.

Dieses Modul klassifiziert nur — es macht keine Requests (kein httpx-Import),
damit es ueberall (auch in der dependency-freien CI) importierbar ist. Der
HTTP-Aufruf und das Mapping von Exceptions passieren beim Aufrufer (verify.py).
"""
from __future__ import annotations

# Zustaende. DATA_PROBLEM markiert, welche als echte Datenfehler gelten.
OK = "ok"               # 2xx — erreichbar
DEAD = "tot"            # 404/410 — Ziel existiert nicht mehr (DATENproblem)
BLOCKED = "blockiert"   # 401/403/407/451 — Policy/Auth (UMGEBUNG, kein Datenfehler)
NETERROR = "netzfehler"  # Verbindung/Timeout/DNS/Proxy (UMGEBUNG, kein Datenfehler)
OTHER = "anders"        # uebrige Status (z.B. 5xx) — unklar, als Hinweis behandeln

# Nur diese gelten als echte Datenfehler (harter Stopp moeglich). Block/Netzfehler
# sind Umgebungsbefunde und sollen einen Lauf NICHT als Datenfehler scheitern lassen.
DATA_PROBLEM = frozenset({DEAD})


def classify_status(status: int) -> str:
    """Ordnet einen HTTP-Statuscode einem Tri-State-Zustand zu."""
    if 200 <= status < 300:
        return OK
    if status in (404, 410):
        return DEAD
    if status in (401, 403, 407, 451):
        return BLOCKED
    return OTHER


def is_data_problem(state: str) -> bool:
    """True nur fuer Zustaende, die ein echtes Datenproblem sind (nicht Umgebung)."""
    return state in DATA_PROBLEM
