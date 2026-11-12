import argparse

import pandas as pd

import common


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs=3, default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 80)

    df = common.load_go_df(a.refresh)
    print("Go-вакансий всего: %d" % len(df))
    print("\nТоп-10 регионов по числу Go-вакансий:")
    print(df.area.value_counts().head(10).to_string())
    regions = a.regions or df.area.value_counts().head(3).index.tolist()
    print("\nВыбраны регионы:", ", ".join(regions))

    rows = []
    for r in regions:
        d = df[df.area == r]
        s = d.salary.dropna()
        rows.append({
            "регион": r, "вакансий": len(d),
            "с навыками, %": round(100 * (d.skills.str.len() > 0).mean(), 1),
            "с зарплатой (RUR), %": round(100 * len(s) / len(d), 1),
            "n с зарплатой": len(s),
            "медиана": round(s.median()) if len(s) else None,
            "Q1": round(s.quantile(.25)) if len(s) else None,
            "Q3": round(s.quantile(.75)) if len(s) else None,
            "опыт 3-6 лет, %": round(100 * (d.experience == "От 3 до 6 лет").mean(), 1),
            "удалёнка, %": round(100 * d.schedule.fillna("").str.contains("даленн").mean(), 1),
        })
    t1 = pd.DataFrame(rows)
    print("\nТаблица 1. Зарплаты и состав вакансий")
    print(t1.to_string(index=False))
    t1.to_csv(common.RESULTS_DIR / "regions_table1.csv", index=False, encoding="utf-8-sig")

    print("\nОпыт, % вакансий региона")
    print(pd.crosstab(df[df.area.isin(regions)].area, df[df.area.isin(regions)].experience, normalize="index").mul(100).round(1).to_string())

    out = []
    print("\nТаблица 2. Навыки, пары и тройки по регионам")
    for r in regions:
        d = df[df.area == r]
        cs = common.skill_counters(d.skills.tolist(), exclude_go=False)
        for n, label in ((1, "навыки"), (2, "пары"), (3, "тройки")):
            top = cs[n].most_common(a.top)
            out += [dict(регион=r, тип=label, набор=k, вакансий=v, доля_региона_pct=round(100 * v / len(d), 1)) for k, v in top]
            print("\n%s — %s (всего Go-вакансий в регионе: %d):" % (r, label, len(d)))
            for k, v in top:
                print("  %4d  (%4.1f%%)  %s" % (v, 100 * v / len(d), k))
    pd.DataFrame(out).to_csv(common.RESULTS_DIR / "regions_table2.csv", index=False, encoding="utf-8-sig")
    print("\nсохранено: results/regions_table1.csv, results/regions_table2.csv")


if __name__ == "__main__":
    main()