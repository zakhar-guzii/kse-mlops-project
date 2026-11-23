"""Train one commit on Colab and retrieve its result without sending local data or credentials."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from landcover.models import MODEL_FILES
from landcover.pipeline import ROOT
from landcover.train import data_hash, git, sha256

GPUS = ("T4", "L4", "G4", "H100", "A100")


def remote_train(commit, args, gpu, runs, revision=None):
    if gpu not in GPUS:
        raise SystemExit(f"unsupported Colab GPU {gpu!r}; choose from {', '.join(GPUS)}")
    repository = git("config", "--get", "remote.origin.url")
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", repository):
        raise SystemExit("Colab requires a public HTTPS GitHub origin without credentials")
    data = data_hash(git("show", f"{commit}:data/raw.dvc"))
    session = f"landcover-{commit[:7]}-{uuid4().hex[:10]}"
    runs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runs, prefix=".download-") as scratch:
        archive = Path(scratch) / "result.zip"
        launcher = ROOT / "scripts" / "remote_train.py"
        pin = ["--pinned-encoder", revision] if revision else []
        command = ["colab", "run", "-s", session, "--gpu", gpu, "--keep", "--timeout", "0",
                   "--", str(launcher), "--gpu", gpu, *pin, repository, commit, *args]
        try:
            subprocess.run(command, check=True)
            subprocess.run(["colab", "download", "-s", session, "/content/result.zip",
                            str(archive)], check=True)
        finally:
            # A cleanup failure must not replace an error from training or download.
            failed = sys.exc_info()[0] is not None
            try:
                subprocess.run(["colab", "stop", "-s", session], check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                if not failed:
                    raise
                print(f"could not stop {session}: {error}", file=sys.stderr)

        staging = Path(scratch) / "result"
        staging.mkdir()
        with ZipFile(archive) as result:
            members = [entry for entry in result.infolist() if not entry.is_dir()]
            names = {Path(entry.filename).name: entry for entry in members}
            model_file = MODEL_FILES["unet"]
            if len(members) != 2 or names.keys() != {"run.json", model_file}:
                raise SystemExit("unexpected contents in Colab result archive")
            for filename, entry in names.items():
                with result.open(entry) as source, (staging / filename).open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        record = json.loads((staging / "run.json").read_text())
        expected = {"git_commit": commit, "data_version": data, "model": "unet",
                    "model_file": model_file, "device": "cuda", "training_location": "colab"}
        different = [key for key, value in expected.items() if record.get(key) != value]
        if different:
            raise SystemExit(f"Colab result has unexpected fields: {', '.join(different)}")
        if revision and record["encoder_weights"]["revision"] != revision:
            raise SystemExit("Colab result used a different encoder revision")
        if sha256(staging / model_file) != record["model_sha256"]:
            raise SystemExit("Colab result model hash differs from run.json")
        out = runs / f"unet-{commit[:7]}-{uuid4().hex}"
        staging.rename(out)
    print(f"Colab result: {out}")
    return out


def main(gpu, *args):
    from landcover.tracking import log

    if git("status", "--porcelain"):
        raise SystemExit("uncommitted changes: commit and push first")
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=ROOT, check=True)
    if not git("branch", "-r", "--list", "origin/*", "--contains", "HEAD"):
        raise SystemExit("HEAD is not on origin: push it first")
    commit = git("rev-parse", "HEAD")
    log(remote_train(commit, ["--device=cuda", *args], gpu, ROOT / "runs"))


if __name__ == "__main__":
    main(*sys.argv[1:])
