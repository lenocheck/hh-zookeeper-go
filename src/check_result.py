import argparse
import hashlib
from datetime import datetime

from kazoo.client import KazooClient

import common
import zk_common as Z


def read(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def ts(line):
    return datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S.%f")


def first(lines, text):
    return next((ln for ln in lines if text in ln), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=2)
    a = ap.parse_args()
    s3 = common.get_s3()
    ref, refmeta, refsha = common.read_result(s3, "mr", a.n)
    print("ДЗ 3 (s3://hh-lake/results/mr/n%d.tsv)" % a.n)
    print("ключей %d, вхождений %d, sha256 %s" % (len(ref), sum(ref.values()), refsha))

    print("\nРезультаты прогона %s в S3 (results/zk/%s/)" % (a.tag, a.tag))
    objs = s3.list_objects_v2(Bucket=common.BUCKET, Prefix="results/zk/%s/" % a.tag).get("Contents", [])
    for o in objs:
        body = s3.get_object(Bucket=common.BUCKET, Key=o["Key"])["Body"].read()
        sha = hashlib.sha256(body).hexdigest()
        print("%s: %d байт, sha256 %s, %s ДЗ 3" % (o["Key"], o["Size"], sha, "совпадает с" if sha == refsha else "не совпадает с"))
    print("файлов результата: %d" % len(objs))

    print("\nZooKeeper")
    zk = KazooClient(hosts=Z.ZK_HOSTS, timeout=Z.SESSION_TIMEOUT)
    zk.start(timeout=30)
    data, stat = zk.get(Z.POINTER)
    _, est = zk.get(Z.EPOCH)
    zk.stop()
    if ("results/zk/%s/" % a.tag) in data.decode():
        print("/hh/result_pointer: dataVersion=%d, данные: %s" % (stat.version, data.decode()))
        print("/hh/epoch: dataVersion=%d" % est.version)
    else:
        print("/hh/result_pointer сейчас относится к другому прогону, состояние этого прогона в logs\\transcript_stage3.txt")

    print("\nЖурналы")
    logs = {n: read(Z.LOGS / ("%s_%s.log" % (a.tag, n))) for n in ("A", "B")}
    for n, lines in logs.items():
        print("%s: строк «записан результат»: %d, строк с BadVersionError: %d"
              % (n, sum("записан результат" in x for x in lines), sum("BadVersionError" in x for x in lines)))
    pause = read(Z.LOGS / ("%s_pause.log" % a.tag))
    p_susp, p_res = first(pause, "Приостановлен"), first(pause, "Возобновлён")
    b_lead, b_pub = first(logs["B"], "] лидер, эпоха"), first(logs["B"], "записан результат")
    if p_susp and b_lead:
        print("\nВремя смены лидера: %.1f с (лидер приостановлен %s, B стал лидером %s)"
              % ((ts(b_lead) - ts(p_susp)).total_seconds(), p_susp[:23], b_lead[:23]))
    if p_res and b_pub:
        print("B опубликовал результат %s, A возобновлён %s: B закончил %s возобновления A"
              % (b_pub[:23], p_res[:23], "до" if ts(b_pub) < ts(p_res) else "после"))
    ck = first(logs["B"], "восстановлен чекпоинт")
    if ck:
        print("B: " + ck[ck.index("восстановлен"):])


if __name__ == "__main__":
    main()