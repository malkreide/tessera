"""Pre-Flight-Checks (Pflicht vor jedem Crawl).

1. Katalog KONSUMIEREN, nicht entdecken: I14Y Public API (Behoerdenleistungen,
   ohne Auth) und eCH-0070-Leistungsinventar (XLSX) abrufen; Abdeckung pro
   kuratierter Leistung nach reports/coverage.md schreiben.
2. Rechtsflaeche pruefen: robots.txt jeder Quell-Domain gegen unseren
   User-Agent auswerten; Funde nach reports/scraping-compliance.md. Bei
   Disallow wird die Leistung GESPERRT (der Crawler verweigert sie).
3. Nutzungsbedingungen (ToU-Gate): die rechtliche Einschaetzung trifft der
   Maintainer und erfasst sie je Domain in sources.yaml (`terms_of_use`:
   verdict, reviewed_at, basis, version_marker). Gecrawlt wird nur, wenn fuer
   JEDE Domain einer Leistung `erlaubt` mit Beleg vorliegt UND die gepruefte
   Fassung (version_marker) noch woertlich auf der Live-ToU-Seite steht —
   geaenderte Bedingungen oder eine umgezogene Seite sperren von selbst.

Das Gate VERFAELLT nach MAX_GATE_AGE_DAYS: robots.txt kann sich aendern, ein
altes «erlaubt» ist keine Freigabe mehr — dann erst `tessera preflight` erneut.

Zweites, rein redaktionelles Gate: `paused` in sources.yaml. Eine Leistung mit
nicht-leerem `paused`-Grund ist fuer die automatische Extraktion GESPERRT
(crawl/extract/pr verweigern sie), bleibt aber in der Liste — preflight,
verify, fingerprint, diff und eval lesen und ueberwachen sie weiter.

Modul-Importe sind reine stdlib (httpx/openpyxl lazy in den Fetch-Funktionen),
damit die Gate-Logik (load_gate/require_allowed) in der dependency-freien CI
testbar ist — wie grounding/binding/risk.
"""

from __future__ import annotations

import io
import json
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:  # nur Typhinweise — kein Laufzeit-Import von config (pydantic/yaml)
    from .config import ProcessSource, SourcesConfig

# Repo-Wurzel ohne config-Import (src/tessera/preflight.py -> parents[2]),
# damit das Modul stdlib-importierbar bleibt (wie verify.py/diff.py).
ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
GATE_FILE = REPORTS / "raw" / "preflight-gate.json"

# Maximales Alter eines Preflight-Ergebnisses in Tagen. Aelter -> Gate verfallen,
# Crawl verweigert (robots.txt/ToU koennen sich geaendert haben).
MAX_GATE_AGE_DAYS = 7

# UA-Token, auf das robots.txt-Regeln matchen (erste Komponente des User-Agent).
UA_TOKEN = "tessera"

# Moegliche Verdikte einer ToU-Pruefung (terms_of_use in sources.yaml). Nur
# `erlaubt` gibt frei; die Einschaetzung trifft der Maintainer, nie der Code.
TOU_VERDICTS = ("ausstehend", "erlaubt", "verboten")
_TOU_MISSING = "keine ToU-Pruefung erfasst (terms_of_use in sources.yaml)"


def _fetch_i14y(url: str, ua: str) -> list[str]:
    """Holt alle Behoerdenleistungs-Namen (de) aus der I14Y Public API."""
    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar

    names: list[str] = []
    page = 1
    with httpx.Client(headers={"User-Agent": ua}, timeout=30) as client:
        while True:
            r = client.get(url, params={"page": page, "pageSize": 100})
            r.raise_for_status()
            data = r.json().get("data", [])
            for svc in data:
                name = (svc.get("name") or {}).get("de") or ""
                kw = [(k.get("de") or "") for k in (svc.get("keywords") or []) if isinstance(k, dict)]
                names.append(" · ".join(s for s in [name, *kw] if s).strip())
            total_pages = int(r.headers.get("x-paging-totalpages", page))
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)
    return names


# Groessen-Guard fuer das extern geladene XLSX: openpyxl parst ZIP-Container;
# ein unerwartet grosses Artefakt (Zip-Bomb, falsche Datei hinter dem Link)
# wird gar nicht erst geparst, sondern als Befund gemeldet (-> coverage.md).
MAX_XLSX_BYTES = 20 * 1024 * 1024


