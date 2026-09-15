"""CLI entry point.

Usage:
  # Self-test (synthetic bars, no network) — verifies resolver + detector
  python -m research.cli --self-test

  # Real run on the droplet:
  #   1) download bars into a cache directory
  #   2) point CachedFileSource at it
  python -m research.cli \
      --detector BREAKOUT_INSIDE_DAY_CONTINUATION \
      --cache-dir data/research_bars \
      --symbols-file config/universe.json \
      --start 2020-01-01 --end 2026-01-01

Never touches production. All output under `research/results/`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

from .cells import CELLS_BY_DETECTOR
from .data import BarSource, CachedFileSource, ResilientSource, YFinanceSource
from .detectors._base import Detector
from .detectors.breakout_inside_day_continuation import BreakoutInsideDayContinuation
from .report import build_stats, write_results
from .runner import run_detector


DETECTORS: dict[str, type[Detector]] = {
    "BREAKOUT_INSIDE_DAY_CONTINUATION": BreakoutInsideDayContinuation,
}


def _load_symbols(symbols_file: str) -> list[str]:
    p = Path(symbols_file)
    if p.suffix.lower() == ".json":
        u = json.loads(p.read_text())
        syms: set[str] = set()
        for sec in u.get("sectors", []):
            syms.update(c for c in sec.get("candidates", []))
        return sorted(syms)
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def _make_source(cache_dir: str | None) -> BarSource:
    sources: list[BarSource] = []
    if cache_dir:
        sources.append(CachedFileSource(cache_dir))
    # yfinance last-ditch; on the droplet you might want AlpacaSource first —
    # commented out to avoid requiring env vars in the CLI default path.
    sources.append(YFinanceSource())
    return ResilientSource(sources)


def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    detector_cls = DETECTORS.get(args.detector)
    if detector_cls is None:
        print(f"unknown detector: {args.detector}. options: {sorted(DETECTORS)}", file=sys.stderr)
        return 2
    detector = detector_cls()
    source = _make_source(args.cache_dir)
    symbols = _load_symbols(args.symbols_file)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    occurrences, manifest = run_detector(
        detector=detector, symbols=symbols, source=source,
        start=start, end=end, max_bars=args.max_bars, spy_source=source,
    )
    cells = CELLS_BY_DETECTOR[args.detector]
    stats = build_stats(occurrences, cells)
    out_dir = Path("research/results")
    run_dir = write_results(out_dir, args.detector, occurrences, stats, manifest)
    print(f"OK. results in: {run_dir}")
    return 0


def _self_test(_: argparse.Namespace) -> int:
    """Runs the offline synthetic tests. No network."""
    import subprocess
    return subprocess.call([sys.executable, "-m", "pytest", "research/tests", "-q"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research.cli")
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run")
    run.add_argument("--detector", required=True)
    run.add_argument("--symbols-file", required=True)
    run.add_argument("--cache-dir", default=None)
    run.add_argument("--start", required=True)
    run.add_argument("--end", required=True)
    run.add_argument("--max-bars", type=int, default=30)
    run.set_defaults(func=_run)

    st = sub.add_parser("self-test")
    st.set_defaults(func=_self_test)

    # Back-compat: allow flags without a sub-command (defaults to `run`).
    parser.add_argument("--self-test", action="store_true", help="Run pytest suite offline")
    parser.add_argument("--detector", dest="_detector_shim")
    args, rest = parser.parse_known_args(argv)

    if args.self_test:
        return _self_test(args)
    if args.cmd is None:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
