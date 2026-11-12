import argparse
import re
import time

import psutil

import zk_common as Z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--name", default="A")
    ap.add_argument("--at-chunk", type=int, default=32)
    ap.add_argument("--seconds", type=float, default=40)
    a = ap.parse_args()
    pause_log = Z.LOGS / ("%s_pause.log" % a.tag)
    pause_log.write_text("", encoding="utf-8")

    def log(msg):
        line = "%s [PAUSE] %s" % (Z.stamp(), msg)
        print(line, flush=True)
        with open(pause_log, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

    pid_file = Z.LOGS / ("%s_%s.pid" % (a.tag, a.name))
    while not pid_file.exists():
        time.sleep(0.2)
    time.sleep(0.5)
    pid = int(pid_file.read_text())
    proc = psutil.Process(pid)
    log("ожидание, пока координатор %s (PID %d) дойдёт до чанка %d" % (a.name, pid, a.at_chunk))
    pat = re.compile(r"чанк (\d+)/\d+ обработан")
    lg = Z.LOGS / ("%s_%s.log" % (a.tag, a.name))
    while True:
        found = pat.findall(lg.read_text(encoding="utf-8", errors="replace"))
        if found and int(found[-1]) >= a.at_chunk:
            break
        time.sleep(0.1)
    proc.suspend()
    log("Приостановлен процесс %s (PID %d) на чанке %s, пауза %.0f с" % (a.name, pid, found[-1], a.seconds))
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        time.sleep(5)
        log("прошло %.0f с" % (time.time() - t0))
    proc.resume()
    log("Возобновлён процесс %s (PID %d)" % (a.name, pid))


if __name__ == "__main__":
    main()