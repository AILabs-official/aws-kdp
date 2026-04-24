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
    """Backtracking generator with unique-solution guarantee."""

    DIFFICULTY_CLUES = {
        "easy":   (38, 45),
        "medium": (30, 36),
        "hard":   (26, 29),
        "expert": (22, 25),
    }

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    # ---- Full grid generation ----

    def generate_complete_grid(self) -> list[list[int]]:
        grid = [[0] * 9 for _ in range(9)]
        self._fill(grid)
        return grid

    def _fill(self, grid: list[list[int]]) -> bool:
        cell = self._find_empty(grid)
        if cell is None:
            return True
        r, c = cell
        nums = list(range(1, 10))
        self.rng.shuffle(nums)
        for n in nums:
            if self._is_valid(grid, r, c, n):
                grid[r][c] = n
                if self._fill(grid):
                    return True
                grid[r][c] = 0
        return False

    @staticmethod
    def _find_empty(grid: list[list[int]]) -> tuple[int, int] | None:
        for r in range(9):
            for c in range(9):
                if grid[r][c] == 0:
                    return (r, c)
        return None

    @staticmethod
    def _is_valid(grid: list[list[int]], r: int, c: int, n: int) -> bool:
        for i in range(9):
            if grid[r][i] == n or grid[i][c] == n:
                return False
        br, bc = (r // 3) * 3, (c // 3) * 3
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
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
        for n in range(1, 10):
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

        for _ in range(max_attempts):
            solution = self.generate_complete_grid()
            puzzle = [row[:] for row in solution]

            cells = [(r, c) for r in range(9) for c in range(9)]
            self.rng.shuffle(cells)

            target_clues = self.rng.randint(min_clues, max_clues)
            clues_left = 81

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

    # ---- Batch ----

    def batch(self, counts: dict[str, int]) -> list[dict]:
        puzzles: list[dict] = []
        pid = 1
        t0 = time.time()
        for difficulty in ("easy", "medium", "hard", "expert"):
            n = counts.get(difficulty, 0)
            if n <= 0:
                continue
            print(f"\n  {difficulty.upper()} × {n}")
            for _ in range(n):
                ts = time.time()
                puzzle, solution, clues = self.make_puzzle(difficulty)
                dt = time.time() - ts
                puzzles.append({
                    "id": pid,
                    "difficulty": difficulty,
                    "clue_count": clues,
                    "puzzle": puzzle,
                    "solution": solution,
                })
                print(f"    #{pid:03d}  clues={clues:2d}  ({dt:.1f}s)")
                pid += 1
        elapsed = time.time() - t0
        print(f"\n⏱  Total: {elapsed:.1f}s ({elapsed/len(puzzles):.1f}s/puzzle)")
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
        help="spec like 'easy:50,medium:100,hard:80,expert:20'",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (reproducible)")
    args = parser.parse_args()

    counts = parse_difficulty_spec(args.difficulty)
    total = sum(counts.values())

    theme_dir = Path(config.get_book_dir(args.theme))
    theme_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {total} sudoku puzzles for '{args.theme}':")
    for d, n in counts.items():
        print(f"  {d}: {n}")

    gen = SudokuGenerator(seed=args.seed)
    puzzles = gen.batch(counts)

    out_path = theme_dir / "sudoku_puzzles.json"
    out_path.write_text(json.dumps(puzzles, indent=2))

    by_diff = {d: sum(1 for p in puzzles if p["difficulty"] == d) for d in counts}
    print(f"\n✅ Wrote {len(puzzles)} puzzles to {out_path}")
    print(f"   {by_diff}")


if __name__ == "__main__":
    main()
