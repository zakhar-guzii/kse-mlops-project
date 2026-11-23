"""MLflow steps: log a training result, register a run, move `champion`, reproduce a version.

    python -m landcover.tracking log DIR [--tag KEY=VALUE]
    python -m landcover.tracking register RUN_ID
    python -m landcover.tracking champion VERSION
    python -m landcover.tracking reproduce VERSION

`log` is the only way a result enters MLflow, for local and remote runs alike.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import mlflow
import numpy as np
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from landcover import models
from landcover.pipeline import NUM_CLASSES, ROOT
from landcover.remote import GPUS, remote_train
from landcover.train import data_hash, data_version, git, sha256, verify_data

EXPERIMENT = "landcover"
MODEL_NAME = "landcover-segmenter"
SCORE_BOUND = 0.005  # recorded vs re-measured development mIoU when logging
# Reproduction tolerance on development mIoU per model kind (README, "Reproduction").
TOLERANCE = {"rule": 0.01, "rf": 0.01, "unet": 0.02}
REQUIREMENTS = {
    "rule": ["numpy", "rasterio", "psycopg"],
    "rf": ["numpy", "rasterio", "psycopg", "scikit-learn", "scikit-image", "joblib"],
    "unet": ["numpy", "rasterio", "psycopg", "torch", "segmentation-models-pytorch", "timm"],
}


class Segmenter(mlflow.pyfunc.PythonModel):
    """predict: RGB array (height x width x 3, uint8) -> mask of class IDs (height x width)."""

    def load_context(self, context):
        with open(context.artifacts["run"]) as f:
            kind = json.load(f)["model"]
        self.predict_mask = models.load_predictor(kind, context.artifacts["model"])

    def predict(self, context, model_input, params=None):
        return self.predict_mask(np.asarray(model_input, dtype=np.uint8))


def log(result, tags=None):
    """Check the model file and its score, then create one run. Returns the run ID."""
    lineage = {"model", "data_version", "git_commit"}
    if lineage.intersection(tags or {}):
        raise SystemExit("--tag cannot override model, data_version or git_commit")
    result = Path(result)
    record = json.loads((result / "run.json").read_text())
    kind, model_file = record["model"], result / record["model_file"]
    if sha256(model_file) != record["model_sha256"]:
        raise SystemExit(f"{model_file}: SHA-256 differs from run.json; nothing logged")
    data = record["data_version"]
    if data_hash(git("show", f"{record['git_commit']}:data/raw.dvc")) != data:
        raise SystemExit("run.json data_version differs from data/raw.dvc at its git_commit")
    verify_data(ROOT, data)
    dev_tiles = models.load_tiles(record["batches"]["dev"])
    measured, _ = models.evaluate(models.load_predictor(kind, model_file), dev_tiles)
    recorded = record["scores"]["miou"]
    if abs(measured["miou"] - recorded) > SCORE_BOUND:
        raise SystemExit(f"development mIoU recorded {recorded:.4f}, measured here"
                         f" {measured['miou']:.4f}: differ by more than {SCORE_BOUND};"
                         " nothing logged")

    params = {**record["params"], "trained_on": record["device"]}
    params.update({key: record[key] for key in ("training_location", "gpu_name") if key in record})
    if "encoder_weights" in record:
        params["encoder_repo"] = record["encoder_weights"]["repo"]
        params["encoder_revision"] = record["encoder_weights"]["revision"]
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=result.name) as run:
        mlflow.set_tags({"model": kind, "data_version": record["data_version"],
                         "git_commit": record["git_commit"], **(tags or {})})
        mlflow.log_params(params)
        mlflow.log_metrics({f"dev_{k}": v for k, v in measured.items()})
        for epoch in record["history"]:
            mlflow.log_metrics({"epoch_train_loss": epoch["train_loss"],
                                "epoch_dev_miou": epoch["dev_miou"]}, step=epoch["epoch"])
        mlflow.log_artifact(str(result / "run.json"))
        mlflow.pyfunc.log_model(
            name="model",
            python_model=Segmenter(),
            artifacts={"model": str(model_file), "run": str(result / "run.json")},
            code_paths=[str(Path(models.__file__).parent)],
            pip_requirements=[f"{p}=={version(p)}" for p in REQUIREMENTS[kind]],
        )
    print(f"run {run.info.run_id}: development mIoU {measured['miou']:.4f}"
          f" (recorded {recorded:.4f})")
    return run.info.run_id


def register(run_id):
    """New version of the registered model with the run's lineage tags, loaded back to check it."""
    client = MlflowClient()
    run = client.get_run(run_id)
    tags = {k: run.data.tags[k] for k in ("data_version", "git_commit")}
    mv = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME, tags=tags)
    try:
        model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{mv.version}")
        rgb, _ = models.load_tiles(models.batches("dev"))[0]
        mask = np.asarray(model.predict(rgb))
        if mask.shape != rgb.shape[:2] or not np.isin(mask, range(NUM_CLASSES)).all():
            raise ValueError(f"version {mv.version} returned a {mask.shape} mask with values"
                             f" {np.unique(mask)[:10]}")
    except (Exception, KeyboardInterrupt):
        try:
            client.delete_model_version(MODEL_NAME, mv.version)
        except (MlflowException, OSError) as error:
            print(f"could not delete unverified version {mv.version}: {error}", file=sys.stderr)
        raise
    print(f"{MODEL_NAME} version {mv.version}: run {run_id}, data_version"
          f" {tags['data_version']}, git_commit {tags['git_commit']};"
          f" predicted a {mask.shape[0]}x{mask.shape[1]} mask")


