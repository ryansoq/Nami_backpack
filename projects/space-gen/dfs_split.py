#!/usr/bin/env python3
"""dfs_split — TVM SplitSpace 的極簡教學版（DFS 逐一展開）

問題：長度 L 的迴圈軸，切成 n 段，有哪些切法？
      每個解 = [f1, f2, ..., fn]，且 f1 × f2 × ... × fn = L

TVM 的做法（autotvm/task/space.py SplitSpace）本質就是一個 DFS：
  - 每一層選一個因子 f
  - 剩餘長度變成 remaining // f
  - 走到最後一層，剩多少就是最後一段（保證乘積 = L）
  - 不整除的分支直接剪掉

本檔就是把那個 DFS 拆到只剩骨架，加上：
  - constraint：任何 callable，不滿足就丟（例：內層 ≤ 向量寬度）
  - trace：印出整棵展開樹，看 DFS 怎麼走

用法：
  $ python3 dfs_split.py 16 3              # L=16 切 3 段
  $ python3 dfs_split.py 16 3 --trace      # 看展開過程
  $ python3 dfs_split.py 64 3 --max-inner 8
"""

import argparse


def factors_of(n):
    """n 的因數（升冪）。16 → [1, 2, 4, 8, 16]"""
    return [i for i in range(1, n + 1) if n % i == 0]


def split_space(L, n, constraint=None, trace=False):
    """DFS 展開「L 切成 n 段」的所有切法。

    L          : 軸長度（例：迴圈 trip count 16）
    n          : 要切成幾段（例：3 → outer / middle / inner）
    constraint : callable(sizes) -> bool，False 就丟掉這個解
    trace      : True 時印出展開樹

    回傳：所有 [f1, ..., fn]，乘積必為 L
    """
    solutions = []

    def dfs(depth, remaining, path):
        indent = "    " * depth
        if trace:
            print(f"{indent}dfs(depth={depth}, remaining={remaining}, path={path})")

        # ── 終止條件：最後一段直接吃掉剩下的 ──
        if depth == n - 1:
            sizes = path + [remaining]
            ok = constraint is None or constraint(sizes)
            if trace:
                print(f"{indent}  └→ 解 {sizes} {'✓' if ok else '✗ (constraint)'}")
            if ok:
                solutions.append(sizes)
            return

        # ── 展開：這一層試每個因子 ──
        for f in factors_of(remaining):     # 只有整除的 f 會出現 = 天然剪枝
            dfs(depth + 1, remaining // f, path + [f])

    dfs(depth=0, remaining=L, path=[])
    return solutions


def _main():
    ap = argparse.ArgumentParser(description="TVM SplitSpace 教學版 DFS")
    ap.add_argument("L", type=int, help="軸長度，例: 16")
    ap.add_argument("n", type=int, help="切成幾段，例: 3")
    ap.add_argument("--max-inner", type=int, default=None,
                    help="constraint 範例: 最內層 ≤ 此值（向量暫存器寬度）")
    ap.add_argument("--trace", action="store_true", help="印出 DFS 展開樹")
    args = ap.parse_args()

    constraint = None
    if args.max_inner is not None:
        constraint = lambda sizes: sizes[-1] <= args.max_inner

    sols = split_space(args.L, args.n, constraint, args.trace)
    print(f"\n# L={args.L} 切 {args.n} 段"
          f"{f'，內層≤{args.max_inner}' if args.max_inner else ''}"
          f" → {len(sols)} 種切法")
    for s in sols:
        print(s)


if __name__ == "__main__":
    _main()
