"""Common types for detectors. A Detector produces Occurrences; an Occurrence
carries all information needed for the resolver and the cell predicates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class Occurrence:
    """One frozen setup event.

    - `t0`: index in the symbol's dataframe at which the setup triggers.
    - `entry` / `stop` / `target`: preregistered per detector; never rewritten.
    - `side`: 'long' or 'short'.
    - `features`: locked feature dict from `features.freeze_at(df, t0)`, plus
      any detector-specific frozen fields (e.g. `broke_pivot: float`).
    - `entry_bar_offset`: how many bars AFTER t0 the entry happens (usually 1
      for next-bar-open detectors, 0 for close-based). Used by runner to
      correctly slice `bars_fwd` for the resolver.
    """
    symbol: str
    t0: pd.Timestamp
    entry: float
    stop: float
    target: float
    side: str
    features: dict = field(default_factory=dict)
    entry_bar_offset: int = 1


class Detector(Protocol):
    name: str

    def scan(self, symbol: str, df: pd.DataFrame) -> list[Occurrence]:
        """Return all occurrences of this setup in `df`. Called ONCE per symbol.

        Implementations MUST NOT read df beyond the index of each candidate
        bar for feature freezing. The forward walk is applied separately by
        the runner.
        """
        ...
