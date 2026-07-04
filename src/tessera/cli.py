"""tessera CLI — schlichte Schleife ueber die kuratierten Leistungen.

    tessera preflight [--id ...]   Katalog-Abdeckung + robots/ToU-Check (Pflicht)
    tessera crawl     [--id ...]   Quellseiten -> Markdown-Snapshots
    tessera extract   [--id ...]   Snapshots -> Vertrags-JSON (LLM, Grounding-Gate)
    tessera validate  [--id ...]   Vertrags-Validator auf out/<id>.json
    tessera verify    [--id ...] [--online]
                                   Re-Verifikation: Label<->Wert (netzfrei) und
                                   mit --online Link-Rot (tri-state) + Beleg-Drift
    tessera pr        [--id ...]   Draft-PR-Bundle bauen / einreichen
    tessera fingerprint [--id ...] Aenderungs-Baseline schreiben (reports/fingerprints/)
    tessera diff      [--id ...] [--fail-on-change]
                                   Live-Quellseiten gegen die Baseline diffen
                                   (v2 Aenderungs-Erkennung; ergaenzt `verify`)
    tessera run       [--id ...]   alles oben in Reihenfolge
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .config import ROOT, SourcesConfig, load_sources

OUT = ROOT / "out"
FLAGS_SUFFIX = ".flags.json"


def _procs(cfg: SourcesConfig, ids: list[str] | None):
    if not ids:
        return cfg.processes
    return [cfg.by_id(i) for i in ids]


def cmd_preflight(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import preflight  # noqa: PLC0415

    gate = preflight.run_preflight(cfg, only=ids)
    print("Preflight abgeschlossen -> reports/coverage.md, reports/scraping-compliance.md")
    blocked = {k: v for k, v in gate.items() if not v["allowed"]}
    for pid, entry in gate.items():
        status = "GESPERRT (robots)" if pid in blocked else "freigegeben"
        print(f"  {pid}: {status}")
    if blocked:
        print("Gesperrte Leistungen NICHT crawlen — Maintainer fragen.", file=sys.stderr)
    return 0


def cmd_crawl(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import crawl  # noqa: PLC0415

    for proc in _procs(cfg, ids):
        print(f"Crawle {proc.id} …")
        crawl.crawl_process(proc, cfg)
    return 0


def cmd_extract(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import crawl, extract, grounding, schema  # noqa: PLC0415

    OUT.mkdir(exist_ok=True)
    rc = 0
    for proc in _procs(cfg, ids):
        print(f"Extrahiere {proc.id} …")
        corpus_text, meta, url_texts = crawl.load_corpus(proc.id)
        ok_meta = [m for m in meta if m["http_status"] == 200 and m["chars"] > 0]
        if not ok_meta:
            print(f"  [{proc.id}] Keine brauchbaren Snapshots — uebersprungen.", file=sys.stderr)
            rc = 1
            continue

        x = extract.extract_process(proc, corpus_text)
        retrieved_at = max(m["retrieved_at"] for m in ok_meta)
        process, step_quotes, doc_quotes = schema.to_contract(
            x,
            proc_id=proc.id,
            target_audience=proc.target_audience,  # kuratiert, nie LLM-inferiert
            source_url=proc.official_urls[0],
            retrieved_at=retrieved_at,
        )
        # Per-URL-Grounding: Reference-Zitate muessen auf der Seite ihrer
        # source_url stehen, nicht bloss irgendwo im Gesamt-Korpus.
        corpus_by_url = {u: grounding.Corpus(t) for u, t in url_texts.items()}
        process, flags = grounding.apply_gate(
            process,
            step_quotes,
            grounding.Corpus(corpus_text),
            doc_quotes,
            corpus_by_url=corpus_by_url,
        )
        out_json = OUT / f"{proc.id}.json"
        out_json.write_text(
            json.dumps(process, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (OUT / f"{proc.id}{FLAGS_SUFFIX}").write_text(
            json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  [{proc.id}] -> {out_json} ({len(process['steps'])} Schritte, {len(flags)} Flags)")
        for f in flags:
            print(f"    ⚠ {f}")
    return rc


def cmd_validate(cfg: SourcesConfig, ids: list[str] | None) -> int:
    rc = 0
    for proc in _procs(cfg, ids):
        out_json = OUT / f"{proc.id}.json"
        if not out_json.exists():
            print(f"  [{proc.id}] out/{proc.id}.json fehlt — zuerst `tessera extract`.", file=sys.stderr)
            rc = 1
            continue
        # Eingangskontrolle fuer JEDE Ausgabe: der Vertrags-Validator muss Exit 0 liefern.
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_contract.py"), str(out_json)]
        )
        rc = rc or result.returncode
    return rc


def cmd_verify(cfg: SourcesConfig, ids: list[str] | None, online: bool = False) -> int:
    """Re-Verifikation bestehender Ausgaben (propose-only, schreibt nie in out/).

    Netzfrei: Label<->Wert-Befunde. Mit --online zusaetzlich tri-state
    Erreichbarkeit (tot/blockiert/netzfehler) und Beleg-Drift gegen die
    Live-Seite. Exit 1 NUR bei echten Datenproblemen (toter Link / Drift);
    Umgebungsbefunde (Block/Netzfehler/SPA) lassen den Lauf nicht scheitern.
    """
    from . import verify as verify_mod  # noqa: PLC0415

    rc = 0
    fetch = None
    client = None
    if online:
        import httpx  # noqa: PLC0415 — nur im Online-Modus

        ua = cfg.crawler.user_agent
        client = httpx.Client(
            headers={"User-Agent": ua}, timeout=30, follow_redirects=True
        )
        fetch = verify_mod.make_http_fetcher(client)
    try:
        for proc in _procs(cfg, ids):
            out_json = OUT / f"{proc.id}.json"
            if not out_json.exists():
                print(f"  [{proc.id}] out/{proc.id}.json fehlt — zuerst `tessera extract`.", file=sys.stderr)
                rc = 1
                continue
            process = json.loads(out_json.read_text(encoding="utf-8"))
            rep = verify_mod.verify_process(process, fetch=fetch)
            report_path = verify_mod.write_report(rep)
            lv, dead, drift = len(rep.label_value), len(rep.dead_links), len(rep.drift_hits)
            print(
                f"  [{proc.id}] -> {report_path} "
                f"(Label<->Wert: {lv}, tote Links: {dead}, Drift: {drift})"
            )
            for f in rep.label_value:
                print(f"    ⚠ Reference {f.reference_id} «{f.label}»: {f.detail}")
            for l in rep.dead_links:
                print(f"    ❌ toter Link: {l.url} ({l.status})")
            for d in rep.drift_hits:
                print(f"    ❌ Drift: Reference {d.reference_id} «{d.label}» — {d.source_url}")
            if rep.data_problem:
                rc = 1
    finally:
        if client is not None:
            client.close()
    return rc


def _make_ssr_fetcher(cfg: SourcesConfig):
    """Online-Fetcher fuer fingerprint/diff: (fetch, client). fetch(url) ->
    (markdown, tri_state), gleicher SSR-Pfad wie der Crawl (httpx+Trafilatura),
    damit Hashes zwischen Fingerprint- und Diff-Zeit vergleichbar sind."""
    import httpx  # noqa: PLC0415

    from . import crawl  # noqa: PLC0415

    client = httpx.Client(
        headers={"User-Agent": cfg.crawler.user_agent}, timeout=30, follow_redirects=True
    )

    def fetch(url: str):
        md, _status, _raw, state = crawl._ssr_fetch(client, url)
        return md, state

    return fetch, client


def cmd_fingerprint(cfg: SourcesConfig, ids: list[str] | None) -> int:
    """Schreibt/aktualisiert die Aenderungs-Baseline reports/fingerprints/<id>.json
    (SHA-256 ueber den normalisierten Seitentext je Quell-URL). Nach einem Lauf
    ausfuehren und das Ergebnis committen — `tessera diff` vergleicht dagegen."""
    from datetime import date  # noqa: PLC0415

    from . import diff as diff_mod  # noqa: PLC0415

    today = date.today().isoformat()
    fetch, client = _make_ssr_fetcher(cfg)
    try:
        for proc in _procs(cfg, ids):
            entries = diff_mod.build_entries(proc, fetch, today)
            path = diff_mod.write_fingerprints(proc.id, entries, today)
            usable = [e for e in entries if "sha256" in e]
            print(f"  [{proc.id}] Fingerprint -> {path} ({len(usable)}/{len(entries)} URLs erfasst)")
            for e in entries:
                if "sha256" not in e:
                    print(f"    ⚠ nicht erfasst (Umgebungsbefund): {e['url']} ({e['state']})")
    finally:
        client.close()
    return 0


def cmd_diff(
    cfg: SourcesConfig,
    ids: list[str] | None,
    fail_on_change: bool = False,
    as_json: bool = False,
) -> int:
    """Vergleicht die Live-Quellseiten gegen die committete Fingerprint-Baseline
    und meldet inhaltliche Aenderungen (Re-Extraktion pruefen). Exit 1 bei totem
    Link immer; bei inhaltlicher Aenderung nur mit --fail-on-change. Block/
    Netzfehler/SPA und neu/entfernt sind Hinweise (nicht-fatal).

    Mit --json wird eine maschinenlesbare Zusammenfassung nach stdout geschrieben
    (menschliche Zeilen dann nach stderr) — der change-diff-Cron liest das und
    oeffnet/aktualisiert daraus ein GitHub-Issue."""
    from . import diff as diff_mod  # noqa: PLC0415

    def out(msg: str) -> None:
        print(msg, file=sys.stderr if as_json else sys.stdout)

    rc = 0
    results: list[dict] = []
    fetch, client = _make_ssr_fetcher(cfg)
    try:
        for proc in _procs(cfg, ids):
            rep = diff_mod.diff_process(proc, fetch)
            results.append(diff_mod.report_to_dict(rep))
            if rep.no_baseline:
                out(
                    f"  [{proc.id}] keine Baseline (reports/fingerprints/{proc.id}.json) "
                    "— uebersprungen. Erst `tessera fingerprint` ausfuehren + committen."
                )
                continue
            out(
                f"  [{proc.id}] geaendert: {len(rep.changed)}, tot: {len(rep.dead)}, "
                f"env: {len(rep.env)}, neu: {len(rep.new)}, entfernt: {len(rep.removed)}, "
                f"unveraendert: {len(rep.unchanged)}"
            )
            for u in rep.changed:
                out(f"    ✏ geaendert — Re-Extraktion pruefen: {u}")
            for u in rep.dead:
                out(f"    ❌ toter Link: {u}")
            for u in rep.new:
                out(f"    + neu in sources, noch keine Baseline: {u}")
            for u in rep.removed:
                out(f"    - in Baseline, nicht mehr in sources: {u}")
            for e in rep.env:
                out(f"    · Umgebungsbefund (nicht-fatal): {e}")
            if rep.dead:
                rc = 1  # toter Link ist immer ein Datenproblem
            if fail_on_change and rep.changed:
                rc = 1
    finally:
        client.close()
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    return rc


def cmd_pr(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import pr as pr_mod  # noqa: PLC0415
    from .crawl import RAW  # noqa: PLC0415

    rc = 0
    for proc in _procs(cfg, ids):
        out_json = OUT / f"{proc.id}.json"
        flags_file = OUT / f"{proc.id}{FLAGS_SUFFIX}"
        if not out_json.exists():
            print(f"  [{proc.id}] out/{proc.id}.json fehlt.", file=sys.stderr)
            rc = 1
            continue
        if cmd_validate(cfg, [proc.id]) != 0:
            print(f"  [{proc.id}] Validierung fehlgeschlagen — KEIN PR.", file=sys.stderr)
            rc = 1
            continue
        process = json.loads(out_json.read_text(encoding="utf-8"))
        flags = json.loads(flags_file.read_text(encoding="utf-8")) if flags_file.exists() else []
        meta = json.loads((RAW / proc.id / "meta.json").read_text(encoding="utf-8"))
        # Lokales Artefakt vorab schreiben (struktur-only); open_draft_pr merged
        # bei Bedarf gegen die bestehende Zieldatei und ueberschreibt das Bundle
        # mit dem tatsaechlich eingereichten (gemergten) Stand.
        body = pr_mod.build_pr_body(proc, process, flags, meta)
        pr_mod.write_bundle(proc, process, body)
        pr_mod.open_draft_pr(proc, process, flags, meta)
    return rc


COMMANDS = {
    "preflight": cmd_preflight,
    "crawl": cmd_crawl,
    "extract": cmd_extract,
    "validate": cmd_validate,
    "pr": cmd_pr,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tessera", description=__doc__)
    parser.add_argument("command", choices=[*COMMANDS, "verify", "fingerprint", "diff", "run"])
    parser.add_argument("--id", action="append", dest="ids", metavar="LEISTUNG",
                        help="nur diese Leistung(en) verarbeiten")
    parser.add_argument("--online", action="store_true",
                        help="nur fuer `verify`: Live-Erreichbarkeit + Beleg-Drift pruefen")
    parser.add_argument("--fail-on-change", action="store_true",
                        help="nur fuer `diff`: Exit 1 auch bei inhaltlicher Seitenaenderung")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="nur fuer `diff`: maschinenlesbare Zusammenfassung nach stdout")
    args = parser.parse_args(argv)

    cfg = load_sources()
    if args.command == "run":
        for name in ("preflight", "crawl", "extract", "validate", "pr"):
            rc = COMMANDS[name](cfg, args.ids)
            if rc != 0:
                print(f"Abbruch in Schritt {name!r} (Exit {rc}).", file=sys.stderr)
                return rc
        return 0
    if args.command == "verify":
        return cmd_verify(cfg, args.ids, online=args.online)
    if args.command == "fingerprint":
        return cmd_fingerprint(cfg, args.ids)
    if args.command == "diff":
        return cmd_diff(cfg, args.ids, fail_on_change=args.fail_on_change, as_json=args.as_json)
    return COMMANDS[args.command](cfg, args.ids)


if __name__ == "__main__":
    raise SystemExit(main())