def _fetch_ech0070(url: str, ua: str) -> list[str]:
    """Holt die deutschen Leistungsbezeichnungen aus dem eCH-0070-Inventar."""
    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar
    import openpyxl  # noqa: PLC0415

    with httpx.Client(headers={"User-Agent": ua}, timeout=60, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
    if len(r.content) > MAX_XLSX_BYTES:
        raise RuntimeError(
            f"eCH-0070-XLSX ist {len(r.content)} Bytes (> {MAX_XLSX_BYTES}) — "
            "wird nicht geparst; Quelle pruefen."
        )
    wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)
    sheet = next((n for n in wb.sheetnames if "Leistungsinventar" in n), None)
    if sheet is None:
        raise RuntimeError(f"Kein Leistungsinventar-Sheet in {wb.sheetnames}")
    ws = wb[sheet]
    rows = ws.iter_rows(min_row=1, values_only=True)
    header = [str(c or "") for c in next(rows)]
    col = next((i for i, h in enumerate(header) if h.startswith("Leistungsergebnis")), None)
    if col is None:
        raise RuntimeError(f"Spalte 'Leistungsergebnis' nicht gefunden: {header}")
    return [str(row[col]) for row in rows if row[col]]


def _matches(names: list[str], keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for n in names:
        low = n.lower()
        if any(k.lower() in low for k in keywords):
            hits.append(n)
    return hits


def _robots_for_host(host: str, ua: str) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
    """Laedt und parst robots.txt einer Domain. (parser, status_notiz)."""
    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar

    rp = urllib.robotparser.RobotFileParser()
    url = f"https://{host}/robots.txt"
    try:
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=20)
    except httpx.HTTPError as exc:
        return None, f"robots.txt nicht abrufbar ({exc.__class__.__name__})"
    if r.status_code != 200:
        # Kein robots.txt => keine maschinenlesbare Einschraenkung.
        return None, f"robots.txt HTTP {r.status_code} (keine Regeln)"
    rp.parse(r.text.splitlines())
    return rp, "robots.txt geladen"


def _fetch_tou_page(url: str, ua: str) -> tuple[str, str]:
    """Ruft die ToU-Seite einer Domain ab: (tri_state, lesbarer Text).
    Netzfehler -> netzfehler; Statuscodes ueber reach.classify_status."""
    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar

    from . import reach  # noqa: PLC0415
    from .verify import extract_text  # noqa: PLC0415

    try:
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=30, follow_redirects=True)
    except httpx.HTTPError:
        return reach.NETERROR, ""
    state = reach.classify_status(r.status_code)
    return state, (extract_text(r.text) if state == reach.OK else "")


def tou_check(review: dict | None, page: tuple[str, str] | None, today: date | None = None) -> str | None:
    """Prueft eine ToU-Pruefung (Eintrag aus terms_of_use) gegen die Live-Seite.

    Rueckgabe: None = freigegeben, sonst der Sperrgrund. Freigegeben ist eine
    Domain NUR, wenn der Maintainer `erlaubt` mit Datum, Begruendung (`basis`)
    und `version_marker` erfasst hat UND dieser Marker noch woertlich auf der
    erreichbaren ToU-Seite steht. Aendert sich die Fassung oder zieht die Seite
    um, sperrt das Gate von selbst — eine alte Freigabe gilt nicht fuer neue
    Bedingungen."""
    from . import reach  # noqa: PLC0415
    from .grounding import normalize  # noqa: PLC0415

    if not review:
        return _TOU_MISSING
    verdict = str(review.get("verdict") or "ausstehend")
    basis = str(review.get("basis") or "").strip()
    reviewed_at = str(review.get("reviewed_at") or "").strip()
    if verdict == "verboten":
        return f"Nutzungsbedingungen verbieten die Nutzung (geprueft {reviewed_at or '—'}): {basis or '—'}"
    if verdict != "erlaubt":
        return "ToU-Pruefung ausstehend — der Maintainer entscheidet (terms_of_use in sources.yaml)"
    try:
        if date.fromisoformat(reviewed_at) > (today or date.today()):
            return f"reviewed_at {reviewed_at!r} liegt in der Zukunft"
    except ValueError:
        return f"reviewed_at fehlt oder ist kein Datum (YYYY-MM-DD): {reviewed_at!r}"
    if not basis:
        return "Begruendung (basis) fehlt — «erlaubt» braucht einen nachvollziehbaren Beleg"
    marker = str(review.get("version_marker") or "").strip()
    if not marker:
        return "version_marker fehlt — ohne Kennung der gepruefte Fassung ist eine Aenderung nicht erkennbar"
    if page is None:
        return "ToU-Seite nicht abgerufen"
    state, text = page
    if state != reach.OK:
        return f"ToU-Seite {review.get('url')} nicht pruefbar ({state}) — gepruefte Fassung nicht bestaetigt"
    if normalize(marker) not in normalize(text):
        return (
            f"gepruefte Fassung «{marker}» steht nicht mehr auf der ToU-Seite — "
            "Nutzungsbedingungen geaendert? erneut pruefen"
        )
    return None


