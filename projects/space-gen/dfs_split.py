#!/usr/bin/env python3
"""dfs_split — TVM AutoTVM SplitSpace 抽取版（邏輯與 TVM v0.9.0 一致，只做簡化＋註解）

原始碼出處：tvm/python/tvm/autotvm/task/space.py 的 SplitSpace
對應關係在每段註解標明 [TVM] 。

問題：長度 L 的迴圈軸，切成 n 段，有哪些切法？

TVM 的機制（本檔完全對齊）：
  1. 候選因子表 factors 從 L «算一次»（policy 決定內容），DFS 全程共用
  2. DFS 只填 n-1 個「內層槽」，每層自由選 — 中途不檢查整除
  3. 所有剪枝在«葉子»做：乘積 > L 丟掉；乘積整除 L 收下；
     若允許 tail（verbose/power2），乘積 < L 也收下（執行時生尾巴迴圈）
  4. 解的表示：[-1, f_{n-1}, ..., f_1] — 第一格 -1 = «最外層»，
     apply 時用 L / prod(其餘) 推導（有 tail 時是 ceil，產生邊界處理）

用法：
  $ python3 dfs_split.py 16 3                        # factors 政策（無 tail）
  $ python3 dfs_split.py 16 3 --policy power2        # 2的冪（可能有 tail）
  $ python3 dfs_split.py 16 3 --trace                # 看 DFS 展開樹
  $ python3 dfs_split.py 64 3 --max-inner 8          # constraint 範例
"""

import argparse
import math


# ── 候選因子表（[TVM] get_factors / get_pow2s） ─────────────────────────

def get_factors(n):
    """n 的因數（升冪）。16 → [1, 2, 4, 8, 16]"""
    return [i for i in range(1, n + 1) if n % i == 0]


def get_pow2s(n):
    """2 的冪 ≤ n。16 → [1, 2, 4, 8, 16]；12 → [1, 2, 4, 8]"""
    out, v = [], 1
    while v <= n:
        out.append(v)
        v <<= 1
    return out


def make_candidates(L, policy, max_factor=None):
    """[TVM] SplitSpace.__init__ 的 else 分支 — 候選表從 L 算«一次»。"""
    if policy == "factors":
        # 只取因數 → 保證無 tail
        factors = get_factors(L)
    elif policy == "power2":
        # 只取 2 的冪 → 可能有 tail
        factors = get_pow2s(L)
    elif policy == "verbose":
        # 因數 ∪ 2的冪 → 覆蓋最廣，可能有 tail
        factors = sorted(set(get_factors(L)) | set(get_pow2s(L)))
    else:
        raise ValueError(f"Invalid policy: {policy}")
    if max_factor is not None:
        factors = [x for x in factors if x <= max_factor]
    return factors


# ── DFS 生成（[TVM] SplitSpace._generate_space，逐行對齊） ──────────────

def split_space(L, n, policy="factors", max_factor=None,
                no_tail=None, constraint=None, trace=False):
    """枚舉「L 切成 n 段」的空間，回傳 TVM 表示法的解：[-1, f, f, ...]

    L          : 軸長度（TVM: self.product = axis.length）
    n          : 段數（TVM: num_outputs）
    policy     : factors / power2 / verbose（同 TVM）
    max_factor : 候選因子上限（同 TVM kwargs）
    no_tail    : 乘積必須整除 L 才收。預設 = (policy == "factors")，同 TVM
    constraint : callable(sizes) -> bool（TVM: kwargs["filter"]）
    trace      : 印出 DFS 展開樹（教學用，TVM 沒有）
    """
    factors = make_candidates(L, policy, max_factor)
    if no_tail is None:
        no_tail = (policy == "factors")     # [TVM] no_tail 預設值同款
    solutions = []

    def dfs(now, tmp_stack):
        indent = "    " * now
        if trace:
            print(f"{indent}dfs(now={now}, tmp_stack={tmp_stack})")

        # ── 葉子：n-1 個內層槽填滿了 ──（[TVM] if now == num_output-1）
        if now == n - 1:
            prod = math.prod(tmp_stack)
            if prod > L:                     # [TVM] 乘積超過軸長 → 剪
                if trace:
                    print(f"{indent}  ✗ prod={prod} > L")
                return
            # [TVM] 整除 → 收；允許 tail 時乘積 < L 也收
            if L % prod == 0 or (not no_tail and prod < L):
                sizes = [-1] + tmp_stack[::-1]   # [TVM] -1 = 最外層推導槽
                if constraint is None or constraint(sizes):
                    tag = "" if L % prod == 0 else "（tail）"
                    if trace:
                        print(f"{indent}  └→ 解 {sizes} ✓{tag}")
                    solutions.append(sizes)
                elif trace:
                    print(f"{indent}  ✗ constraint")
            elif trace:
                print(f"{indent}  ✗ prod={prod} 不整除且 no_tail")
            return

        # ── 展開：這個槽試每個候選因子 ──（[TVM] for factor in self.factors）
        # 注意：跟 TVM 一樣«自由枚舉、不檢查整除» — 剪枝全部留給葉子
        for f in factors:
            dfs(now + 1, tmp_stack + [f])

    dfs(now=0, tmp_stack=[])
    return solutions


def outer_size(sizes, L):
    """把 -1 槽解出來（apply 時的實際外層大小；tail 時為 ceil）。"""
    prod = math.prod(sizes[1:])
    return math.ceil(L / prod)


def _main():
    ap = argparse.ArgumentParser(description="TVM SplitSpace 抽取教學版")
    ap.add_argument("L", type=int, help="軸長度，例: 16")
    ap.add_argument("n", type=int, help="切成幾段，例: 3")
    ap.add_argument("--policy", default="factors",
                    choices=["factors", "power2", "verbose"])
    ap.add_argument("--max-factor", type=int, default=None)
    ap.add_argument("--max-inner", type=int, default=None,
                    help="constraint 範例: 最內層 ≤ 此值")
    ap.add_argument("--trace", action="store_true", help="印出 DFS 展開樹")
    args = ap.parse_args()

    constraint = None
    if args.max_inner is not None:
        # TVM 表示法 [-1, ..., inner]：最內層 = sizes[-1]
        constraint = lambda sizes: sizes[-1] <= args.max_inner

    sols = split_space(args.L, args.n, args.policy, args.max_factor,
                       constraint=constraint, trace=args.trace)
    print(f"\n# L={args.L} n={args.n} policy={args.policy} → {len(sols)} 解"
          f"（表示法 [-1, ...] = 外層推導，同 TVM SplitEntity）")
    for s in sols:
        tail = "" if args.L % math.prod(s[1:]) == 0 else "  ← tail"
        print(f"{s}  外層={outer_size(s, args.L)}{tail}")


if __name__ == "__main__":
    _main()
