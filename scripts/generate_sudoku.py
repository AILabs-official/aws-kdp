#!/usr/bin/env python3
"""Generate Sudoku puzzles for a KDP book.

Pure-Python backtracking generator + solver. No external dependencies.
Every puzzle is verified to have EXACTLY ONE solution (the #1 review
complaint on sudoku books is "multiple solutions / broken grids" —
this guarantees we never ship those).

Difficulty is controlled via target clue count per level. For v1 this
is a clue-count proxy; a logical-technique rater can be added later
without breaking the output format.

Output:
  output/{theme_key}/sudoku_puzzles.json
    [{id, difficulty, puzzle: 9x9 (0=empty), solution: 9x9}, ...]

Usage:
  python3 scripts/generate_sudoku.py \\
    --theme commuter_sudoku_15min \\
    --difficulty medium:120,hard:96,expert:24

  python3 scripts/generate_sudoku.py \\
    --theme senior_sudoku_jumbo \\
    --difficulty easy:100,medium:100,hard:100 \\
    --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402


class SudokuGenerator:
    """Backtracking generator with unique-solution guarantee.

    Supports two grid sizes:
      • 9×9 (box 3×3, digits 1–9) — standard tiers: easy / medium / hard / expert
      • 6×6 (box 2×3, digits 1–6) — warm-up tier ("warmup")
    """

    # Per-difficulty (min_clues, max_clues). The "warmup" tier targets a 6×6
    # grid (36 cells); all other tiers target a 9×9 grid (81 cells).
    DIFFICULTY_CLUES = {
        "warmup": (22, 26),  # 6×6 — gentle introduction (most cells filled)
        "easy":   (38, 45),
        "medium": (30, 36),
        "hard":   (26, 29),
        "expert": (22, 25),
    }

    # Grid size + box dimensions per tier.
    TIER_GRID = {
        "warmup": {"size": 6, "box_rows": 2, "box_cols": 3},
        "easy":   {"size": 9, "box_rows": 3, "box_cols": 3},
        "medium": {"size": 9, "box_rows": 3, "box_cols": 3},
        "hard":   {"size": 9, "box_rows": 3, "box_cols": 3},
        "expert": {"size": 9, "box_rows": 3, "box_cols": 3},
    }

    def __init__(self, seed: int | None = None, size: int = 9, box_rows: int = 3, box_cols: int = 3):
        self.rng = random.Random(seed)
        self.size = size
        self.box_rows = box_rows
        self.box_cols = box_cols
        # size must equal box_rows × box_cols (e.g. 9 = 3×3, 6 = 2×3)
        assert size == box_rows * box_cols, (
            f"size {size} must equal box_rows ({box_rows}) × box_cols ({box_cols})"
        )

    # ---- Full grid generation ----

    def generate_complete_grid(self) -> list[list[int]]:
        grid = [[0] * self.size for _ in range(self.size)]
        self._fill(grid)
        return grid

    def _fill(self, grid: list[list[int]]) -> bool:
        cell = self._find_empty(grid)
        if cell is None:
            return True
        r, c = cell
        nums = list(range(1, self.size + 1))
        self.rng.shuffle(nums)
        for n in nums:
            if self._is_valid(grid, r, c, n):
                grid[r][c] = n
                if self._fill(grid):
                    return True
                grid[r][c] = 0
        return False

    def _find_empty(self, grid: list[list[int]]) -> tuple[int, int] | None:
        for r in range(self.size):
            for c in range(self.size):
                if grid[r][c] == 0:
                    return (r, c)
        return None

    def _is_valid(self, grid: list[list[int]], r: int, c: int, n: int) -> bool:
        for i in range(self.size):
            if grid[r][i] == n or grid[i][c] == n:
                return False
        br = (r // self.box_rows) * self.box_rows
        bc = (c // self.box_cols) * self.box_cols
        for i in range(br, br + self.box_rows):
            for j in range(bc, bc + self.box_cols):
                if grid[i][j] == n:
                    return False
        return True

    # ---- Solution counting (for uniqueness check) ----

    def count_solutions(self, grid: list[list[int]], limit: int = 2) -> int:
        """Count solutions up to `limit`. limit=2 is enough for uniqueness check."""
        state = [0]
        grid_copy = [row[:] for row in grid]
        self._count_helper(grid_copy, state, limit)
        return state[0]

    def _count_helper(self, grid: list[list[int]], state: list[int], limit: int) -> None:
        if state[0] >= limit:
            return
        cell = self._find_empty(grid)
        if cell is None:
            state[0] += 1
            return
        r, c = cell
        for n in range(1, self.size + 1):
            if self._is_valid(grid, r, c, n):
                grid[r][c] = n
                self._count_helper(grid, state, limit)
                grid[r][c] = 0
                if state[0] >= limit:
                    return

    # ---- Puzzle creation (remove clues with uniqueness guard) ----

    def make_puzzle(
        self, difficulty: str, max_attempts: int = 3
    ) -> tuple[list[list[int]], list[list[int]], int]:
        """Return (puzzle, solution, clue_count). Retries up to `max_attempts`
        times if the target clue count is unreachable due to uniqueness floor."""
        min_clues, max_clues = self.DIFFICULTY_CLUES[difficulty]
        n_cells = self.size * self.size

        for _ in range(max_attempts):
            solution = self.generate_complete_grid()
            puzzle = [row[:] for row in solution]

            cells = [(r, c) for r in range(self.size) for c in range(self.size)]
            self.rng.shuffle(cells)

            target_clues = self.rng.randint(min_clues, max_clues)
            clues_left = n_cells

            for r, c in cells:
                if clues_left <= target_clues:
                    break
                saved = puzzle[r][c]
                puzzle[r][c] = 0
                if self.count_solutions(puzzle) != 1:
                    puzzle[r][c] = saved
                else:
                    clues_left -= 1

            if clues_left <= max_clues:
                return puzzle, solution, clues_left

        # Fallback: return whatever we got (still unique)
        return puzzle, solution, clues_left


def batch_mixed(counts: dict[str, int], seed: int | None = None) -> list[dict]:
    """Run a batch across mixed grid sizes. Per-tier generators are instantiated
    so the 6×6 warm-up and 9×9 standard tiers each get their own correct
    box geometry. Seeds are derived deterministically from the master seed."""
    puzzles: list[dict] = []
    pid = 1
    t0 = time.time()

    # Order: warmup first (gentle introduction), then standard tiers.
    for difficulty in ("warmup", "easy", "medium", "hard", "expert"):
        n = counts.get(difficulty, 0)
        if n <= 0:
            continue
        tier = SudokuGenerator.TIER_GRID[difficulty]
        # Derive a per-tier seed so each tier is independent but reproducible.
        sub_seed = None if seed is None else seed + hash(difficulty) % 10_000
        gen = SudokuGenerator(
            seed=sub_seed,
            size=tier["size"],
            box_rows=tier["box_rows"],
            box_cols=tier["box_cols"],
        )
        print(f"\n  {difficulty.upper()} × {n}  ({tier['size']}×{tier['size']})")
        for _ in range(n):
            ts = time.time()
            puzzle, solution, clues = gen.make_puzzle(difficulty)
            dt = time.time() - ts
            puzzles.append({
                "id": pid,
                "difficulty": difficulty,
                "grid_size": tier["size"],
                "clue_count": clues,
                "puzzle": puzzle,
                "solution": solution,
            })
            print(f"    #{pid:03d}  clues={clues:2d}  ({dt:.1f}s)")
            pid += 1
    elapsed = time.time() - t0
    if puzzles:
        print(f"\n⏱  Total: {elapsed:.1f}s ({elapsed/len(puzzles):.2f}s/puzzle)")
    return puzzles


# ---- CLI ----

def parse_difficulty_spec(spec: str) -> dict[str, int]:
    """'easy:50,medium:100' → {'easy': 50, 'medium': 100}"""
    out: dict[str, int] = {}
    for part in spec.split(","):
        k, _, v = part.strip().partition(":")
        if not k or not v:
            raise ValueError(f"bad difficulty spec part: {part!r}")
        k = k.strip().lower()
        if k not in SudokuGenerator.DIFFICULTY_CLUES:
            raise ValueError(
                f"unknown difficulty {k!r}. valid: "
                f"{list(SudokuGenerator.DIFFICULTY_CLUES)}"
            )
        out[k] = int(v.strip())
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--theme", required=True, help="theme_key (folder under output/)")
    parser.add_argument(
        "--difficulty", required=True,
        help="spec like 'warmup:20,easy:50,medium:100,hard:80,expert:20'",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (reproducible)")
    args = parser.parse_args()

    counts = parse_difficulty_spec(args.difficulty)
    total = sum(counts.values())

    theme_dir = Path(config.get_book_dir(args.theme))
    theme_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {total} sudoku puzzles for '{args.theme}':")
    for d, n in counts.items():
        tier = SudokuGenerator.TIER_GRID[d]
        print(f"  {d}: {n}  ({tier['size']}×{tier['size']})")

    puzzles = batch_mixed(counts, seed=args.seed)

    out_path = theme_dir / "sudoku_puzzles.json"
    out_path.write_text(json.dumps(puzzles, indent=2))

    by_diff = {d: sum(1 for p in puzzles if p["difficulty"] == d) for d in counts}
    print(f"\n✅ Wrote {len(puzzles)} puzzles to {out_path}")
    print(f"   {by_diff}")


if __name__ == "__main__":
    main()
