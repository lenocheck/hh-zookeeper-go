import argparse
import time
from math import comb

import common
from common import SQL_DIR, BUCKET


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[1], choices=[1, 2, 3])
    args = ap.parse_args(argv)
    t_start = time.perf_counter()
    s3 = common.get_s3()
    con = common.duckdb_connect()
    for f in sorted(SQL_DIR.glob("0[0-9]_*.sql")):
        con.execute(f.read_text(encoding="utf-8").replace("{csv}", common.CSV_URI))
    total_rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    go_vac = con.execute("SELECT count(*) FROM go_ids").fetchone()[0]
    m_list = [r[0] for r in con.execute("SELECT count(*) FROM go_skills GROUP BY vacancy_id").fetchall()]

    for n in args.n:
        rows = con.execute((SQL_DIR / ("n%d.sql" % n)).read_text(encoding="utf-8")).fetchall()
        counts = {k: int(c) for k, c in rows}
        total = time.perf_counter() - t_start
        meta = dict(total_records=total_rows, go_vacancies=go_vac,
                    expected_occurrences=sum(comb(m, n) for m in m_list),
                    seconds=round(total, 2), peak_mem_mb=round(common.peak_memory_mb(), 1))
        meta = common.save_result(s3, "duckdb", n, counts, meta)
        print("\nDuckDB, n=%d" % n)
        print("записей в CSV: %d, Go-вакансий: %d" % (total_rows, go_vac))
        print("уникальных ключей: %d, всего вхождений: %d (сумма C(m,%d): %d)"
              % (meta["unique_keys"], meta["total_occurrences"], n, meta["expected_occurrences"]))
        print("топ-10:")
        for line in common.result_lines(counts)[:10]:
            k, v = line.rsplit("\t", 1)
            print("  %6s  %s" % (v, k))
        print("sha256 результата: %s" % meta["sha256"])
        print("сохранено: s3://%s/results/duckdb/n%d.tsv" % (BUCKET, n))
    print("время: %.1f с; пик памяти %.0f МБ" % (time.perf_counter() - t_start, common.peak_memory_mb()))


if __name__ == "__main__":
    main()