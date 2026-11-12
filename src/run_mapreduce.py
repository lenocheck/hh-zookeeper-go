import argparse
import json
import time
from collections import defaultdict
from math import comb

import common
from common import SEP, BUCKET, CSV_KEY
from s3_chunks import iter_chunks, MIB

MAX_ATTEMPTS = 3


def map_chunk(idx, records, ns, fail=False):
    if fail:
        raise RuntimeError("simulated mapper failure")
    from itertools import combinations
    vacancies = common.go_vacancy_skills(idx, records)
    pairs = []
    expected = {n: 0 for n in ns}
    for skills in vacancies:
        for n in ns:
            expected[n] += comb(len(skills), n)
            for combo in combinations(skills, n):
                pairs.append((n, SEP.join(combo), 1))
    return len(records), len(vacancies), pairs, expected


def reduce_all(groups):
    return {key: sum(vals) for key, vals in groups.items()}


def main(argv=None, s3=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[1], choices=[1, 2, 3], help="размер набора навыков")
    ap.add_argument("--chunk-mib", type=float, default=16, help="размер чанка (Range-запроса), МиБ")
    ap.add_argument("--fail-chunk", type=int, default=None, help="уронить маппер на этом чанке при первой попытке")
    args = ap.parse_args(argv)
    ns = args.n
    s3 = s3 or common.get_s3()
    engine = "mr_fail" if args.fail_chunk is not None else "mr"

    t_start = time.perf_counter()
    t_io = t_map = 0.0
    idx = None
    groups = defaultdict(list)
    n_chunks = total_records = go_vac = failures = 0
    expected = {n: 0 for n in ns}

    it = iter(iter_chunks(s3, BUCKET, CSV_KEY, int(args.chunk_mib * MIB)))
    while True:
        t0 = time.perf_counter()
        try:
            ci, records = next(it)
        except StopIteration:
            break
        t_io += time.perf_counter() - t0
        if idx is None:
            if not records:
                continue
            idx = common.parse_header(records.pop(0))
        n_chunks += 1
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.perf_counter()
            try:
                nrec, ngo, pairs, exp = map_chunk(idx, records, ns, fail=(ci == args.fail_chunk and attempt == 1))
                t_map += time.perf_counter() - t0
                break
            except Exception as e:
                t_map += time.perf_counter() - t0
                failures += 1
                print("[chunk %d] попытка %d упала: %s -> перезапуск" % (ci, attempt, e), flush=True)
        else:
            raise SystemExit("chunk %d: все %d попытки неудачны" % (ci, MAX_ATTEMPTS))
        if attempt > 1:
            print("[chunk %d] успешно с попытки %d" % (ci, attempt), flush=True)
        total_records += nrec
        go_vac += ngo
        for n in ns:
            expected[n] += exp[n]
        for n, key, v in pairs:
            groups[(n, key)].append(v)

    t0 = time.perf_counter()
    reduced = reduce_all(groups)
    t_reduce = time.perf_counter() - t0
    total = time.perf_counter() - t_start

    for n in ns:
        counts = {k: v for (nn, k), v in reduced.items() if nn == n}
        assert sum(counts.values()) == expected[n], "сумма не равна ожидаемому числу сочетаний"
        meta = dict(total_records=total_records, go_vacancies=go_vac, expected_occurrences=expected[n],
                    chunks=n_chunks, chunk_mib=args.chunk_mib, mapper_failures=failures,
                    seconds=round(total, 2), peak_mem_mb=round(common.peak_memory_mb(), 1))
        meta = common.save_result(s3, engine, n, counts, meta)
        print("\nMapReduce, n=%d (%s)" % (n, {1: "навыки", 2: "пары", 3: "тройки"}[n]))
        print("чанков: %d, записей в CSV: %d, Go-вакансий: %d" % (n_chunks, total_records, go_vac))
        print("уникальных ключей: %d, всего вхождений: %d (сумма C(m,%d) по вакансиям: %d)"
              % (meta["unique_keys"], meta["total_occurrences"], n, expected[n]))
        print("топ-10:")
        for line in common.result_lines(counts)[:10]:
            k, v = line.rsplit("\t", 1)
            print("  %6s  %s" % (v, k))
        print("sha256 результата: %s" % meta["sha256"])
        print("сохранено: s3://%s/results/%s/n%d.tsv" % (BUCKET, engine, n))
        if engine == "mr_fail":
            ref = common.RESULTS_DIR / ("mr_n%d.meta.json" % n)
            if ref.exists():
                same = json.loads(ref.read_text(encoding="utf-8"))["sha256"] == meta["sha256"]
                print("падений маппера: %d; результат %s обычного запуска (sha256)" % (failures, "совпал с" if same else "не совпал с"))
            else:
                print("падений маппера: %d; сначала запустите обычный запуск (без --fail-chunk) для сравнения" % failures)
    print("время: чтение из S3 %.1f с, map %.1f с, reduce %.1f с, всего %.1f с; пик памяти %.0f МБ"
          % (t_io, t_map, t_reduce, total, common.peak_memory_mb()))


if __name__ == "__main__":
    main()