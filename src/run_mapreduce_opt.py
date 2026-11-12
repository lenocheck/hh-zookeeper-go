import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from itertools import combinations
from math import comb

import common
from common import SEP, BUCKET, CSV_KEY
from s3_chunks import iter_chunks, MIB


def map_combine(idx, records, ns):
    vacancies = common.go_vacancy_skills(idx, records, prefilter=True)
    local = {n: Counter() for n in ns}
    expected = {n: 0 for n in ns}
    for skills in vacancies:
        for n in ns:
            expected[n] += comb(len(skills), n)
            for combo in combinations(skills, n):
                local[n][SEP.join(combo)] += 1
    return len(records), len(vacancies), local, expected


def main(argv=None, s3=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[1], choices=[1, 2, 3])
    ap.add_argument("--chunk-mib", type=float, default=16)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args(argv)
    ns = args.n
    s3 = s3 or common.get_s3()
    t_start = time.perf_counter()

    totals = {n: Counter() for n in ns}
    expected = {n: 0 for n in ns}
    stats = {"records": 0, "go": 0, "chunks": 0}
    idx = None

    def absorb(fut):
        nrec, ngo, local, exp = fut.result()
        stats["records"] += nrec
        stats["go"] += ngo
        for n in ns:
            totals[n].update(local[n])
            expected[n] += exp[n]

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = set()
        for ci, records in iter_chunks(s3, BUCKET, CSV_KEY, int(args.chunk_mib * MIB)):
            if idx is None:
                if not records:
                    continue
                idx = common.parse_header(records.pop(0))
            stats["chunks"] += 1
            pending.add(pool.submit(map_combine, idx, records, ns))
            while len(pending) >= args.workers * 2:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for f in done:
                    absorb(f)
        for f in pending:
            absorb(f)
    total = time.perf_counter() - t_start

    for n in ns:
        assert sum(totals[n].values()) == expected[n]
        meta = dict(total_records=stats["records"], go_vacancies=stats["go"], expected_occurrences=expected[n],
                    chunks=stats["chunks"], chunk_mib=args.chunk_mib, workers=args.workers, seconds=round(total, 2))
        meta = common.save_result(s3, "mr_opt", n, dict(totals[n]), meta)
        print("\nMapReduce (оптимизированный), n=%d" % n)
        print("чанков: %d, записей: %d, Go-вакансий: %d, процессов: %d" % (stats["chunks"], stats["records"], stats["go"], args.workers))
        print("уникальных ключей: %d, вхождений: %d" % (meta["unique_keys"], meta["total_occurrences"]))
        print("sha256: %s" % meta["sha256"])
        ref = common.RESULTS_DIR / ("mr_n%d.meta.json" % n)
        if ref.exists():
            same = json.loads(ref.read_text(encoding="utf-8"))["sha256"] == meta["sha256"]
            print("совпадает с базовым MapReduce: %s" % ("да" if same else "нет"))
    print("время: %.1f с" % total)


if __name__ == "__main__":
    main()