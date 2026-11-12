import sys

import common


def load(s3, engine, n):
    try:
        return common.read_result(s3, engine, n)
    except Exception as e:
        print("  (нет s3://hh-lake/results/%s/n%d.tsv: %s)" % (engine, n, type(e).__name__))
        return None


def main(s3=None):
    s3 = s3 or common.get_s3()
    ok_all = True
    growth = []
    for n in (1, 2, 3):
        print("\n n=%d" % n)
        mr, db = load(s3, "mr", n), load(s3, "duckdb", n)
        if not mr or not db:
            ok_all = False
            continue
        (c1, m1, h1), (c2, m2, h2) = mr, db
        only1 = sorted(set(c1) - set(c2))
        only2 = sorted(set(c2) - set(c1))
        diff = sorted(k for k in set(c1) & set(c2) if c1[k] != c2[k])
        same = not only1 and not only2 and not diff and h1 == h2
        ok_all &= same
        print("MapReduce: строк %d, вхождений %d, Go-вакансий %d, записей CSV %d"
              % (len(c1), sum(c1.values()), m1["go_vacancies"], m1["total_records"]))
        print("DuckDB: строк %d, вхождений %d, Go-вакансий %d, записей CSV %d"
              % (len(c2), sum(c2.values()), m2["go_vacancies"], m2["total_records"]))
        print("sha256 MR: %s" % h1)
        print("sha256 DuckDB: %s" % h2)
        print("Go-вакансий совпадает: %s; записей CSV совпадает: %s"
              % (m1["go_vacancies"] == m2["go_vacancies"], m1["total_records"] == m2["total_records"]))
        print("Результат: %s" % ("match (полное совпадение)" if same else "mismatch"))
        if not same:
            print("  только в MR: %d, только в DuckDB: %d, разные счёты: %d" % (len(only1), len(only2), len(diff)))
            for k in only1[:10]:
                print(" только MR:", k, c1[k])
            for k in only2[:10]:
                print(" только DuckDB:", k, c2[k])
            for k in diff[:10]:
                print(" разные счёты:", k, c1[k], c2[k])
        growth.append((n, len(c1), sum(c1.values()), m1["expected_occurrences"], m1["go_vacancies"]))

    print("\nРост числа комбинаций (из результатов MapReduce)")
    print("%-3s %-18s %-18s %-26s %s" % ("n", "уникальных ключей", "всего вхождений", "сумма C(m,n) по вакансиям", "Go-вакансий"))
    for n, u, t, e, g in growth:
        print("%-3d %-18d %-18d %-26d %d" % (n, u, t, e, g))
    print("\nИтог:", "все совпали" if ok_all else "есть расхождения")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())