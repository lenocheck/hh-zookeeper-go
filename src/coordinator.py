import argparse
import hashlib
import json
import logging
import os
import threading
import time
import traceback
from collections import Counter
from itertools import combinations
from math import comb

from botocore.exceptions import ClientError
from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError, NoNodeError, RolledBackError

import common
import zk_common as Z
from common import SEP, BUCKET, CSV_KEY
from s3_chunks import iter_chunks, object_size, MIB

logging.getLogger("kazoo").setLevel(logging.ERROR)
CHUNK = 16 * MIB


class Log:
    def __init__(self, name, path):
        self.name = name
        path.parent.mkdir(exist_ok=True)
        self.f = open(path, "w", encoding="utf-8", newline="\n")

    def __call__(self, msg):
        line = "%s [%s] %s" % (Z.stamp(), self.name, msg)
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def ensure(zk, path, data=b""):
    try:
        zk.create(path, data, makepath=True)
    except NodeExistsError:
        pass


def wait_for_leadership(zk, name, log):
    node = zk.create(Z.ELECTION + "/n_", name.encode(), ephemeral=True, sequence=True)
    mine = node.rsplit("/", 1)[1]
    log("выборы: узел %s" % node)
    while True:
        kids = sorted(zk.get_children(Z.ELECTION))
        if kids[0] == mine:
            return node
        prev = kids[kids.index(mine) - 1]
        ev = threading.Event()
        if zk.exists(Z.ELECTION + "/" + prev, watch=lambda e: ev.set()) is None:
            continue
        try:
            leader = zk.get(Z.ELECTION + "/" + kids[0])[0].decode()
        except NoNodeError:
            leader = "?"
        log("ожидание: лидер = %s, слежка за узлом %s" % (leader, prev))
        ev.wait()


def ckpt_key(tag):
    return "checkpoints/%s/state.json" % tag


def load_ckpt(s3, tag):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=ckpt_key(tag))["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def do_work(s3, a, tag, name, epoch, state, log):
    n = a.n
    total_chunks = -(-object_size(s3, BUCKET, CSV_KEY) // CHUNK)
    counts = Counter(state["counts"]) if state else Counter()
    start = state["next_chunk"] if state else 0
    st = dict(records=state["records"], go=state["go"], expected=state["expected"]) if state else dict(records=0, go=0, expected=0)
    if start:
        log("чанки 0..%d уже посчитаны, перечитывание их без обработки" % (start - 1))
    idx = None
    for ci, records in iter_chunks(s3, BUCKET, CSV_KEY, CHUNK):
        if idx is None:
            if not records:
                continue
            idx = common.parse_header(records.pop(0))
        if ci < start:
            continue
        vacancies = common.go_vacancy_skills(idx, records, prefilter=True)
        for sk in vacancies:
            st["expected"] += comb(len(sk), n)
            for combo in combinations(sk, n):
                counts[SEP.join(combo)] += 1
        st["records"] += len(records)
        st["go"] += len(vacancies)
        time.sleep(a.delay)
        log("чанк %d/%d обработан (Go-вакансий: %d)" % (ci + 1, total_chunks, st["go"]))
        if (ci + 1) % a.ckpt_every == 0 and ci + 1 < total_chunks:
            s3.put_object(Bucket=BUCKET, Key=ckpt_key(tag), Body=json.dumps(
                dict(next_chunk=ci + 1, counts=counts, writer=name, epoch=epoch, **st), ensure_ascii=False).encode("utf-8"))
            log("чекпоинт сохранён: следующий чанк %d" % (ci + 1))
    assert sum(counts.values()) == st["expected"], "сумма не равна ожидаемому числу сочетаний"
    return counts, st, total_chunks


def publish(s3, zk, a, tag, name, epoch, counts, st, total_chunks, log):
    text = "\n".join(common.result_lines(counts)) + "\n"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = "results/zk/%s/n%d_epoch%d.tsv" % (tag, a.n, epoch)
    s3.put_object(Bucket=BUCKET, Key=key, Body=text.encode("utf-8"))
    payload = json.dumps(dict(owner=name, epoch=epoch, key=key, sha256=sha, chunks=total_chunks, records=st["records"], go_vacancies=st["go"], unique_keys=len(counts), occurrences=sum(counts.values()))).encode()
    while not zk.connected:
        time.sleep(0.2)
    if a.fencing:
        def tx():
            t = zk.transaction()
            t.check(Z.EPOCH, version=epoch)
            t.set_data(Z.POINTER, payload)
            return t.commit()
        res = zk.retry(tx)
        bad = [r for r in res if isinstance(r, Exception) and not isinstance(r, RolledBackError)]
        if bad:
            log("Запись отклонена: %s: эпоха %d устарела, указатель не изменён" % (type(bad[0]).__name__, epoch))
            s3.delete_object(Bucket=BUCKET, Key=key)
            log("удален файл %s, результат не опубликован" % key)
            return False
        version = zk.exists(Z.POINTER).version
    else:
        version = zk.retry(lambda: zk.set(Z.POINTER, payload)).version
    log("записан результат: s3://%s/%s, эпоха %d, версия указателя %d, sha256 %s" % (BUCKET, key, epoch, version, sha))
    log("контрольные числа: чанков %d, записей CSV %d, Go-вакансий %d, ключей %d, вхождений %d"
        % (total_chunks, st["records"], st["go"], len(counts), sum(counts.values())))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--n", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--ckpt-every", type=int, default=3)
    a = ap.parse_args()
    a.fencing = os.environ.get("FENCING", "0") == "1"
    a.delay = float(os.environ.get("CHUNK_DELAY", "0.8"))
    tag = os.environ.get("RUN_TAG", "run")
    log = Log(a.name, Z.LOGS / ("%s_%s.log" % (tag, a.name)))
    (Z.LOGS / ("%s_%s.pid" % (tag, a.name))).write_text(str(os.getpid()))
    log("старт: PID=%d, RUN_TAG=%s, FENCING=%d, CHUNK_DELAY=%.2f, таймаут сессии %d с, n=%d"
        % (os.getpid(), tag, a.fencing, a.delay, Z.SESSION_TIMEOUT, a.n))
    s3 = common.get_s3()
    zk = KazooClient(hosts=Z.ZK_HOSTS, timeout=Z.SESSION_TIMEOUT)
    zk.add_listener(lambda s: log("состояние сессии ZooKeeper: %s" % s) and None)
    zk.start(timeout=30)
    log("подключён к ZooKeeper, session id 0x%x" % zk.client_id[0])
    try:
        ensure(zk, Z.ELECTION)
        ensure(zk, Z.EPOCH, b"0")
        ensure(zk, Z.POINTER, b"none")
        wait_for_leadership(zk, a.name, log)
        epoch = zk.set(Z.EPOCH, a.name.encode()).version
        log("лидер, эпоха %d" % epoch)
        if zk.get(Z.POINTER)[0] != b"none":
            log("результат уже опубликован")
            return
        state = load_ckpt(s3, tag)
        if state:
            log("восстановлен чекпоинт (записан %s, эпоха %s): продолжение с чанка %d, записей %d"
                % (state["writer"], state["epoch"], state["next_chunk"], state["records"]))
        else:
            log("чекпоинта нет, начало с чанка 0")
        counts, st, total = do_work(s3, a, tag, a.name, epoch, state, log)
        publish(s3, zk, a, tag, a.name, epoch, counts, st, total, log)
        log("работа завершена")
    except Exception:
        log("Ошибка:\n" + traceback.format_exc())
        raise
    finally:
        try:
            zk.stop()
            zk.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()