#!/usr/bin/env python3
"""Tests fuer den Schutz der Ausgabe-Kette (`tessera.runguard` + CLI-Verdrahtung).

Anlass (Lauf L5, 2026-11-27): Ein abgelaufener API-Key brach `extract` mit HTTP
401 fuer alle Leistungen ab; in einem frueheren Versuch liefen die Folgeschritte
danach still auf alten `out/<id>.json`. Geprueft wird:

  * 401/403 werden erkannt, auch als Ursache in der Exception-Kette; 429/529 nicht,
  * `retire_previous` verschiebt nach `*.prev` statt zu loeschen,
  * `stale_reason` erkennt eine Ausgabe, die aelter ist als der letzte Crawl,
  * `extract` laeuft nach einem gewoehnlichen Fehler mit der naechsten Leistung
    weiter, bricht bei abgelehnter Anmeldung oder fehlendem Key den Lauf ab und
    hinterlaesst fuer eine gescheiterte Leistung keine `out/<id>.json`,
  * `validate` und `pr` verweigern eine veraltete Ausgabe.

Die runguard-Tests sind reine stdlib. Die CLI-Tests brauchen pydantic und pyyaml
(`tessera.config`); ohne sie werden sie sauber uebersprungen, nicht stillschweigend
bestanden.

Aufruf: python tests/test_runguard.py — Exit 0 = alle Tests gruen.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tessera import runguard  # noqa: E402


class _Skip(Exception):
    pass


class _HTTPError(Exception):
    """Steht fuer pydantic-ai `ModelHTTPError` / anthropic `APIStatusError`."""

    def __init__(self, status_code: int, message: str = "error") -> None:
        super().__init__(message)
        self.status_code = status_code


# --- runguard (stdlib) -------------------------------------------------------


def test_auth_status_direct_and_chained() -> None:
    assert runguard.auth_status(_HTTPError(401)) == 401
    assert runguard.auth_status(_HTTPError(403)) == 403
    try:
        try:
            raise _HTTPError(401, "invalid x-api-key")
        except _HTTPError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert runguard.auth_status(outer) == 401, "401 als Ursache muss erkannt werden"


def test_auth_status_ignores_other_errors() -> None:
    for status in (400, 429, 500, 529):
        assert runguard.auth_status(_HTTPError(status)) is None, status
    assert runguard.auth_status(ValueError("x")) is None
    weird = _HTTPError(401)
    weird.status_code = "401"  # kein int -> nicht raten
    assert runguard.auth_status(weird) is None


def test_describe_is_short_single_line() -> None:
    text = runguard.describe(_HTTPError(529, "overloaded\n" + "x" * 1000))
    assert text.startswith("_HTTPError (HTTP 529): overloaded"), text
    assert "\n" not in text and len(text) < 400, len(text)
    assert runguard.describe(ValueError()) == "ValueError"


def test_missing_key_is_system_exit() -> None:
    assert issubclass(runguard.MissingKeyError, SystemExit)


def test_retire_previous_moves_not_deletes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "a.json"
        flags = Path(tmp) / "a.flags.json"
        missing = Path(tmp) / "b.json"
        out.write_text("neu", encoding="utf-8")
        flags.write_text("[]", encoding="utf-8")
        (Path(tmp) / "a.json.prev").write_text("uralt", encoding="utf-8")
        moved = runguard.retire_previous([out, flags, missing])
        assert not out.exists() and not flags.exists()
        assert [p.name for p in moved] == ["a.json.prev", "a.flags.json.prev"], moved
        assert (Path(tmp) / "a.json.prev").read_text(encoding="utf-8") == "neu"


def test_stale_reason() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "x.json"
        meta = Path(tmp) / "raw" / "x" / "meta.json"
        meta.parent.mkdir(parents=True)
        out.write_text("{}", encoding="utf-8")
        assert runguard.stale_reason(out, meta) == "", "ohne Crawl-Metadaten nicht veraltet"
        meta.write_text("[]", encoding="utf-8")
        os.utime(out, (1000, 1000))
        os.utime(meta, (2000, 2000))
        reason = runguard.stale_reason(out, meta)
        assert "aelter als der letzte Crawl" in reason and "x/meta.json" in reason, reason
        os.utime(out, (3000, 3000))
        assert runguard.stale_reason(out, meta) == ""


# --- CLI-Verdrahtung (braucht pydantic + pyyaml) ----------------------------


def _cli():
    try:
        from tessera import cli, steps  # noqa: PLC0415
    except ImportError as exc:
        raise _Skip(f"tessera.cli nicht importierbar ({exc})") from exc
    return cli, steps


@contextlib.contextmanager
def _sandbox(cli, steps, run_extract):
    """OUT/RAW auf ein Temp-Verzeichnis, steps.run_extract ersetzt."""
    saved = (cli.OUT, cli.RAW, steps.run_extract)
    with tempfile.TemporaryDirectory() as tmp:
        cli.OUT, cli.RAW = Path(tmp) / "out", Path(tmp) / "raw"
        steps.run_extract = run_extract
        err = io.StringIO()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                yield cli.OUT, cli.RAW, err
        finally:
            cli.OUT, cli.RAW, steps.run_extract = saved


def _cfg(*ids: str):
    procs = [SimpleNamespace(id=i, paused="") for i in ids]
    return SimpleNamespace(processes=procs, by_id=lambda i: next(p for p in procs if p.id == i))


def _ok():
    return SimpleNamespace(process={"steps": [{}, {}]}, flags=[])


def test_extract_continues_after_ordinary_error() -> None:
    cli, steps = _cli()
    calls = []

    def fake(proc):
        calls.append(proc.id)
        if proc.id == "b":
            raise _HTTPError(529, "overloaded")
        return _ok()

    with _sandbox(cli, steps, fake) as (out, _raw, err):
        out.mkdir()
        (out / "b.json").write_text('{"alt": true}', encoding="utf-8")
        rc = cli.cmd_extract(_cfg("a", "b", "c"), None)
        assert rc == 1, rc
        assert calls == ["a", "b", "c"], calls
        assert (out / "a.json").exists() and (out / "c.json").exists()
        assert not (out / "b.json").exists(), "gescheiterte Leistung darf keine out/<id>.json behalten"
        assert (out / "b.json.prev").exists(), "vorige Ausgabe muss als .prev liegen bleiben"
        text = err.getvalue()
        assert "HTTP 529" in text and "fehlgeschlagen fuer: b" in text, text


def test_extract_aborts_run_on_rejected_login() -> None:
    cli, steps = _cli()
    calls = []

    def fake(proc):
        calls.append(proc.id)
        try:
            raise _HTTPError(401, "invalid x-api-key")
        except _HTTPError as inner:
            raise RuntimeError("model error") from inner

    with _sandbox(cli, steps, fake) as (out, _raw, err):
        rc = cli.cmd_extract(_cfg("a", "b", "c"), None)
        assert rc == 1 and calls == ["a"], (rc, calls)
        assert not any(out.glob("*.json")), list(out.glob("*"))
        text = err.getvalue()
        assert "HTTP 401" in text and "nicht versucht: b, c" in text, text
        assert "Traceback" not in text


def test_extract_aborts_run_on_missing_key() -> None:
    cli, steps = _cli()
    calls = []

    def fake(proc):
        calls.append(proc.id)
        raise runguard.MissingKeyError("LLM-Key fehlt: ENV-Variable ANTHROPIC_API_KEY ist nicht gesetzt")

    with _sandbox(cli, steps, fake) as (_out, _raw, err):
        rc = cli.cmd_extract(_cfg("a", "b"), None)
        assert rc == 1 and calls == ["a"], (rc, calls)
        assert "nicht versucht: b" in err.getvalue(), err.getvalue()


def test_extract_system_exit_only_ends_that_process() -> None:
    cli, steps = _cli()

    def fake(proc):
        if proc.id == "a":
            raise SystemExit("Antwort am Token-Limit abgeschnitten")
        return _ok()

    with _sandbox(cli, steps, fake) as (out, _raw, _err):
        rc = cli.cmd_extract(_cfg("a", "b"), None)
        assert rc == 1 and (out / "b.json").exists() and not (out / "a.json").exists()


def test_validate_and_pr_refuse_stale_output() -> None:
    cli, steps = _cli()
    with _sandbox(cli, steps, None) as (out, raw, err):
        out.mkdir()
        (out / "a.json").write_text("{}", encoding="utf-8")
        meta = raw / "a" / "meta.json"
        meta.parent.mkdir(parents=True)
        meta.write_text("[]", encoding="utf-8")
        os.utime(out / "a.json", (1000, 1000))
        os.utime(meta, (2000, 2000))
        assert cli.cmd_validate(_cfg("a"), None) == 1
        assert cli.cmd_pr(_cfg("a"), None) == 1
        text = err.getvalue()
        assert text.count("aelter als der letzte Crawl") == 2, text
        assert "KEIN PR" in text, text


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    skipped = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"[SKIP] {t.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} Tests gruen, {skipped} uebersprungen.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
