#!/usr/bin/env python3
"""Verifiable delegated matmul — the maths behind pay-for-compute.

The whole point: checking someone else's matrix multiply is cheaper than doing
it. That asymmetry is what makes delegated compute trustless instead of
reputation-based.

  compute  C = A·B        O(n^3)
  verify   A·(B·r) == C·r  O(n^2)      <- Freivalds, one random vector r

A cheater passes one round with probability <= 1/2, so k rounds leaves at most
2^-k. Integer matrices throughout, so the check is exact — no float tolerance,
and an honest worker on different hardware can never be misjudged as cheating.

Run:  /usr/bin/python3 verifiable_matmul.py
"""

from __future__ import annotations

import time

import numpy as np

# Values stay small enough that n * v^2 cannot overflow int64.
VALUE_RANGE = 100
DTYPE = np.int64


# ── task ─────────────────────────────────────────────────────────────────────


def make_task(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    A = rng.integers(-VALUE_RANGE, VALUE_RANGE, size=(n, n), dtype=DTYPE)
    B = rng.integers(-VALUE_RANGE, VALUE_RANGE, size=(n, n), dtype=DTYPE)
    return A, B


# ── worker ───────────────────────────────────────────────────────────────────


def work_honest(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    return A @ B


def work_lazy(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Returns garbage instantly — the attack we must catch."""
    return np.zeros((A.shape[0], B.shape[1]), dtype=DTYPE)


def work_subtle(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Correct except for one entry. The hardest cheat to notice by eye."""
    C = A @ B
    C[0, 0] += 1
    return C


def work_truncated(A: np.ndarray, B: np.ndarray, frac: float = 0.5) -> np.ndarray:
    """Only bothers with part of the sum — a plausible way to skimp on work."""
    k = max(1, int(A.shape[1] * frac))
    return A[:, :k] @ B[:k, :]


# ── verifier ─────────────────────────────────────────────────────────────────


def freivalds_round(A, B, C, rng) -> bool:
    """One probabilistic check. Three matrix-vector products, no n^3 work."""
    r = rng.integers(0, 2, size=(A.shape[1], 1), dtype=DTYPE)
    return np.array_equal(A @ (B @ r), C @ r)


def verify(A, B, C, rounds: int, seed: int) -> tuple[bool, int]:
    """Returns (accepted, rounds_used). Stops at the first failed round."""
    rng = np.random.default_rng(seed)
    if C.shape != (A.shape[0], B.shape[1]):
        return False, 0
    for i in range(1, rounds + 1):
        if not freivalds_round(A, B, C, rng):
            return False, i
    return True, rounds


# ── splitting (how the job is handed to many workers) ────────────────────────


def split_rows(A: np.ndarray, workers: int) -> list[tuple[int, np.ndarray]]:
    """Row-block split: worker i gets A[rows_i, :] and all of B.

    The simplest useful decomposition — each worker's output block is
    independently verifiable, so one cheat does not poison the whole job.
    (SUMMA-style 2D splits cut communication further; same verification story.)
    """
    bounds = np.linspace(0, A.shape[0], workers + 1, dtype=int)
    return [(bounds[i], A[bounds[i]:bounds[i + 1], :]) for i in range(workers)]


# ── demo ─────────────────────────────────────────────────────────────────────


def bench(n: int) -> None:
    A, B = make_task(n, seed=1)

    t0 = time.perf_counter()
    C = work_honest(A, B)
    t_compute = time.perf_counter() - t0

    t0 = time.perf_counter()
    ok, used = verify(A, B, C, rounds=8, seed=99)
    t_verify = time.perf_counter() - t0

    print(f"n={n:>5}  compute {t_compute*1000:8.1f} ms   "
          f"verify(8 rounds) {t_verify*1000:7.2f} ms   "
          f"ratio {t_compute/max(t_verify,1e-9):6.1f}x   accepted={ok}")


def main() -> None:
    print("=" * 74)
    print("1. Verification is cheaper than computation (that's the whole trick)")
    print("=" * 74)
    for n in (256, 512, 1024):
        bench(n)

    print()
    print("=" * 74)
    print("2. Catching cheats — n=512, 8 rounds")
    print("=" * 74)
    A, B = make_task(512, seed=2)
    attacks = {
        "honest": work_honest(A, B),
        "lazy (all zeros)": work_lazy(A, B),
        "subtle (one entry off by 1)": work_subtle(A, B),
        "truncated (half the sum)": work_truncated(A, B),
        "wrong shape": np.zeros((512, 511), dtype=DTYPE),
    }
    for name, C in attacks.items():
        ok, used = verify(A, B, C, rounds=8, seed=7)
        verdict = "✅ PAY" if ok else f"❌ REJECT (caught in round {used})"
        print(f"  {name:<30} {verdict}")

    print()
    print("=" * 74)
    print("3. Single-round catch rate over 200 trials (theory says >= 50%)")
    print("=" * 74)
    A, B = make_task(128, seed=3)
    C_bad = work_subtle(A, B)   # hardest case: one entry wrong
    caught = sum(
        0 if freivalds_round(A, B, C_bad, np.random.default_rng(s)) else 1
        for s in range(200)
    )
    print(f"  one-entry-wrong caught in {caught}/200 single rounds "
          f"({caught/2:.0f}%)")
    print(f"  → k rounds leaves at most 2^-k: "
          f"8 rounds = 1/256, 20 rounds = 1 in a million")

    print()
    print("=" * 74)
    print("4. Splitting across workers — each block verified independently")
    print("=" * 74)
    A, B = make_task(512, seed=4)
    blocks = split_rows(A, workers=4)
    print(f"  512x512 job -> 4 workers, each gets A[{blocks[0][1].shape[0]} rows] + all of B")
    cheater = 2
    total_paid = 0
    for i, (row0, A_i) in enumerate(blocks):
        C_i = work_lazy(A_i, B) if i == cheater else work_honest(A_i, B)
        ok, used = verify(A_i, B, C_i, rounds=8, seed=11)
        if ok:
            total_paid += 1
            print(f"  worker {i}: rows {row0:>3}-{row0+A_i.shape[0]-1:>3}  ✅ verified → pay")
        else:
            print(f"  worker {i}: rows {row0:>3}-{row0+A_i.shape[0]-1:>3}  "
                  f"❌ failed round {used} → no pay, slash stake, reassign")
    print(f"  paid {total_paid}/4 workers; the bad block is re-dispatched, "
          f"the good work is kept")


if __name__ == "__main__":
    main()
