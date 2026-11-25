"""Apriori: frequent itemsets + association rules (support, confidence, lift)."""
from collections import Counter
from itertools import combinations

import pandas as pd

LEVELS = {
    "Produk (ukuran digabung)": "base_product",
    "Produk + varian ukuran": "product_name",
    "Kategori": "category_name",
}
TOPPING_CATEGORIES = {"Topping & Tambahan", "Topping"}


def build_baskets(df: pd.DataFrame, level: str, exclude_non_menu: bool = True, drop_topping_only: bool = True):
    """Satu order_key = satu keranjang berisi item unik pada level yang dipilih.

    Filter (tahun, kanal, tipe order) harus diterapkan pada `df` SEBELUM fungsi ini, karena filter itu
    memilih transaksi; isi keranjang tidak dipotong sebagian."""
    col = LEVELS[level]
    data = df
    if exclude_non_menu and "is_menu_item" in data:
        data = data[data.is_menu_item.astype(int) == 1]
    if drop_topping_only:
        main = data[~data.category_name.isin(TOPPING_CATEGORIES)].order_key.unique()
        data = data[data.order_key.isin(main)]
    baskets = data.groupby("order_key")[col].agg(lambda s: frozenset(s.astype(str)))
    return list(baskets.values)


def mine_rules(baskets, min_support=0.05, min_confidence=0.5, min_lift=1.0, max_size=3, limit=300):
    n = len(baskets)
    if not n:
        return {"orders": 0, "itemsets": [], "rules": [], "total_itemsets": 0, "total_rules": 0}
    single = Counter(i for b in baskets for i in b)
    counts = {frozenset([i]): c for i, c in single.items() if c / n >= min_support}
    all_counts = dict(counts)
    previous = set(counts)
    for size in range(2, max_size + 1):
        candidates = set()
        prev = sorted(previous, key=lambda x: tuple(sorted(x)))
        for a, b in combinations(prev, 2):
            combo = a | b
            if len(combo) == size and all(frozenset(sub) in previous for sub in combinations(combo, size - 1)):
                candidates.add(combo)
        if not candidates:
            break
        current = Counter()
        for b in baskets:
            if len(b) < size:
                continue
            for cand in candidates:
                if cand <= b:
                    current[cand] += 1
        current = {k: v for k, v in current.items() if v / n >= min_support}
        all_counts.update(current)
        previous = set(current)
        if not previous:
            break
    itemsets = [{"items": sorted(k), "size": len(k), "count": v, "support": v / n} for k, v in all_counts.items()]
    rules = []
    for itemset, count in all_counts.items():
        if len(itemset) < 2:
            continue
        for r in range(1, len(itemset)):
            for left in combinations(sorted(itemset), r):
                ant = frozenset(left)
                cons = itemset - ant
                support, confidence = count / n, count / all_counts[ant]
                lift = confidence / (all_counts[cons] / n)
                if confidence >= min_confidence and lift >= min_lift:
                    rules.append({"antecedent": sorted(ant), "consequent": sorted(cons), "support": support,
                                  "confidence": confidence, "lift": lift, "count": count})
    rules.sort(key=lambda x: (-x["lift"], -x["confidence"], -x["support"]))
    itemsets.sort(key=lambda x: (-x["size"], -x["count"]))
    return {"orders": n, "itemsets": itemsets[:limit], "rules": rules[:limit],
            "total_itemsets": len(itemsets), "total_rules": len(rules)}
