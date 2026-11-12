import csv
import hashlib
import json
import os
import pickle
import re
import statistics
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

csv.field_size_limit(2 ** 30)

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
SQL_DIR = ROOT / "sql"

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:9010")
ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "hhadmin")
SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "hhadmin-secret")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BUCKET = "hh-lake"
CSV_KEY = "raw/it_vacancies_2024.csv"
CSV_URI = "s3://%s/%s" % (BUCKET, CSV_KEY)

ROLE = "Программист, разработчик"
NAME_PATTERN = r"(^|[^a-zа-я])(go|golang)([^a-zа-я]|$)"
NAME_RE = re.compile(NAME_PATTERN)
CYR_O = "\u043e"
RULE_VERSION = "name-only-v1"

SKILL_PATTERN = r"(^|[^a-zа-я0-9_-])(go|golang)([^a-zа-я0-9_-]|$)"
SKILL_RE = re.compile(SKILL_PATTERN)

NET_RATE = 0.87
SEP = " | "


def split_skills(raw):
    return raw.split(";") if ";" in raw else raw.split(",")


def parse_skills(raw):
    if not raw:
        return []
    return sorted({s.strip(" ").lower() for s in split_skills(raw) if s.strip(" ")})


def is_go(name):
    return bool(NAME_RE.search((name or "").lower().replace(CYR_O, "o")))


def parse_header(record):
    import io
    row = next(csv.reader(io.StringIO(record.lstrip("\ufeff"), newline="")))
    return {name: i for i, name in enumerate(row)}


def go_vacancy_skills(idx, records, prefilter=False):
    import io
    if prefilter:
        records = [r for r in records if ROLE in r]
    ri, ni, ki = idx["role"], idx["name"], idx["key_skills"]
    need = max(ri, ni, ki)
    out = []
    for row in csv.reader(io.StringIO("".join(records), newline="")):
        if len(row) <= need or row[ri] != ROLE:
            continue
        if is_go(row[ni]):
            out.append(parse_skills(row[ki]))
    return out


def comb_count(m, n):
    from math import comb
    return comb(m, n)


def _num(x):
    if x is None:
        return None
    x = str(x).strip()
    if x in ("", "None", "nan"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def salary_value(frm, to, currency, gross):
    if currency != "RUR":
        return None
    f, t = _num(frm), _num(to)
    if f is None and t is None:
        return None
    v = (f + t) / 2 if (f is not None and t is not None) else (f if f is not None else t)
    if str(gross).lower() == "true":
        v *= NET_RATE
    return v


def get_s3():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
        region_name=REGION, config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}))


def duckdb_connect():
    import duckdb
    u = urlparse(ENDPOINT)
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute("SET s3_endpoint='%s'" % u.netloc)
    con.execute("SET s3_access_key_id='%s'" % ACCESS_KEY)
    con.execute("SET s3_secret_access_key='%s'" % SECRET_KEY)
    con.execute("SET s3_use_ssl=%s" % ("true" if u.scheme == "https" else "false"))
    con.execute("SET s3_url_style='path'")
    con.execute("SET s3_region='%s'" % REGION)
    return con


def result_lines(counts):
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ["%s\t%d" % (k, v) for k, v in items]


def save_result(s3, engine, n, counts, meta):
    RESULTS_DIR.mkdir(exist_ok=True)
    text = "\n".join(result_lines(counts)) + "\n"
    meta = dict(meta)
    meta.update(engine=engine, n=n, unique_keys=len(counts), total_occurrences=sum(counts.values()), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    (RESULTS_DIR / ("%s_n%d.tsv" % (engine, n))).write_text(text, encoding="utf-8", newline="\n")
    (RESULTS_DIR / ("%s_n%d.meta.json" % (engine, n))).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    s3.put_object(Bucket=BUCKET, Key="results/%s/n%d.tsv" % (engine, n), Body=text.encode("utf-8"))
    s3.put_object(Bucket=BUCKET, Key="results/%s/n%d.meta.json" % (engine, n), Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"))
    return meta


def read_result(s3, engine, n):
    body = s3.get_object(Bucket=BUCKET, Key="results/%s/n%d.tsv" % (engine, n))["Body"].read()
    meta = json.loads(s3.get_object(Bucket=BUCKET, Key="results/%s/n%d.meta.json" % (engine, n))["Body"].read())
    counts = {}
    for line in body.decode("utf-8").splitlines():
        k, v = line.rsplit("\t", 1)
        counts[k] = int(v)
    return counts, meta, hashlib.sha256(body).hexdigest()


def peak_memory_mb():
    import psutil
    mi = psutil.Process().memory_info()
    return getattr(mi, "peak_wset", mi.rss) / 2 ** 20


def load_go_df(refresh=False):
    cache = RESULTS_DIR / ("_cache_go_%s.pkl" % RULE_VERSION)
    if cache.exists() and not refresh:
        return pickle.loads(cache.read_bytes())
    import pandas as pd
    con = duckdb_connect()
    rows = con.execute(
        "SELECT vacancy_id, area, name, experience, schedule, salary_from, salary_to, currency, gross, key_skills, employer_id "
        "FROM read_csv('%s', header=true, quote='\"', escape='\"', all_varchar=true) WHERE role = ?" % CSV_URI,
        [ROLE]).fetchall()
    recs = []
    for vid, area, name, exp, sched, sf, st, cur, gross, ks, emp in rows:
        if not is_go(name):
            continue
        skills = parse_skills(ks)
        recs.append(dict(vacancy_id=vid, employer_id=emp, area=area, name=name, experience=exp, schedule=sched, currency=cur, gross=gross, skills=skills, salary=salary_value(sf, st, cur, gross)))
    df = pd.DataFrame(recs)
    RESULTS_DIR.mkdir(exist_ok=True)
    cache.write_bytes(pickle.dumps(df))
    return df


def skill_counters(skill_lists, ns=(1, 2, 3), exclude_go=False):
    from collections import Counter
    cs = {n: Counter() for n in ns}
    for sk in skill_lists:
        if exclude_go:
            sk = [s for s in sk if not SKILL_RE.search(s)]
        for n in ns:
            for combo in combinations(sk, n):
                cs[n][SEP.join(combo)] += 1
    return cs


def median(xs):
    return statistics.median(xs) if len(xs) else float("nan")