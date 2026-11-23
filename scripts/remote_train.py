"""Train the U-Net of one commit on a fresh machine; the only file `make train-remote` sends.

    python remote_train.py REPOSITORY COMMIT [TRAINING ARGUMENTS ...]

In the current directory: clone the repository, check out the commit, install the locked
dependencies with the nn group, fetch the raw data from its public source, fail unless it
hashes to data/raw.dvc, run the same training command as on the Mac, and zip the result
directory into result.zip. Standard library only. Exits with the code of the first failing step.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENCODER_REPO = "timm/tf_efficientnet_b4.in1k"


def prepare_encoder(cache, revision, command=(), cwd=None):
    """Map legacy timm's `main` request to the original snapshot in an isolated cache."""
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit("expected a full Hugging Face commit hash")
    weights = Path(subprocess.check_output(
        [*command, "hf", "download", ENCODER_REPO, "model.safetensors", "--revision", revision,
         "--cache-dir", str(cache), "--quiet"], cwd=cwd, text=True,
    ).strip())
    if not weights.is_file() or weights.parent.name != revision:
        raise SystemExit("downloaded encoder weights do not match the requested revision")
    ref = weights.parents[2] / "refs" / "main"
    ref.parent.mkdir(exist_ok=True)
    ref.write_text(revision)


def main(repository, commit, *train_args, pinned_encoder=None, gpu=None):
    work = Path.cwd() / "landcover"
    uv = ["uv", "run", "--locked", "--group", "nn"]
    steps = [
        (["git", "clone", "--quiet", repository, str(work)], None),
        (["git", "checkout", "--quiet", commit], work),
        (uv + ["python", "scripts/fetch_sample.py"], work),
        # as `make data`: hash the fetch into the DVC cache, fail unless it is the committed hash
        (uv + ["dvc", "commit", "-f", "-q", "data/raw.dvc"], work),
        (["git", "diff", "--exit-code", "--", "data/raw.dvc"], work),
    ]
    if shutil.which("uv") is None:
        steps.insert(0, ([sys.executable, "-m", "pip", "install", "--quiet", "uv==0.11.21"], None))
    env = {**os.environ, "PYTHONPATH": "src"}
    for command, cwd in steps:
        print("+", " ".join(command), flush=True)
        code = subprocess.run(command, cwd=cwd, env=env, check=False).returncode
        if code:
            return code
    if pinned_encoder:
        cache = Path.cwd() / "encoder-cache"
        prepare_encoder(cache, pinned_encoder, uv, work)
        env = {**env, "HF_HUB_CACHE": str(cache), "HF_HUB_OFFLINE": "1"}

    gpu_name = None
    if gpu:
        gpu_name = subprocess.check_output(
            [*uv, "python", "-c", "import torch; print(torch.cuda.get_device_name())"],
            cwd=work, env=env, text=True,
        ).strip()
        if gpu.upper() not in gpu_name.upper().split():
            raise SystemExit(f"requested GPU {gpu}, Colab allocated {gpu_name}")

    subprocess.run([*uv, "python", "-m", "landcover.train", "unet", *train_args],
                   cwd=work, env=env, check=True)
    [result] = (work / "runs").glob("*/run.json")
    if gpu:
        record = json.loads(result.read_text())
        if record["device"] != "cuda":
            raise SystemExit("remote training did not use CUDA")
        record.update(training_location="colab", gpu_name=gpu_name)
        result.write_text(json.dumps(record, indent=2) + "\n")
    archive = shutil.make_archive("result", "zip", result.parent.parent, result.parent.name)
    print(f"result: {archive}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--prepare-encoder"]:
        prepare_encoder(*sys.argv[2:])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--pinned-encoder")
        parser.add_argument("--gpu")
        parser.add_argument("repository")
        parser.add_argument("commit")
        parser.add_argument("train_args", nargs=argparse.REMAINDER)
        args = parser.parse_args()
        sys.exit(main(args.repository, args.commit, *args.train_args,
                      pinned_encoder=args.pinned_encoder, gpu=args.gpu))
