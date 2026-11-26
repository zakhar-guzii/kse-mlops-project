"""Smoke requests of make cluster (openspec add-lab4-cluster, design Decision 11). Standard library only.

predict: post a development tile to the ML service; fail unless it answers with the champion's version and the
deployed commit. ask: post one question to the LLM service; fail unless it answers with the configured model.
"""

import argparse
import json
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TILE = ROOT / "data/raw/D017-2021/images/AA-S2-9_2-7.tif"
QUESTION = "What does the value 255 mean in the output mask?"
MODEL_NAME = "landcover-segmenter"


def call(url, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"smoke failed: {url} answered {error.code}: {error.read().decode()[:300]}")


def check(condition, message):
    if not condition:
        sys.exit(f"smoke failed: {message}")


def predict(ml, mlflow, commit):
    alias = call(f"{mlflow}/api/2.0/mlflow/registered-models/alias?name={MODEL_NAME}&alias=champion")
    champion = alias["model_version"]["version"]
    body = call(f"{ml}/predict", TILE.read_bytes(), {"X-Source-Id": "smoke"})
    check(body["width"] == body["height"] == 512, f"mask is {body['width']}x{body['height']}, not 512x512")
    check(body.get("mask"), "the response has no mask")
    check(body["model_version"] == champion,
          f"served version {body['model_version']}, champion is version {champion}")
    check(body["image_commit"] == commit, f"image commit {body['image_commit']}, deployed commit {commit}")
    print(f"smoke /predict: {MODEL_NAME} version {body['model_version']} (champion), image {commit}")


def ask(llm):
    model = tomllib.loads((ROOT / "retrieval.toml").read_text())["llm"]["model"]
    body = call(f"{llm}/ask", json.dumps({"question": QUESTION}).encode(), {"Content-Type": "application/json"})
    check(body.get("answer", "").strip(), "the answer is empty")
    check(body["model"] == model, f"answered by {body['model']}, configured model is {model}")
    print(f"smoke /ask: {body['model']}, index {body['index_version']}, sources "
          f"{[s['doc_id'] for s in body['sources']]}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scripts/smoke.py")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--ml", required=True)
    p.add_argument("--mlflow", required=True)
    p.add_argument("--commit", required=True)
    sub.add_parser("ask").add_argument("--llm", required=True)
    args = parser.parse_args(argv)
    if args.command == "predict":
        predict(args.ml, args.mlflow, args.commit)
    else:
        ask(args.llm)


if __name__ == "__main__":
    main()
