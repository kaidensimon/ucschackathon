"""Council against solo models, from the command line.

    python -m council.bench.compare_cli --solo solo.json --council council.json
                                        [--tags tags.json] [--md out.md]

--solo     a solo report (read by council.bench.solo_import.load_solo_report).
--council  what a finished bench run wrote for the council condition. Accepted:
           - a bench out dir (its results.jsonl, or council/results.jsonl)
           - a results.jsonl: BenchResult lines {"id", "mode", "correct", ...}; the rows of mode
             "council" are used (else the first mode starting with "council", never random_council)
           - a report.json (extra.results_files points at the per-mode files)
           - a plain {"task_id": true/false} object
           - a list of {"task_id" or "id", "correct", optional "category"}
           - {"results": [...]} wrapping any of the lists above
--tags     task -> category: {"task": "cat"} or a list of {"id"/"task_id", "category"}.
--md       also write the markdown table to this file.

Exit 0 on success, 2 when an input is missing, unreadable or holds no usable rows.
The sibling modules are imported inside main(), so this file loads without them.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Optional, TextIO

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_BROKEN = 1


class InputError(Exception):
    """A file is missing or has nothing usable. main() turns this into exit 2."""


# ------------------------------------------------------------------ reading files


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"file not found: {path}") from None
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from None
    try:
        return json.loads(text)
    except ValueError:
        pass
    rows: list[Any] = []  # not one JSON value: try JSON lines
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            raise InputError(f"{path}: not JSON (line {n})") from None
    return rows


def _task_id(row: dict) -> Optional[str]:
    for key in ("task_id", "id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _pick_mode(rows: list[dict]) -> list[dict]:
    """Rows that carry a mode: keep the council condition only."""
    modes = [str(r["mode"]) for r in rows if isinstance(r.get("mode"), str)]
    if not modes:
        return rows
    seen = list(dict.fromkeys(modes))
    if "council" in seen:
        chosen = "council"
    else:
        names = [m for m in seen if m.startswith("council") and not m.startswith("random")]
        if not names:
            raise InputError("no council rows in the results (modes found: " + ", ".join(seen) + ")")
        chosen = names[0]
    return [r for r in rows if r.get("mode") == chosen]


def _rows_to_maps(rows: list[Any]) -> tuple[dict[str, bool], dict[str, str]]:
    dicts = [r for r in rows if isinstance(r, dict)]
    correct: dict[str, bool] = {}
    cats: dict[str, str] = {}
    for row in _pick_mode(dicts):
        tid = _task_id(row)
        if tid is None or "correct" not in row:
            continue
        correct[tid] = row["correct"] is True  # ungraded counts as wrong, as in the bench report
        cat = row.get("category")
        if isinstance(cat, str) and cat:
            cats[tid] = cat
    return correct, cats


def _from_report(path: Path, data: dict) -> tuple[dict[str, bool], dict[str, str]]:
    files = ((data.get("extra") or {}).get("results_files")) or {}
    rel = files.get("council")
    if not rel:
        names = [k for k in files if str(k).startswith("council") and not str(k).startswith("random")]
        rel = files[names[0]] if names else None
    if not rel:
        raise InputError(f"{path}: report has no council results file")
    return load_council(path.parent / str(rel))


def load_council(path: Path) -> tuple[dict[str, bool], dict[str, str]]:
    """(task -> correct, task -> category) for the council condition of a bench run."""
    path = Path(path)
    if path.is_dir():
        for rel in ("results.jsonl", "council/results.jsonl", "report.json"):
            if (path / rel).is_file():
                return load_council(path / rel)
        raise InputError(f"no results.jsonl or report.json in folder {path}")
    data = _read_json(path)
    if isinstance(data, dict) and "rows" in data and "extra" in data:
        return _from_report(path, data)
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        data = data["results"]
    elif isinstance(data, dict) and "correct" in data and _task_id(data):
        data = [data]  # a one-line results.jsonl parses as a single object
    if isinstance(data, dict):
        correct = {str(k): v is True for k, v in data.items() if isinstance(v, bool) or v is None}
        cats: dict[str, str] = {}
    elif isinstance(data, list):
        correct, cats = _rows_to_maps(data)
    else:
        raise InputError(f"{path}: unknown council file format")
    if not correct:
        raise InputError(f"{path}: no usable council rows (need task id and correct)")
    return correct, cats


def load_tags(path: Path) -> dict[str, str]:
    """task -> category from a tags file."""
    data = _read_json(Path(path))
    if isinstance(data, dict) and isinstance(data.get("tags"), (dict, list)):
        data = data["tags"]
    out: dict[str, str] = {}
    if isinstance(data, dict):
        out = {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and _task_id(row) and isinstance(row.get("category"), str):
                out[_task_id(row)] = row["category"]  # type: ignore[index]
    if not out:
        raise InputError(f"{path}: no usable tags (need task -> category)")
    return out


# ------------------------------------------------------------------ main


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m council.bench.compare_cli",
        description="Compare the council against solo models on the same benchmark tasks.",
    )
    p.add_argument("--solo", required=True, type=Path, help="solo report file")
    p.add_argument("--council", required=True, type=Path, help="council results (bench out dir or file)")
    p.add_argument("--tags", type=Path, default=None, help="task -> category file")
    p.add_argument("--md", type=Path, default=None, help="write the markdown table here")
    return p


def _meta_value(meta: Any, key: str) -> Optional[dict]:
    value = meta.get(key) if isinstance(meta, dict) else None
    return value if isinstance(value, dict) and value else None


def main(argv: Optional[list[str]] = None, out: Optional[TextIO] = None) -> int:
    stream = out if out is not None else sys.stdout
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # argparse already printed the usage problem
        return EXIT_OK if exc.code in (0, None) else EXIT_BAD_INPUT

    try:
        solo_import = importlib.import_module("council.bench.solo_import")
        compare_mod = importlib.import_module("council.bench.compare")
        text_mod = importlib.import_module("council.bench.compare_text")
    except ImportError as exc:
        print(f"compare_cli: needed module missing: {exc}", file=sys.stderr)
        return EXIT_BROKEN

    try:
        for label, path in (("solo", args.solo), ("council", args.council), ("tags", args.tags)):
            if path is not None and not Path(path).exists():
                raise InputError(f"{label} file not found: {path}")
        try:
            solo, meta = solo_import.load_solo_report(Path(args.solo))
        except InputError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise InputError(f"solo file {args.solo} unusable: {exc}") from None
        if not solo:
            raise InputError(f"solo file {args.solo} holds no usable rows")
        council, council_cats = load_council(Path(args.council))
        categories = dict(council_cats)
        if args.tags is not None:
            categories.update(load_tags(Path(args.tags)))  # tags file wins
    except InputError as exc:
        print(f"compare_cli: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT

    kwargs: dict[str, Any] = {}
    if categories:
        kwargs["categories"] = categories
    # compare() wants seat_models as a list of model ids (a dict's values are taken).
    seat_models = meta.get("seat_models") if isinstance(meta, dict) else None
    if isinstance(seat_models, dict):
        seat_models = list(seat_models.values())
    if isinstance(seat_models, (list, tuple)) and seat_models:
        kwargs["seat_models"] = [str(m) for m in seat_models]
    latency = _meta_value(meta, "latency")
    if latency:
        kwargs["latency"] = latency

    try:
        report = compare_mod.compare(solo, council, **kwargs)
        table = text_mod.table(report)
        by_cat_fn = getattr(text_mod, "by_category_table", None)
        by_cat = by_cat_fn(report) if categories and callable(by_cat_fn) else ""
        if isinstance(by_cat, str) and by_cat:
            table = f"{table}\n\n{by_cat}"
        markdown = text_mod.markdown(report) if args.md is not None else ""
    except Exception as exc:
        print(f"compare_cli: compare failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_BROKEN

    print(table, file=stream)
    if args.md is not None:
        try:
            Path(args.md).parent.mkdir(parents=True, exist_ok=True)
            Path(args.md).write_text(markdown, encoding="utf-8")
        except OSError as exc:
            print(f"compare_cli: cannot write {args.md}: {exc}", file=sys.stderr)
            return EXIT_BROKEN
        print(f"markdown written: {args.md}", file=stream)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
