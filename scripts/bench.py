"""Section 7.3 measurements on the cluster (openspec add-lab4-drift-alert, design Decision 7).

    uv run --locked python scripts/bench.py --ml http://127.0.0.1:8000 --prometheus http://127.0.0.1:9090 \
        [--llm http://127.0.0.1:8002]

/predict at 256, 512 and 1024 pixels (5 warm-up and 30 measured requests each), the 512 run again with 2 concurrent
clients, the first 10 questions of eval/questions.toml to /ask when --llm is given, the p95 of all /predict requests
next to Prometheus' histogram_quantile, and memory.peak of every running pod. Requests carry X-Source-Id bench/...,
so they count as served traffic: run it outside the drift demonstration's windows.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from landcover.monitor import quadrants, tiles

WARM, RUNS = 5, 30


def post(url, body, headers):
    start = time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=300) as response:
        response.read()
    return time.perf_counter() - start


def mosaic(paths):
    """A 1024x1024 GeoTIFF of four 512x512 tiles in a 2x2 grid, on the first tile's grid."""
    data = []
    for path in paths:
        with rasterio.open(path) as src:
            data.append(src.read())
            profile, colorinterp = src.profile, src.colorinterp
    with MemoryFile() as memfile:
        with memfile.open(**profile | {"width": 1024, "height": 1024}) as dst:
            dst.write(np.block([[data[0], data[1]], [data[2], data[3]]]))
            dst.colorinterp = colorinterp
        return memfile.read()


def summary(seconds, wall):
    p95 = statistics.quantiles(seconds, n=20)[18]
    return f"p50 {statistics.median(seconds):.3f} s, p95 {p95:.3f} s, {len(seconds) / wall:.2f} requests/s"


def predict(ml, name, body, clients=1):
    url = f"{ml}/predict"
    for i in range(WARM):
        post(url, body, {"X-Source-Id": f"bench/{name}/warm{i}"})
    start = time.perf_counter()
    with ThreadPoolExecutor(clients) as pool:
        seconds = list(pool.map(lambda i: post(url, body, {"X-Source-Id": f"bench/{name}/{i}"}), range(RUNS)))
    print(f"/predict {name:>12}: {summary(seconds, time.perf_counter() - start)}", flush=True)
    return seconds


def ask(llm):
    questions = tomllib.loads((ROOT / "eval" / "questions.toml").read_text())["questions"][:10]
    seconds = [post(f"{llm}/ask", json.dumps({"question": q["question"]}).encode(),
                    {"Content-Type": "application/json", "X-Source-Id": f"bench/ask/{q['id']}"})
               for q in questions]
    print(f"/ask {len(seconds)} questions: p50 {statistics.median(seconds):.2f} s, "
          f"p95 {statistics.quantiles(seconds, n=20)[18]:.2f} s")


def prometheus_p95(prometheus, seconds):
    query = ('histogram_quantile(0.95, sum by (le) (increase(landcover_request_seconds_bucket'
             f'{{job="ml",endpoint="/predict"}}[{seconds}s])))')
    url = f"{prometheus}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    with urllib.request.urlopen(url, timeout=30) as response:
        result = json.load(response)["data"]["result"]
    return float(result[0]["value"][1]) if result else None


def memory():
    kubectl = ["minikube", "kubectl", "--"]
    pods = subprocess.run(kubectl + ["get", "pods", "--field-selector=status.phase=Running", "-o", "name"],
                          capture_output=True, text=True, check=True).stdout.split()
    for pod in pods:
        peak = subprocess.run(kubectl + ["exec", pod, "--", "cat", "/sys/fs/cgroup/memory.peak"],
                              capture_output=True, text=True, check=False)
        value = f"{int(peak.stdout) / 2**20:,.0f} MiB" if peak.returncode == 0 else "not readable"
        print(f"memory.peak {pod.removeprefix('pod/')}: {value}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scripts/bench.py")
    parser.add_argument("--ml", required=True)
    parser.add_argument("--prometheus", required=True)
    parser.add_argument("--llm", help="the LLM service; /ask is measured only when given")
    args = parser.parse_args(argv)

    path = tiles("D017-2021")[0]
    started = time.time()
    seconds = predict(args.ml, "256", next(quadrants(path))[1])
    seconds += predict(args.ml, "512", path.read_bytes())
    seconds += predict(args.ml, "1024", mosaic(tiles("D017-2021")[:4]))
    seconds += predict(args.ml, "512 2 clients", path.read_bytes(), clients=2)
    time.sleep(20)  # one scrape after the last request
    measured = statistics.quantiles(seconds, n=20)[18]
    p95 = prometheus_p95(args.prometheus, int(time.time() - started) + 1)
    print(f"/predict all sizes: p95 {measured:.3f} s measured (without warm-ups), "
          f"histogram_quantile(0.95) {p95 if p95 is None else f'{p95:.3f}'} s")
    if args.llm:
        ask(args.llm)
    memory()


if __name__ == "__main__":
    main()
