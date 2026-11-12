import argparse
import json
import os
import statistics
import subprocess
import sys
import time

import psutil

import common


def run_once(cmd, log_path):
    env = dict(os.environ, PYTHONUTF8="1")
    with open(log_path, "wb") as log:
        t0 = time.perf_counter()
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
        proc = psutil.Process(p.pid)
        peak = 0
        while p.poll() is None:
            try:
                procs = [proc] + proc.children(recursive=True)
                rss = 0
                for q in procs:
                    try:
                        rss += q.memory_info().rss
                    except psutil.Error:
                        pass
                peak = max(peak, rss)
            except psutil.Error:
                pass
            time.sleep(0.05)
        return time.perf_counter() - t0, peak / 2 ** 20, p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default=None)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = [c for i, c in enumerate(a.cmd) if not (i == 0 and c == "--")]
    if cmd and cmd[0] in ("python", "python3", "py"):
        cmd[0] = sys.executable
    label = a.label or "_".join(os.path.splitext(os.path.basename(c))[0] for c in cmd[1:2] + cmd[2:])
    (common.ROOT / "logs").mkdir(exist_ok=True)
    rows = []
    print("команда:", " ".join(cmd))
    for i in range(1, a.runs + 1):
        t, mem, rc = run_once(cmd, common.ROOT / "logs" / ("profile_%s_run%d.log" % (label, i)))
        rows.append((i, t, mem, rc))
        print("попытка %d: %.1f с, пик памяти %.0f МБ, код возврата %d" % (i, t, mem, rc), flush=True)
    ts, ms = [r[1] for r in rows], [r[2] for r in rows]
    print("\n| попытка | время, с | пик памяти, МБ |")
    for i, t, mem, rc in rows:
        print("| %d | %.1f | %.0f |" % (i, t, mem))
    sd = statistics.stdev(ts) if len(ts) > 1 else 0.0
    print("| среднее | %.1f | %.0f (макс. %.0f) |" % (statistics.mean(ts), statistics.mean(ms), max(ms)))
    out = common.RESULTS_DIR / ("profile_%s.json" % label)
    out.write_text(json.dumps(dict(cmd=cmd, runs=[dict(run=i, seconds=t, peak_mb=m, rc=rc) for i, t, m, rc in rows], mean_seconds=statistics.mean(ts), mean_peak_mb=statistics.mean(ms)), indent=2), encoding="utf-8")
    print("сохранено:", out)


if __name__ == "__main__":
    main()