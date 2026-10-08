from __future__ import annotations

from .schemas import Flags, Item

ITEM_MATH_TOL = 0.03


def validate_items(items: list[Item]) -> Flags:
    bad_math: list[int] = []
    for it in items:
        if it.qty is None or it.unit_price is None or it.total is None:
            continue
        expected = it.qty * it.unit_price - (it.discount or 0.0)
        if abs(expected - it.total) > ITEM_MATH_TOL:
            ln = it.line_no if it.line_no is not None else -1
            bad_math.append(ln)

    missing_lines: list[int] = []
    duplicate_lines: list[int] = []
    nums = [it.line_no for it in items if it.line_no is not None]

    if nums:
        nums_sorted = sorted(nums)
        if nums_sorted[0] >= 1:
            want = set(range(nums_sorted[0], nums_sorted[-1] + 1))
            missing_lines = sorted(want - set(nums_sorted))
        seen: dict[int, int] = {}
        for n in nums:
            seen[n] = seen.get(n, 0) + 1
        duplicate_lines = sorted(n for n, c in seen.items() if c > 1)

    return Flags(
        bad_math=bad_math,
        missing_lines=missing_lines,
        duplicate_lines=duplicate_lines,
    )
