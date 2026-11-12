import argparse

from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

import common
import zk_common as Z


def purge(s3, prefix):
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=common.BUCKET, Prefix=prefix):
        for o in page.get("Contents", []):
            s3.delete_object(Bucket=common.BUCKET, Key=o["Key"])
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    zk = KazooClient(hosts=Z.ZK_HOSTS, timeout=Z.SESSION_TIMEOUT)
    zk.start(timeout=30)
    try:
        zk.delete(Z.BASE, recursive=True)
    except NoNodeError:
        pass
    zk.create(Z.ELECTION, makepath=True)
    zk.create(Z.EPOCH, b"0")
    zk.create(Z.POINTER, b"none")
    print("ZooKeeper: созданы", Z.ELECTION, Z.EPOCH, Z.POINTER, "(версия указателя %d)" % zk.exists(Z.POINTER).version)
    zk.stop()
    s3 = common.get_s3()
    for prefix in ("checkpoints/%s/" % a.tag, "results/zk/%s/" % a.tag):
        print("S3: удалено %d объектов с префиксом %s" % (purge(s3, prefix), prefix))
    for f in Z.LOGS.glob("%s_*.pid" % a.tag):
        f.unlink()


if __name__ == "__main__":
    main()