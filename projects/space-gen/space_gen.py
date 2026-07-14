#!/usr/bin/env python3
"""space_gen — 迷你調優空間生成器（從 AutoTVM SplitSpace 概念抽出的獨立小工具）

給每個維度一個上限（例如 tile 上限 [16, 32]），生成所有候選組合：

    >>> from space_gen import gen_space
    >>> gen_space([16, 32], policy="pow2")           # doctest: +ELLIPSIS
    [(1, 1), (1, 2), ..., (16, 32)]

政策（對應 AutoTVM 的 policy）：
    pow2    : 每維取 2 的冪 {1,2,4,...,bound}            ← 對齊/向量化友善
    factors : 每維取 bound 的因數                        ← 保證整除、無 tail
    verbose : 兩者聯集（AutoTVM 的 verbose）              ← 覆蓋最廣
    linear  : 1..bound 全部                              ← 小空間暴力用

剪枝：
    filter_fn  : callable(cfg_tuple) -> bool，客製約束（例：內積 ≤ cache）
    max_product: 快捷剪枝 — 保留 prod(cfg) ≤ max_product 的組合

GA / LLM tuner 需要的索引編碼（對應 ConfigSpace.get(i)）：
    space = Space([16, 32], policy="pow2")
    len(space)        → 空間大小
    space[7]          → 第 7 個組合（確定性、可重現）
    space.index(cfg)  → 組合的索引
"""

import argparse
import itertools
import math


def pow2s_upto(n):
    """2 的冪 ≤ n，含 1。 pow2s_upto(16) → [1, 2, 4, 8, 16]"""
    out, v = [], 1
    while v <= n:
        out.append(v)
        v <<= 1
    return out


def factors_of(n):
    """n 的所有因數（升冪）。 factors_of(12) → [1, 2, 3, 4, 6, 12]"""
    out = set()
    for i in range(1, int(math.isqrt(n)) + 1):
        if n % i == 0:
            out.add(i)
            out.add(n // i)
    return sorted(out)


_POLICIES = {
    "pow2": pow2s_upto,
    "factors": factors_of,
    "verbose": lambda n: sorted(set(pow2s_upto(n)) | set(factors_of(n))),
    "linear": lambda n: list(range(1, n + 1)),
}


def axis_candidates(bound, policy="pow2"):
    """單一維度的候選值。"""
    try:
        return _POLICIES[policy](bound)
    except KeyError:
        raise ValueError(
            f"unknown policy {policy!r}; pick from {sorted(_POLICIES)}")


class Space:
    """惰性索引空間：不物化整個笛卡兒積也能 len / 取第 i 個 / 反查索引。

    有 filter/max_product 時退化為物化清單（過濾後無法用純算術索引）。
    """

    def __init__(self, bounds, policy="pow2", filter_fn=None, max_product=None):
        self.bounds = list(bounds)
        self.policy = policy
        self.axes = [axis_candidates(b, policy) for b in self.bounds]
        if filter_fn is None and max_product is not None:
            filter_fn = lambda cfg: math.prod(cfg) <= max_product
        self._materialized = None
        if filter_fn is not None:
            self._materialized = [
                cfg for cfg in itertools.product(*self.axes) if filter_fn(cfg)]

    def __len__(self):
        if self._materialized is not None:
            return len(self._materialized)
        return math.prod(len(a) for a in self.axes)

    def __getitem__(self, i):
        if not 0 <= i < len(self):
            raise IndexError(f"index {i} out of range for space of {len(self)}")
        if self._materialized is not None:
            return self._materialized[i]
        # 混基數展開（mixed-radix）：最後一維變動最快 — 與 itertools.product 同序
        cfg = []
        for axis in reversed(self.axes):
            i, r = divmod(i, len(axis))
            cfg.append(axis[r])
        return tuple(reversed(cfg))

    def index(self, cfg):
        cfg = tuple(cfg)
        if self._materialized is not None:
            return self._materialized.index(cfg)
        idx = 0
        for axis, v in zip(self.axes, cfg):
            idx = idx * len(axis) + axis.index(v)
        return idx

    def __iter__(self):
        if self._materialized is not None:
            return iter(self._materialized)
        return itertools.product(*self.axes)


def gen_space(bounds, policy="pow2", filter_fn=None, max_product=None):
    """一行版：直接回傳組合清單。"""
    return list(Space(bounds, policy, filter_fn, max_product))


def _main():
    ap = argparse.ArgumentParser(description="tuning-space generator")
    ap.add_argument("bounds", nargs="+", type=int, help="每維上限，例: 16 32")
    ap.add_argument("--policy", default="pow2", choices=sorted(_POLICIES))
    ap.add_argument("--max-product", type=int, default=None,
                    help="剪枝: 只留 prod(cfg) <= 此值")
    ap.add_argument("--count", action="store_true", help="只印空間大小")
    args = ap.parse_args()

    space = Space(args.bounds, args.policy, max_product=args.max_product)
    print(f"# bounds={args.bounds} policy={args.policy} "
          f"max_product={args.max_product} → {len(space)} configs")
    if not args.count:
        for cfg in space:
            print(list(cfg))


if __name__ == "__main__":
    _main()
