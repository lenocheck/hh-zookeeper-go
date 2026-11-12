import argparse
from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd

import common
from common import SEP, median


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=10, help="минимум вакансий с зарплатой в наборе")
    ap.add_argument("--min-emp", type=int, default=3, help="минимум разных работодателей в наборе")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--refresh", action="store_true", help="перечитать данные из S3")
    a = ap.parse_args()
    pd.set_option("display.width", 250, "display.max_columns", 20, "display.max_colwidth", 70)

    df = common.load_go_df(a.refresh)
    sal = df[df.salary.notna()].copy()
    sal["sk"] = sal.skills
    print("Go-вакансий: %d; с зарплатой в RUR: %d; из них с навыками: %d"
          % (len(df), len(sal), (sal.sk.str.len() > 0).sum()))
    base_all = median(sal.salary.tolist())
    print("медиана всех Go-вакансий с зарплатой: %.0f руб. (net)" % base_all)

    print("\nПо опыту")
    g = sal.groupby("experience").salary.agg(["count", "median"]).sort_values("median")
    print(g.round(0).to_string())

    by_skill = defaultdict(list)
    by_pair, by_triple = defaultdict(list), defaultdict(list)
    emp_pair, emp_triple = defaultdict(set), defaultdict(set)
    for s, sk, e in zip(sal.salary, sal.sk, sal.employer_id):
        for x in sk:
            by_skill[x].append(s)
        for c in combinations(sk, 2):
            by_pair[c].append(s)
            emp_pair[c].add(e)
        for c in combinations(sk, 3):
            by_triple[c].append(s)
            emp_triple[c].add(e)
    freq = Counter({k: len(v) for k, v in by_skill.items()})

    print("\nОдиночные навыки (n >= %d), отличие от медианы всех Go-вакансий" % a.min_n)
    one = pd.DataFrame([(k, len(v), median(v), median(v) - base_all) for k, v in by_skill.items() if len(v) >= a.min_n],
                       columns=["навык", "n", "медиана", "прибавка к общей"]).sort_values("прибавка к общей", ascending=False)
    print(one.round(0).head(a.top).to_string(index=False))
    print(one.round(0).tail(a.top).to_string(index=False))

    def table(groups, emps, size):
        rows = []
        for combo, vals in groups.items():
            if len(vals) < a.min_n or len(emps[combo]) < a.min_emp:
                continue
            ranked = sorted(combo, key=lambda x: (-freq[x], x))
            base_key = ranked[0]
            base_vals = by_skill[base_key]
            bm, m = median(base_vals), median(vals)
            row = {"набор": SEP.join(combo), "n": len(vals), "работодателей": len(emps[combo]), "медиана": m,
                   "база": base_key, "n_базы": len(base_vals), "медиана_базы": bm,
                   "прибавка": m - bm, "прибавка_pct": 100 * (m - bm) / bm}
            if size == 3:
                pair = tuple(sorted(ranked[:2]))
                pm = median(by_pair[pair])
                row.update({"база_пара": SEP.join(pair), "n_пары": len(by_pair[pair]), "медиана_пары": pm, "прибавка_к_паре": m - pm})
            rows.append(row)
        return pd.DataFrame(rows)

    for size, groups, emps, name in ((2, by_pair, emp_pair, "пары"), (3, by_triple, emp_triple, "тройки")):
        t = table(groups, emps, size)
        if t.empty:
            print("\n%s: нет наборов с n >= %d и работодателей >= %d" % (name, a.min_n, a.min_emp))
            continue
        t = t.sort_values("прибавка", ascending=False)
        t.to_csv(common.RESULTS_DIR / ("salary_%s.csv" % name.lower()), index=False, encoding="utf-8-sig")
        print("\n%s, повышают медиану (топ-%d, n >= %d, работодателей >= %d)" % (name, a.top, a.min_n, a.min_emp))
        print(t.head(a.top).round(1).to_string(index=False))
        print("\n%s, понижают медиану (топ-%d, n >= %d, работодателей >= %d)" % (name, a.top, a.min_n, a.min_emp))
        print(t.sort_values("прибавка").head(a.top).round(1).to_string(index=False))
    print("\nполные таблицы: results/salary_пары.csv, results/salary_тройки.csv")


if __name__ == "__main__":
    main()