def champion(version_):
    MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", version_)
    print(f"{MODEL_NAME}@champion -> version {version_}")


def check_data_version(dvc_file, tag):
    found = data_version(dvc_file)
    if found != tag:
        raise SystemExit(f"data/raw.dvc at the commit names {found}, the version's tag {tag}")


def compare(kind, original, reproduced):
    """Print both scores; exit non-zero when they differ by more than the kind's tolerance."""
    difference = abs(reproduced - original)
    print(f"development mIoU: original {original:.4f}, reproduced {reproduced:.4f},"
          f" difference {difference:.4f}, tolerance {TOLERANCE[kind]}")
    if difference > TOLERANCE[kind]:
        raise SystemExit("not reproduced: the difference exceeds the tolerance")


def reproduce(version_, gpu=None):
    """Train the version's run again from its commit, data version and parameters."""
    client = MlflowClient()
    mv = client.get_model_version(MODEL_NAME, version_)
    run = client.get_run(mv.run_id)
    commit, data = mv.tags["git_commit"], mv.tags["data_version"]
    with tempfile.TemporaryDirectory() as scratch:
        record = json.loads(Path(client.download_artifacts(mv.run_id, "run.json", scratch))
                            .read_text())
        kind, params = record["model"], record["params"]
        if record["git_commit"] != commit or record["data_version"] != data:
            raise SystemExit("registered lineage differs from the original run.json")
        if gpu and (kind != "unet" or record["device"] != "cuda"):
            raise SystemExit("--gpu is only for a recorded CUDA U-Net run")
        revision = record["encoder_weights"]["revision"] if kind == "unet" else None
        if revision and record["encoder_weights"]["repo"] != models.ENCODER_REPO:
            raise SystemExit("recorded U-Net encoder repository is unsupported")
        args = [f"--{k.replace('_', '-')}={v}" for k, v in params.items()]
        uv = ["uv", "run", "--locked", *(["--group", "nn"] if kind == "unet" else [])]
        tree = Path(scratch) / "tree"
        subprocess.run(["git", "worktree", "add", "--detach", str(tree), commit], cwd=ROOT,
                       check=True)
        try:
            check_data_version(tree / "data" / "raw.dvc", data)
            env = {**os.environ, "PYTHONPATH": "src"}
            subprocess.run([*uv, "dvc", "pull"], cwd=tree, env=env, check=True)
            if gpu:
                result = remote_train(commit, args, gpu, tree / "runs", revision)
            else:
                env_train = env
                if revision:
                    cache = str(Path(scratch) / "encoder-cache")
                    subprocess.run([*uv, "python", str(ROOT / "scripts" / "remote_train.py"),
                                    "--prepare-encoder", cache, revision], cwd=tree, env=env,
                                   check=True)
                    env_train = {**env, "HF_HUB_CACHE": cache, "HF_HUB_OFFLINE": "1"}
                subprocess.run([*uv, "python", "-m", "landcover.train", kind, *args], cwd=tree,
                               env=env_train, check=True)
                [record_file] = (tree / "runs").glob("*/run.json")
                result = record_file.parent
            repeated = json.loads((result / "run.json").read_text())
            if repeated["params"] != params or repeated["data_version"] != data:
                raise SystemExit("reproduction recorded different training parameters or data")
            if revision and repeated["encoder_weights"]["revision"] != revision:
                raise SystemExit("reproduction used a different encoder revision")
            verify_data(tree, data)
            # Use the historical logger and model code. Its log() has always returned the run ID.
            output = subprocess.check_output(
                [*uv, "python", "-c", ("import sys; from landcover.tracking import log; "
                 "print(log(sys.argv[1], {'reproduces': sys.argv[2]}))"), str(result), mv.run_id],
                cwd=tree, env=env, text=True,
            ).strip().splitlines()
            print("\n".join(output[:-1]))
            new_id = output[-1]
            if gpu:
                for key in ("training_location", "gpu_name"):
                    client.log_param(new_id, key, repeated[key])
        except subprocess.CalledProcessError as error:
            raise SystemExit(f"reproduction step failed: {error}") from None
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT,
                               check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                if not failed:
                    raise
                print(f"could not remove worktree {tree}: {error}", file=sys.stderr)
    new = client.get_run(new_id)
    print(f"version {version_}: run {mv.run_id} reproduced by run {new_id}")
    compare(kind, run.data.metrics["dev_miou"], new.data.metrics["dev_miou"])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.tracking")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("log")
    p.add_argument("result")
    p.add_argument("--tag", action="append", default=[], metavar="KEY=VALUE")
    sub.add_parser("register").add_argument("run_id")
    sub.add_parser("champion").add_argument("version")
    reproduce_parser = sub.add_parser("reproduce")
    reproduce_parser.add_argument("version")
    reproduce_parser.add_argument("--gpu", choices=GPUS)
    args = parser.parse_args(argv)
    if args.command == "log":
        tags = {}
        for tag in args.tag:
            key, separator, value = tag.partition("=")
            if not separator or not key.strip():
                p.error("--tag requires KEY=VALUE with a non-empty key")
            tags[key] = value
        log(args.result, tags)
    elif args.command == "register":
        register(args.run_id)
    elif args.command == "champion":
        champion(args.version)
    else:
        reproduce(args.version, args.gpu)


if __name__ == "__main__":
    sys.exit(main())