def tou_blocked_hosts(urls: list[str], reasons_by_host: dict[str, str | None]) -> dict[str, str]:
    """Sperrgruende je Domain einer Leistung: jede ihrer Quell-Domains muss
    freigegeben sein. Eine Domain ohne Eintrag gilt als nicht geprueft."""
    out: dict[str, str] = {}
    for host in sorted({urlsplit(u).netloc for u in urls}):
        reason = reasons_by_host.get(host, _TOU_MISSING)
        if reason is not None:
            out[host] = reason
    return out


def run_preflight(cfg: SourcesConfig, only: list[str] | None = None) -> dict[str, dict]:
    """Fuehrt alle Checks aus, schreibt Reports und das Gate-File.

    Rueckgabe: {proc_id: {"allowed": bool, "blocked_urls": [...],
    "tou_allowed": bool, "tou_blocked": {domain: grund}, "checked_at": ...}}
    """
    today = date.today().isoformat()
    ua = cfg.crawler.user_agent
    procs = [p for p in cfg.processes if not only or p.id in only]

    # --- 1. Katalog-Abdeckung -------------------------------------------------
    i14y_names: list[str] = []
    i14y_err = ""
    try:
        i14y_names = _fetch_i14y(cfg.catalog.i14y_publicservices_url, ua)
    except Exception as exc:  # Report statt Crash: Befund gehoert in coverage.md
        i14y_err = f"{exc.__class__.__name__}: {exc}"
    ech_names: list[str] = []
    ech_err = ""
    try:
        ech_names = _fetch_ech0070(cfg.catalog.ech0070_inventory_url, ua)
    except Exception as exc:
        ech_err = f"{exc.__class__.__name__}: {exc}"

    lines = [
        "# Abdeckung der kuratierten Leistungen in den Katalogen",
        "",
        f"Stand: {today} — erzeugt durch `tessera preflight` (Katalog wird",
        "konsumiert, nicht entdeckt; kuratierte Liste: `sources.yaml`).",
        "",
        "- I14Y Public API (Behoerdenleistungen): "
        + (f"{len(i14y_names)} Eintraege" if not i14y_err else f"FEHLER — {i14y_err}"),
        "- eCH-0070-Leistungsinventar (V4.2.0, XLSX): "
        + (f"{len(ech_names)} Eintraege" if not ech_err else f"FEHLER — {ech_err}"),
        "",
        "| Leistung (kuratiert) | I14Y-Treffer | eCH-0070-Treffer |",
        "|---|---|---|",
    ]

    def fmt(hits: list[str]) -> str:
        if not hits:
            return "—  (kommunale Leistung, kein Bundes-Eintrag)"
        more = f" (+{len(hits) - 4})" if len(hits) > 4 else ""
        return "; ".join(h[:60].replace("|", "/") for h in hits[:4]) + more

    for p in procs:
        i_hits = _matches(i14y_names, p.catalog_keywords)
        e_hits = _matches(ech_names, p.catalog_keywords)
        lines.append(f"| `{p.id}` ({p.service_name}) | {fmt(i_hits)} | {fmt(e_hits)} |")
    lines += [
        "",
        "Hinweis: Beide Kataloge sind auf Bundes-/Kantonsebene gepflegt; rein",
        "kommunale Leistungen der Stadt Zuerich koennen ohne Treffer bleiben.",
        "Das ist ein dokumentierter Befund, kein Fehler.",
        "",
    ]
    (REPORTS / "coverage.md").write_text("\n".join(lines), encoding="utf-8")

    # --- 2. Rechtsflaeche (robots.txt + ToU) ----------------------------------
    gate: dict[str, dict] = {}
    hosts = sorted({urlsplit(u).netloc for p in procs for u in p.official_urls})
    robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {
        h: _robots_for_host(h, ua) for h in hosts
    }
    # ToU-Gate: Pruefung des Maintainers (terms_of_use) gegen die Live-Seite.
    reviews = {h: r.model_dump() for h, r in cfg.terms_of_use.items()}
    tou_reasons: dict[str, str | None] = {}
    for h in hosts:
        review = reviews.get(h)
        page = _fetch_tou_page(review["url"], ua) if review and review.get("url") else None
        tou_reasons[h] = tou_check(review, page)

    clines = [
        "# Scraping-Compliance (robots.txt & Nutzungsbedingungen)",
        "",
        f"Stand: {today} — erzeugt durch `tessera preflight`.",
        "",
        "## Respekt-Regeln (fix)",
        "",
        f"- **User-Agent:** identifizierend — `{ua}`",
        f"- **Rate-Limit:** {cfg.crawler.delay_seconds}s Pause zwischen Requests, Backoff bei Fehlern",
        "- **Keine** Umgehung von Logins, Captchas oder anderen Schutzmassnahmen",
        "- **Keine** personenbezogenen Daten in URLs, Query-Strings oder Logs",
        "",
        "## Domains",
        "",
        "| Domain | robots.txt | Nutzungsbedingungen | ToU-Pruefung (Maintainer) | ToU-Gate |",
        "|---|---|---|---|---|",
    ]

    def cell(text: object) -> str:
        return str(text).replace("|", "/").replace("\n", " ")

    for h in hosts:
        _, note = robots[h]
        review = reviews.get(h)
        if review:
            url = review.get("url") or ""
            terms_md = f"[{url}]({url})" if url else "— (URL nachtragen)"
            marker = review.get("version_marker") or "—"
            review_md = (
                f"{review.get('verdict')} (geprueft {review.get('reviewed_at') or '—'}; Fassung «{marker}»)"
            )
        else:
            terms_md, review_md = "— (nicht erfasst)", "—"
        reason = tou_reasons[h]
        gate_md = "frei" if reason is None else f"**GESPERRT** — {reason}"
        clines.append(f"| {h} | {note} | {cell(terms_md)} | {cell(review_md)} | {cell(gate_md)} |")

    clines += ["", "## Geprüfte URLs", "", "| Leistung | URL | robots-Verdikt |", "|---|---|---|"]
    for p in procs:
        blocked: list[str] = []
        for u in p.official_urls:
            rp, _ = robots[urlsplit(u).netloc]
            allowed = rp.can_fetch(UA_TOKEN, u) if rp else True
            if not allowed:
                blocked.append(u)
            clines.append(f"| `{p.id}` | {u} | {'erlaubt' if allowed else '**DISALLOW — nicht crawlen**'} |")
        tou_blocked = tou_blocked_hosts(p.official_urls, tou_reasons)
        gate[p.id] = {
            "allowed": not blocked,
            "blocked_urls": blocked,
            "tou_allowed": not tou_blocked,
            "tou_blocked": tou_blocked,
            "checked_at": today,
        }

    clines += [
        "",
        "## Crawl-Gate je Leistung",
        "",
        "| Leistung | robots | Nutzungsbedingungen |",
        "|---|---|---|",
    ]
    for pid, entry in gate.items():
        robots_md = "frei" if entry["allowed"] else "**GESPERRT**"
        tou_md = "frei" if entry["tou_allowed"] else "**GESPERRT** (" + ", ".join(entry["tou_blocked"]) + ")"
        clines.append(f"| `{pid}` | {robots_md} | {tou_md} |")
    clines += [
        "",
        "Verdikt-Logik: Eine Leistung wird nur gecrawlt, wenn ALLE ihre URLs",
        "fuer unseren User-Agent erlaubt sind (robots.txt) UND fuer JEDE ihrer",
        "Domains eine ToU-Pruefung des Maintainers mit Verdikt «erlaubt», Datum,",
        "Begruendung und Fassungs-Kennung vorliegt, deren Fassung noch auf der",
        "Live-Seite steht (terms_of_use in sources.yaml). Sonst: gesperrt —",
        "Ruecksprache mit dem Maintainer noetig.",
        "",
    ]
    (REPORTS / "scraping-compliance.md").write_text("\n".join(clines), encoding="utf-8")

    GATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATE_FILE.write_text(json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")
    return gate


def load_gate() -> dict[str, dict]:
    if not GATE_FILE.exists():
        return {}
    return json.loads(GATE_FILE.read_text(encoding="utf-8"))


def gate_age_days(entry: dict) -> int | None:
    """Alter eines Gate-Eintrags in Tagen. None bei fehlendem/ungueltigem
    checked_at oder einem Datum in der Zukunft (beides gilt als nicht frisch)."""
    try:
        age = (date.today() - date.fromisoformat(str(entry.get("checked_at")))).days
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


def require_allowed(proc: ProcessSource) -> None:
    """Crawl-Gate: ohne frischen, positiven Preflight wird nicht gecrawlt.

    Frisch heisst: checked_at hoechstens MAX_GATE_AGE_DAYS alt. robots.txt und
    Nutzungsbedingungen koennen sich aendern — ein altes «erlaubt» ist keine
    Freigabe mehr; das war bisher nur ein Docstring-Versprechen.
    """
    gate = load_gate()
    entry = gate.get(proc.id)
    if entry is None:
        raise SystemExit(
            f"[{proc.id}] Kein Preflight-Ergebnis gefunden — zuerst `tessera preflight` ausfuehren."
        )
    age = gate_age_days(entry)
    if age is None or age > MAX_GATE_AGE_DAYS:
        raise SystemExit(
            f"[{proc.id}] Preflight-Ergebnis ist nicht frisch "
            f"(checked_at={entry.get('checked_at')!r}, max. {MAX_GATE_AGE_DAYS} Tage) — "
            "robots.txt kann sich geaendert haben; zuerst `tessera preflight` erneut ausfuehren."
        )
    if not entry["allowed"]:
        raise SystemExit(
            f"[{proc.id}] robots.txt verbietet das Crawlen von {entry['blocked_urls']} — "
            "Leistung gesperrt; bitte Maintainer fragen (siehe reports/scraping-compliance.md)."
        )
    # ToU-Gate: nur ein ausdrueckliches True gibt frei. Ein Gate-File ohne das
    # Feld (aelteres Format) ist KEINE Freigabe.
    tou_ok = entry.get("tou_allowed")
    if tou_ok is not True:
        if tou_ok is None:
            detail = "Preflight-Ergebnis ohne ToU-Pruefung (aelteres Format) — `tessera preflight` erneut ausfuehren"
        else:
            blocked = entry.get("tou_blocked") or {}
            detail = "; ".join(f"{h}: {r}" for h, r in sorted(blocked.items())) or "ohne Grund gesperrt"
        raise SystemExit(
            f"[{proc.id}] Nutzungsbedingungen nicht freigegeben — {detail}. Crawl gesperrt "
            "(siehe reports/scraping-compliance.md; Pruefung erfassen: terms_of_use in sources.yaml)."
        )


def paused_reason(proc: object) -> str:
    """Grund, aus dem die automatische Extraktion dieser Leistung gesperrt ist
    (`paused` in sources.yaml); leer = nicht gesperrt."""
    reason = getattr(proc, "paused", "")
    return reason.strip() if isinstance(reason, str) else ""


def require_extraction_enabled(proc: object) -> None:
    """Extraktions-Gate: eine in sources.yaml pausierte Leistung wird weder
    gecrawlt noch extrahiert noch als PR eingereicht. Hart (SystemExit), damit
    auch ein direkter Aufruf oder alte Snapshots nichts ausloesen.

    Ueberwachung (preflight/verify/fingerprint/diff/eval) ist davon unberuehrt —
    sie liest nur und erzeugt keine Daten fuer die Maschinerie."""
    reason = paused_reason(proc)
    if reason:
        raise SystemExit(
            f"[{getattr(proc, 'id', '?')}] Automatische Extraktion gesperrt: {reason} — "
            "Freischaltung: `paused` in sources.yaml entfernen."
        )
