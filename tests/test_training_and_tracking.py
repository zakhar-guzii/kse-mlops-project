import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import numpy as np
import pytest

from landcover import models, remote, tracking, train


def test_training_twice_keeps_both_completed_results(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(train, "ROOT", tmp_path)
    monkeypatch.setattr(train, "identity", lambda: ("0123456789", "sample.dir"))
    labels = np.array([models.SCORED], dtype=np.uint8)
    monkeypatch.setattr(models, "load_tiles", lambda _: [(np.zeros((1, 6, 3)), labels)])

    paths = []
    for _ in range(2):
        train.main(["rule"])
        paths.append(tmp_path / capsys.readouterr().out.strip())

    assert paths[0] != paths[1]
    for path in paths:
        record = json.loads((path / "run.json").read_text())
        assert record["batches"]["final"] == ["D073-2022"]
        assert record["model_sha256"] == train.sha256(path / "model.json")


def test_logging_rejects_a_result_whose_raw_files_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "ROOT", tmp_path)
    pointer = "outs:\n- md5: sample.dir\n  path: raw\n"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "raw.dvc").write_text(pointer)
    monkeypatch.setattr(tracking, "git", lambda *_: pointer)
    monkeypatch.setattr(train.subprocess, "run", lambda *_, **__: subprocess.CompletedProcess(
        ["dvc", "status"], 0, '{"data/raw.dvc": ["changed"]}', ""))
    artifact = tmp_path / "model.json"
    artifact.write_text('{"class_id": 2}')
    (tmp_path / "run.json").write_text(json.dumps({
        "model": "rule", "model_file": artifact.name, "model_sha256": train.sha256(artifact),
        "data_version": "sample.dir", "git_commit": "0123456789",
    }))

    with pytest.raises(SystemExit, match="data/raw does not match"):
        tracking.log(tmp_path)


def test_registration_removes_the_new_version_when_loading_fails(monkeypatch):
    client = Mock()
    client.get_run.return_value.data.tags = {"data_version": "sample.dir", "git_commit": "a"}
    monkeypatch.setattr(tracking, "MlflowClient", lambda: client)
    monkeypatch.setattr(tracking.mlflow, "register_model", lambda *_, **__: SimpleNamespace(
        version="17"))
    monkeypatch.setattr(tracking.mlflow.pyfunc, "load_model", Mock(
        side_effect=RuntimeError("artifact unavailable")))

    with pytest.raises(RuntimeError, match="artifact unavailable"):
        tracking.register("original-run")

    client.delete_model_version.assert_called_once_with(tracking.MODEL_NAME, "17")


def test_colab_receives_the_launchers_gpu_option(tmp_path, monkeypatch):
    commit = "0123456789"
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(b"test weights")
    metadata = {"git_commit": commit, "data_version": "raw.dir", "model": "unet",
                "model_file": "model.pt", "device": "cuda", "training_location": "colab",
                "model_sha256": train.sha256(model_file)}
    monkeypatch.setattr(remote, "git", lambda action, *_: (
        "https://github.com/reviewer/lab.git" if action == "config" else "md5: raw.dir\n"))

    def colab(command, *, check):
        if command[1] == "run":
            options, script = command[2:command.index("--")], command[command.index("--") + 1:]
            assert options[options.index("--gpu") + 1] == "L4"
            assert script[1:3] == ["--gpu", "L4"]
        if command[1] == "download":
            with ZipFile(command[-1], "w") as archive:
                archive.writestr("unet/run.json", json.dumps(metadata))
                archive.write(model_file, "unet/model.pt")

    monkeypatch.setattr(remote.subprocess, "run", colab)

    result = remote.remote_train(commit, ["--device=cuda"], "L4", tmp_path / "runs")

    assert json.loads((result / "run.json").read_text()) == metadata


def test_reproduction_validates_the_exact_historical_run_and_removes_its_worktree(monkeypatch):
    params = {"seed": 0}
    record = {"model": "rf", "params": params, "git_commit": "07c41af", "data_version": "raw.dir"}
    client = Mock()
    client.get_model_version.return_value = SimpleNamespace(run_id="original", tags={
        "git_commit": "07c41af", "data_version": "raw.dir",
    })

    def download(_run, _artifact, destination):
        path = Path(destination) / "run.json"
        path.write_text(json.dumps(record))
        return path

    client.download_artifacts.side_effect = download
    client.get_run.side_effect = lambda run_id: SimpleNamespace(
        data=SimpleNamespace(metrics={"dev_miou": {"original": 0.3, "exact-repeat": 0.3}[run_id]}),
    )
    monkeypatch.setattr(tracking, "MlflowClient", lambda: client)
    monkeypatch.setattr(tracking, "verify_data", lambda *_: None)
    worktrees = []

    def process(command, *, cwd, **_):
        if command[:3] == ["git", "worktree", "add"]:
            worktree = Path(command[4])
            (worktree / "data").mkdir(parents=True)
            (worktree / "data" / "raw.dvc").write_text("md5: raw.dir\n")
            worktrees.append(worktree)
        if "landcover.train" in command:
            assert cwd == worktrees[0]
            result = cwd / "runs" / "rf-07c41af"
            result.mkdir(parents=True)
            (result / "run.json").write_text(json.dumps(record))
        if command[:3] == ["git", "worktree", "remove"]:
            worktrees.remove(Path(command[-1]))

    monkeypatch.setattr(tracking.subprocess, "run", process)
    monkeypatch.setattr(tracking.subprocess, "check_output", lambda *_, **__: "exact-repeat\n")

    tracking.reproduce(1)

    assert not worktrees
    assert [call.args for call in client.get_run.call_args_list] == [("original",), ("exact-repeat",)]
