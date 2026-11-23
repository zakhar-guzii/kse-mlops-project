"""Train one model on the training batches, score it on the development control, write the result.

    python -m landcover.train {rule,rf,unet} [parameters]

A run is determined by the code commit, the data version and its parameters, so it refuses an
uncommitted tree and raw data that differs from data/raw.dvc. It reads only the raw files; it
never connects to the warehouse, the object store or the tracking server. The result is
runs/<model>-<commit7>-<id>/: the model file and run.json. Prints this path to stdout.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

from landcover import models
from landcover.pipeline import ROOT

PACKAGES = ["numpy", "rasterio", "scikit-learn", "scikit-image", "torch",
            "segmentation-models-pytorch", "timm"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def data_version(dvc_file):
    return data_hash(dvc_file.read_text())


def data_hash(pointer):
    return re.search(r"md5: (\S+)", pointer).group(1)


def verify_data(root, expected):
    if data_version(root / "data" / "raw.dvc") != expected:
        raise SystemExit(f"local data/raw.dvc does not name {expected}")
    status = subprocess.run(["dvc", "status", "--json", "data/raw.dvc"], cwd=root, check=False,
                            capture_output=True, text=True)
    if status.returncode or json.loads(status.stdout or "null") != {}:
        raise SystemExit(f"data/raw does not match data/raw.dvc; run `dvc pull`:\n"
                         f"{status.stdout}{status.stderr}")


def identity():
    """(commit, data version), or exit naming why the run would not be reproducible."""
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"uncommitted changes; commit them first:\n{dirty}")
    data = data_version(ROOT / "data" / "raw.dvc")
    verify_data(ROOT, data)
    return git("rev-parse", "HEAD"), data


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def parse(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.train")
    sub = parser.add_subparsers(dest="model", required=True)
    sub.add_parser("rule", help="majority class of the training labels")
    rf = sub.add_parser("rf", help="random forest on pixel texture features")
    rf.add_argument("--seed", type=int, default=0)
    rf.add_argument("--per-class", type=int, default=10_000)
    rf.add_argument("--trees", type=int, default=100)
    rf.add_argument("--depth", type=int, default=12)
    unet = sub.add_parser("unet", help="U-Net with an EfficientNet-B4 encoder")
    unet.add_argument("--seed", type=int, default=0)
    unet.add_argument("--epochs", type=int, default=40)
    unet.add_argument("--batch-size", type=int, default=8)
    unet.add_argument("--lr", type=float, default=3e-4)
    unet.add_argument("--weight-decay", type=float, default=1e-4)
    unet.add_argument("--device", choices=["auto", "cuda", "mps", "cpu"], default="auto")
    unet.add_argument("--encoder-revision", default=models.ENCODER_REVISION)
    args = parser.parse_args(argv)
    if args.model == "unet" and not re.fullmatch(r"[0-9a-f]{40}", args.encoder_revision):
        parser.error("--encoder-revision requires a full Hugging Face commit hash")
    return args


def train(args, commit, data, out):
    kind = args.model
    params = {k: v for k, v in vars(args).items() if k != "model"}
    roles = {role: models.batches(role) for role in ("train", "dev", "final")}
    model_file = out / models.MODEL_FILES[kind]

    train_tiles = models.load_tiles(roles["train"])
    dev_tiles = models.load_tiles(roles["dev"])
    record = {"history": [], "device": "cpu"}
    if kind == "rule":
        class_id = models.fit_rule(train_tiles)
        model_file.write_text(json.dumps({"class_id": class_id}))
        predict = models.rule_predictor(class_id)
    elif kind == "rf":
        import joblib

        forest = models.fit_forest(train_tiles, args.per_class, args.trees, args.depth, args.seed)
        joblib.dump(forest, model_file)
        predict = models.forest_predictor(forest)
    else:
        import torch

        device = models.pick_device() if args.device == "auto" else args.device
        model, history = models.fit_unet(train_tiles, dev_tiles, args.epochs, args.batch_size,
                                         args.lr, args.weight_decay, args.seed, device,
                                         args.encoder_revision)
        torch.save(model.state_dict(), model_file)
        predict = models.unet_predictor(model, device)
        record = {"history": history, "device": device,
                  "encoder_weights": {"repo": models.ENCODER_REPO,
                                      "revision": args.encoder_revision}}
        if device == "cuda":
            record["gpu_name"] = torch.cuda.get_device_name()

    dev_scores, matrix = models.evaluate(predict, dev_tiles)
    record = {"model": kind, "params": params, "batches": roles, "git_commit": commit,
              "data_version": data, "scores": dev_scores, "confusion_matrix": matrix,
              **record, "packages": {p: installed(p) for p in PACKAGES if installed(p)},
              "model_file": model_file.name, "model_sha256": sha256(model_file)}
    (out / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    return dev_scores["miou"]


def main(argv=None):
    args = parse(argv)
    commit, data = identity()
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    out = runs / f"{args.model}-{commit[:7]}-{uuid4().hex}"
    with tempfile.TemporaryDirectory(dir=runs, prefix=".training-") as scratch:
        staging = Path(scratch) / "result"
        staging.mkdir()
        score = train(args, commit, data, staging)
        staging.rename(out)
    print(f"{out.relative_to(ROOT)}: development mIoU {score:.4f}", file=sys.stderr)
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
