"""Cell design tests: v0.2 requires orthogonal modifiers, not just a cascade."""

from __future__ import annotations

import pandas as pd

from research.cells import BIDC_CELLS


def test_bidc_has_a_base_and_orthogonal_group():
    names = [c.name for c in BIDC_CELLS]
    # Group A base exists
    assert "A1_generic_inside_day" in names
    # Group B orthogonal modifiers all parent to the base
    orth = [c for c in BIDC_CELLS if c.name.startswith("B")]
    assert len(orth) >= 10, f"expected ≥ 10 orthogonal cells, got {len(orth)}"
    for c in orth:
        assert c.parent == "A1_generic_inside_day", (
            f"orthogonal cell {c.name} must parent to A1_generic_inside_day, got {c.parent}"
        )


def test_bidc_has_cascade_group_but_it_is_not_the_only_test_path():
    cascade = [c for c in BIDC_CELLS if c.name.startswith("C")]
    orth = [c for c in BIDC_CELLS if c.name.startswith("B")]
    assert len(cascade) >= 3
    # Orthogonal count must dominate — cascade is retained but not primary
    assert len(orth) > len(cascade)


def test_orthogonal_cells_cover_every_key_modifier():
    """Every listed modifier must have its own orthogonal cell so lift is
    measurable individually rather than only inside a chain."""
    required_axes = {
        "ema_stack_up", "compression", "fresh_macd_reaccel",
        "room_to_next_level", "level_type", "breakout_age",
        "after_breakout", "holding_above", "gap_clean",
    }
    orth_names = " ".join(c.name for c in BIDC_CELLS if c.name.startswith("B"))
    missing = [k for k in required_axes if k not in orth_names]
    # some names use slight variations — this is a broad substring check
    assert not missing, (
        f"orthogonal group missing single-modifier cells for: {missing}. "
        f"Cells present: {orth_names}"
    )


def test_no_orthogonal_modifier_requires_a_prior_modifier():
    """Orthogonal cells must be plain (base AND single modifier). Chained
    orthogonal cells are the cascade group's job."""
    single_mod_prefixes = ("B1_", "B2_", "B3_", "B4_", "B5_", "B6_",
                            "B7_", "B8_", "B9_", "B10_", "B11_", "B12_", "B13_")
    for c in BIDC_CELLS:
        if not any(c.name.startswith(p) for p in single_mod_prefixes):
            continue
        assert c.parent == "A1_generic_inside_day", (
            f"{c.name}: orthogonal cell must parent to base only, got parent={c.parent}"
        )


def _features(base=True, **kw):
    d = {"inside_day": base}
    d.update(kw)
    return d


def test_orthogonal_predicate_independence_examples():
    """Sanity: an orthogonal predicate that adds compression should fire on a
    bar that has inside_day + compression regardless of breakout status."""
    by_name = {c.name: c for c in BIDC_CELLS}
    b4 = by_name["B4_compression"]
    assert b4.predicate(_features(compression=True))
    # No breakout, no MACD, no EMA stack — still fires:
    assert b4.predicate(_features(compression=True, was_breakout_at_tm1=False,
                                   ema_stack_up=False, fresh_macd_reaccel_up=False))
    # Without compression, does not fire:
    assert not b4.predicate(_features(compression=False))
