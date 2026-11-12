import os
from datetime import datetime
from pathlib import Path

ZK_HOSTS = os.environ.get("ZK_HOSTS", "localhost:2181,localhost:2182,localhost:2183")
SESSION_TIMEOUT = 10
BASE = "/hh"
ELECTION = BASE + "/election"
EPOCH = BASE + "/epoch"
POINTER = BASE + "/result_pointer"
ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]