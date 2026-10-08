from __future__ import annotations

from rapidfuzz import fuzz

from .schemas import Item

VOTE_TOL = 0.02
MATH_TOL = 0.03
NAME_SIM = 65.0


def _item_math_ok(it: Item) -> bool:
    if it.qty is None or it.unit_price is None or it.total is None:
        return False
    return abs(it.qty * it.unit_price - (it.discount or 0.0) - it.total) <= MATH_TOL


def _vote(
    values: list[float | None],
    weights: list[float] | None = None,
    tol: float = VOTE_TOL,
) -> tuple[float | None, float]:
    if not values:
        return None, 0.0
    weights = weights or [1.0] * len(values)
    scores = []
    for v, w in zip(values, weights):
        if v is None:
            continue
        total_w = sum(
            w2
            for u, w2 in zip(values, weights)
            if u is not None and abs(u - v) <= tol
        )
        scores.append((total_w, v))
    if not scores:
        return None, 0.0
    scores.sort(key=lambda t: -t[0])
    return scores[0][1], scores[0][0]


def merge_line_group(
    items: list[Item], weights: list[float] | None = None
) -> tuple[Item, bool]:
    weights = weights or [1.0] * len(items)
    total, w_total = _vote([it.total for it in items], weights)
    qty, _ = _vote([it.qty for it in items], weights)
    up, _ = _vote([it.unit_price for it in items], weights)

    disc_items: list[float | None] = []
    disc_weights: list[float] = []
    for it, w in zip(items, weights):
        if it.discount is None or (
            it.total is not None and 0 < it.discount <= it.total
        ):
            disc_items.append(it.discount)
            disc_weights.append(w)
    disc, _ = _vote(disc_items, disc_weights)

    printed, _ = _vote(
        [it.printed_total for it in items if it.printed_total is not None],
        weights,
    )

    # Tie-break on total. The printed line total is the authoritative charged
    # amount, so a candidate that is BOTH printed-backed and math-consistent
    # outranks a bare vote winner. The vote is overridden only when no
    # ok candidate agrees with it — an ok candidate that matches the vote
    # just confirms it (no change).
    if total is not None:
        cand = [
            (it.printed_total is not None and _item_math_ok(it), w, i)
            for i, (it, w) in enumerate(zip(items, weights))
            if it.total is not None
        ]
        ok_cand = [c for c in cand if c[0]]
        bad_cand = [c for c in cand if not c[0]]
        if ok_cand and bad_cand:
            agrees = any(
                items[c[2]].total is not None
                and abs(items[c[2]].total - total) <= VOTE_TOL
                for c in ok_cand
            )
            if not agrees:
                best = max(ok_cand, key=lambda c: c[1])
                total = items[best[2]].total

    top_w = max(weights) if weights else 1.0
    top_items = [
        it for it, w in zip(items, weights) if w >= top_w - 1e-9
    ] or list(items)
    ref = next((it.name or "" for it in top_items), "")
    sim_items = [
        it
        for it in top_items
        if fuzz.partial_ratio(ref.upper(), (it.name or "").upper()) >= NAME_SIM
    ]
    name = (
        min(sim_items, key=lambda it: len(it.name or ""), default=top_items[0])
        .name
        or ref
    )

    n_readings = len(items)
    contested = (
        n_readings > 1
        and w_total < sum(weights)
        and total is not None
        and any(
            it.total is not None and abs(it.total - total) > VOTE_TOL
            for it in items
        )
    )

    line_no = next((it.line_no for it in items if it.line_no is not None), None)
    unit = next((it.unit for it in items if it.unit), None)

    merged = Item(
        line_no=line_no,
        name=name,
        qty=qty,
        unit=unit,
        unit_price=up,
        discount=disc,
        total=total,
        printed_total=printed,
        contested=contested,
    )
    return merged, contested


def group_by_line(
    items: list[Item], weights: list[float]
) -> tuple[dict[int, list[Item]], dict[int, list[float]]]:
    groups: dict[int, list[Item]] = {}
    gweights: dict[int, list[float]] = {}
    strays: list[tuple[Item, float]] = []
    for it, w in zip(items, weights):
        n = it.line_no
        if n is not None:
            groups.setdefault(n, []).append(it)
            gweights.setdefault(n, []).append(w)
        else:
            strays.append((it, w))
    for it, w in strays:
        for key, g in groups.items():
            if (
                fuzz.partial_ratio(
                    (it.name or "").upper(), (g[0].name or "").upper()
                )
                >= 80
            ):
                g.append(it)
                gweights[key].append(w)
                break
    return groups, gweights


def consensus_merge(
    readings: list[list[Item]], weights: list[float] | None = None
) -> tuple[list[Item], list[int]]:
    if weights is None:
        weights = [1.0] * len(readings)
    if len(weights) != len(readings):
        raise ValueError(
            f"weights ({len(weights)}) must match readings ({len(readings)})"
        )
    flat = [it for r in readings for it in r]
    flat_w = [w for r, w in zip(readings, weights) for _ in r]
    groups, gweights = group_by_line(flat, flat_w)
    merged: list[Item] = []
    contested: list[int] = []
    for key in sorted(groups):
        m, is_contested = merge_line_group(groups[key], gweights[key])
        merged.append(m)
        if is_contested:
            n = m.line_no
            contested.append(n if n is not None else -1)
    return merged, contested
