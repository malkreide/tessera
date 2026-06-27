"""Re-Verifikation bestehender Ausgaben: Link-Rot + Beleg-Drift. Propose-only.

Drei Befundklassen, getrennt gehalten:

1. **Label<->Wert** (netzfrei): benennt ein Reference-Label einen bindenden Wert,
   den sein source_quote gar nicht belegt? (Mechanischer Teil von «richtige Seite,
   falscher Wert».)
2. **Erreichbarkeit** (online): jede source_url tri-state pruefen — tot (404/410)
   != blockiert (403/Policy) != netzfehler. Nur «tot» ist ein Datenproblem; Block/
   Netzfehler sind Umgebungsbefunde und lassen den Lauf NICHT scheitern.
3. **Drift** (online): steht jedes verifizierte source_quote noch WOERTLICH auf
   der Live-Seite? Identische Normalisierung wie beim Speichern (grounding.Corpus).
   Eine erkannte JS-SPA (App-Shell statt Inhalt) wird als «ungeprueft — braucht
   Rendering» gemeldet, nicht als Drift (Umgebungs-Ehrlichkeit).

Dieses Modul SCHREIBT NIE in out/-Daten. Es erzeugt einen Report unter
reports/verify/<id>.md und liefert ein VerifyReport zurueck. Der HTTP-Fetch ist
injizierbar (`fetch`-Callable), damit der netzfreie Teil ohne httpx testbar ist;
`import httpx` passiert ausschliesslich im echten Fetcher (lazy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import reach
from .binding import label_value_mismatch
from .grounding import Corpus

# ROOT lokal berechnen (nicht aus .config), damit das Modul ohne pydantic/yaml
# importierbar bleibt — der netzfreie Teil laeuft so in der dependency-freien CI.
ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "verify"

# App-Shell-Marker echter SPAs: gerendert kommt nur eine Huelle, der Inhalt erst
# per JS. Substring-Suche im Roh-HTML.
_SPA_MARKERS = (
    "window.__nuxt__", "__nuxt_data__", "__next_data__", 'id="__next"',
    "data-server-rendered", "ng-version", "window.__initial_state__",
    "data-reactroot",
)
# Unter so wenig lesbarem Text gehen wir von einer leeren Huelle aus.
_SPA_MIN_TEXT = 200

_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


@dataclass
class Fetched:
    """Ergebnis eines URL-Abrufs (vom Fetcher geliefert)."""

    state: str            # reach.OK / DEAD / BLOCKED / NETERROR / OTHER
    status: int | None = None
    text: str = ""        # lesbarer Text (nur sinnvoll bei state == OK)
    spa: bool = False     # App-Shell vermutet (Inhalt erst per JS)


@dataclass
class LinkState:
    url: str
    state: str
    status: int | None
    detail: str = ""


@dataclass
class DriftFinding:
    reference_id: object
    label: str
    source_url: str
    kind: str             # 'ok' | 'drift' | 'ungeprueft' | 'unerreichbar'
    detail: str = ""


@dataclass
class LabelValueFinding:
    reference_id: object
    label: str
    detail: str


@dataclass
class VerifyReport:
    proc_id: str
    online: bool
    links: list[LinkState] = field(default_factory=list)
    drifts: list[DriftFinding] = field(default_factory=list)
    label_value: list[LabelValueFinding] = field(default_factory=list)

    @property
    def dead_links(self) -> list[LinkState]:
        return [l for l in self.links if l.state == reach.DEAD]

    @property
    def drift_hits(self) -> list[DriftFinding]:
        return [d for d in self.drifts if d.kind == "drift"]

    @property
    def data_problem(self) -> bool:
        """Echtes Datenproblem (harter Stopp): toter Link oder Beleg-Drift.

        Block/Netzfehler/SPA-ungeprueft zaehlen NICHT — das sind Umgebungsbefunde.
        """
        return bool(self.dead_links or self.drift_hits)


def _ref_label(ref: dict) -> str:
    label = ref.get("label")
    if isinstance(label, dict) and isinstance(label.get("de"), str):
        return label["de"]
    return "?"


def looks_like_spa(raw_html: str, text: str) -> bool:
    low = raw_html.lower()
    if any(m in low for m in _SPA_MARKERS):
        return True
    return len(text.strip()) < _SPA_MIN_TEXT


def extract_text(raw_html: str) -> str:
    """Roh-HTML -> lesbarer Text. Trafilatura, wenn verfuegbar; sonst Tag-Strip."""
    try:
        import trafilatura  # noqa: PLC0415
        out = trafilatura.extract(raw_html, include_links=True, include_tables=True)
        if out:
            return out
    except Exception:
        pass
    stripped = _SCRIPT_STYLE.sub(" ", raw_html)
    return _TAG.sub(" ", stripped)


def make_http_fetcher(client, *, results_cache: dict | None = None):
    """Baut einen `fetch(url) -> Fetched` ueber einen offenen httpx.Client.

    Exceptions werden auf Tri-State gemappt (Verbindung/Timeout/Proxy ->
    netzfehler), Statuscodes ueber reach.classify_status. Ergebnisse werden je
    URL gecacht (eine URL kann als Prozess- und als Reference-Quelle auftauchen).
    """
    import httpx  # noqa: PLC0415 — nur im echten Fetcher (CI bleibt dependency-frei)

    cache: dict = results_cache if results_cache is not None else {}

    def fetch(url: str) -> Fetched:
        if url in cache:
            return cache[url]
        try:
            r = client.get(url)
        except httpx.HTTPError:
            # Verbindung/Timeout/DNS/Proxy: Umgebung, kein Datenfehler.
            res = Fetched(state=reach.NETERROR)
            cache[url] = res
            return res
        state = reach.classify_status(r.status_code)
        if state != reach.OK:
            res = Fetched(state=state, status=r.status_code)
        else:
            text = extract_text(r.text)
            res = Fetched(
                state=reach.OK,
                status=r.status_code,
                text=text,
                spa=looks_like_spa(r.text, text),
            )
        cache[url] = res
        return res

    return fetch


def verify_process(process: dict, *, fetch=None) -> VerifyReport:
    """Prueft ein Vertrags-JSON. Ohne `fetch` nur netzfreie Label<->Wert-Befunde.

    `process` wird nie mutiert.
    """
    proc_id = str(process.get("id", "?"))
    rep = VerifyReport(proc_id=proc_id, online=fetch is not None)
    refs = process.get("references") or []

    # --- 1. Label<->Wert (netzfrei) ------------------------------------------
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("status", "verifiziert") != "verifiziert":
            continue
        quote = ref.get("source_quote") or ""
        mismatch = label_value_mismatch(_ref_label(ref), quote)
        if mismatch:
            rep.label_value.append(
                LabelValueFinding(ref.get("reference_id"), _ref_label(ref), mismatch)
            )

    if fetch is None:
        return rep

    # --- 2. Erreichbarkeit (online, tri-state) -------------------------------
    urls: list[str] = []
    seen: set[str] = set()
    for u in [process.get("source_url"), *[r.get("source_url") for r in refs if isinstance(r, dict)]]:
        if isinstance(u, str) and u and u not in seen:
            seen.add(u)
            urls.append(u)
    fetched: dict[str, Fetched] = {}
    for u in urls:
        f = fetch(u)
        fetched[u] = f
        detail = {
            reach.DEAD: "Ziel existiert nicht mehr (404/410) — Re-Discovery noetig",
            reach.BLOCKED: "Policy/Auth (403/451) — Umgebung, kein Datenfehler",
            reach.NETERROR: "Verbindung/Timeout/Proxy — Umgebung, kein Datenfehler",
            reach.OTHER: "unerwarteter Status",
            reach.OK: "erreichbar",
        }.get(f.state, "")
        rep.links.append(LinkState(u, f.state, f.status, detail))

    # --- 3. Beleg-Drift (online) ---------------------------------------------
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("status", "verifiziert") != "verifiziert":
            continue
        quote = ref.get("source_quote") or ""
        if not quote.strip():
            continue
        url = ref.get("source_url")
        f = fetched.get(url) if isinstance(url, str) else None
        rid, label = ref.get("reference_id"), _ref_label(ref)
        if f is None or f.state != reach.OK:
            rep.drifts.append(DriftFinding(
                rid, label, str(url), "unerreichbar",
                f"Seite {f.state if f else 'unbekannt'} — Drift nicht pruefbar (Umgebung)",
            ))
        elif Corpus(f.text).contains(quote):
            rep.drifts.append(DriftFinding(rid, label, str(url), "ok", "Zitat unveraendert auffindbar"))
        elif f.spa:
            rep.drifts.append(DriftFinding(
                rid, label, str(url), "ungeprueft",
                "JS-SPA / App-Shell — Zitat nur per Browser-Rendering pruefbar",
            ))
        else:
            rep.drifts.append(DriftFinding(
                rid, label, str(url), "drift",
                "Zitat NICHT mehr woertlich auf der Seite — Quelle hat sich geaendert",
            ))
    return rep


def render_report(rep: VerifyReport) -> str:
    lines = [
        f"# Re-Verifikation: `{rep.proc_id}`",
        "",
        f"Modus: {'online (Erreichbarkeit + Drift)' if rep.online else 'netzfrei (nur Label<->Wert)'}.",
        "Dieser Report aendert KEINE Daten (propose-only).",
        "",
        "## Label<->Wert",
        "",
    ]
    if rep.label_value:
        for f in rep.label_value:
            lines.append(f"- ⚠️ Reference {f.reference_id} «{f.label}»: {f.detail}")
    else:
        lines.append("- Keine Auffaelligkeit: belegte Labels passen zum Werttyp ihres Zitats.")

    if rep.online:
        lines += ["", "## Erreichbarkeit (tri-state)", "", "| URL | Status | Befund |", "|---|---|---|"]
        for l in rep.links:
            code = l.status if l.status is not None else "—"
            lines.append(f"| {l.url} | **{l.state}** ({code}) | {l.detail} |")

        lines += ["", "## Beleg-Drift", ""]
        if rep.drifts:
            icon = {"ok": "✅", "drift": "❌", "ungeprueft": "🟡", "unerreichbar": "⚪"}
            for d in rep.drifts:
                lines.append(
                    f"- {icon.get(d.kind, '•')} Reference {d.reference_id} «{d.label}»: "
                    f"{d.detail} ({d.source_url})"
                )
        else:
            lines.append("- Keine verifizierten References mit Zitat zu pruefen.")

    lines += [
        "",
        "## Verdikt",
        "",
        f"- Datenproblem (harter Stopp): **{'JA' if rep.data_problem else 'nein'}** "
        f"({len(rep.dead_links)} tote Link(s), {len(rep.drift_hits)} Drift-Treffer)",
        "- Umgebungsbefunde (Block/Netzfehler/SPA-ungeprueft) zaehlen bewusst NICHT "
        "als Datenproblem.",
        "",
    ]
    return "\n".join(lines)


def write_report(rep: VerifyReport) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{rep.proc_id}.md"
    out.write_text(render_report(rep), encoding="utf-8")
    return out
