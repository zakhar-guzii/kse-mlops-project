import numpy as np
import pytest

from landcover import models, pipeline

I = pipeline.IGNORE


def tile(label):
    label = np.array(label, dtype=np.uint8)
    return np.zeros((*label.shape, 3), dtype=np.uint8), label


def test_every_batch_has_one_role():
    assert list(pipeline.BATCH_ROLES) == list(pipeline.BATCHES)
    assert models.batches("dev") == ["D017-2021"]
    assert "D073-2022" not in models.batches("train") + models.batches("dev")


def all_scored_label():
    # one pixel of each scored class, two ignored pixels
    return [[0, 1, 4, 5], [6, 7, I, I]]


def test_confusion_matrix_by_hand():
    label = np.array(all_scored_label(), dtype=np.uint8)
    prediction = np.array([[0, 1, 4, 4], [6, 7, 3, 5]], dtype=np.uint8)
    result, matrix = models.evaluate(lambda rgb: prediction, [tile(label)])
    expected = np.zeros((8, 8), dtype=int)
    for true, pred in [(0, 0), (1, 1), (4, 4), (5, 4), (6, 6), (7, 7)]:
        expected[true, pred] += 1
    assert matrix == expected.tolist()
    # tree: TP 1, FP 1 (the water pixel), FN 0 -> 1/2; water: TP 0 -> 0; the rest 1
    assert result["iou_tree"] == 0.5
    assert result["iou_water"] == 0.0
    assert result["miou"] == pytest.approx((4 + 0.5) / 6)
    assert result["pixel_accuracy"] == 5 / 6
    assert result["px_water"] == 1
    assert result["ignored_share"] == 2 / 8


def test_ignored_pixels_change_no_score():
    label = all_scored_label()
    good = models.evaluate(lambda rgb: np.array(label, dtype=np.uint8) % 8, [tile(label)])[0]
    # whatever is predicted on the ignored pixels
    bad = models.evaluate(lambda rgb: np.array([[0, 1, 4, 5], [6, 7, 3, 2]], np.uint8),
                          [tile(label)])[0]
    assert good == bad
    assert good["miou"] == 1.0


@pytest.mark.parametrize("unscored", [2, 8, 64, -1])
def test_unscored_class_prediction_is_a_miss(unscored):
    label = all_scored_label()
    prediction = np.array([[unscored, 1, 4, 5], [6, 7, 0, 0]])
    result = models.evaluate(lambda rgb: prediction, [tile(label)])[0]
    assert result["iou_bareland"] == 0.0
    assert result["pixel_accuracy"] == 5 / 6


def test_scored_class_without_pixels_is_named():
    label = [[0, 1, 4, 5], [6, I, I, I]]  # no building
    with pytest.raises(ValueError, match="incomplete.*building"):
        models.evaluate(lambda rgb: np.zeros((2, 4), np.uint8), [tile(label)])


def test_rule_predicts_most_frequent_training_class_everywhere():
    train = [tile([[6, 6, 1], [I, I, I]]), tile([[6, 0, 1], [I, I, I]])]
    class_id = models.fit_rule(train)
    assert class_id == 6
    prediction = models.rule_predictor(class_id)(np.zeros((5, 7, 3), np.uint8))
    assert prediction.shape == (5, 7)
    assert (prediction == 6).all()


def test_pixel_draw_caps_classes_and_skips_ignored():
    rng = np.random.default_rng(1)
    labels = [rng.choice(np.array([0, 1, 6, I], np.uint8), size=(32, 32), p=[0.1, 0.2, 0.3, 0.4])
              for _ in range(3)]
    positions = models.draw_pixels(labels, per_class=50, seed=0)
    drawn = np.concatenate([label.ravel() for label in labels])[positions]
    assert I not in drawn
    counts = np.bincount(drawn, minlength=8)
    assert counts.max() <= 50
    assert counts[0] == counts[1] == counts[6] == 50
    assert len(np.unique(positions)) == len(positions)
    assert np.array_equal(positions, models.draw_pixels(labels, per_class=50, seed=0))
    assert not np.array_equal(positions, models.draw_pixels(labels, per_class=50, seed=1))


def test_rare_class_keeps_all_its_pixels():
    labels = [np.array([[7, 0, 0, 0]], np.uint8)]
    drawn = labels[0].ravel()[models.draw_pixels(labels, per_class=2, seed=0)]
    assert sorted(drawn.tolist()) == [0, 0, 7]


def test_reproduction_outside_tolerance_fails(capsys):
    from landcover import tracking

    tracking.compare("rf", 0.1478, 0.1478 + tracking.TOLERANCE["rf"] / 2)
    with pytest.raises(SystemExit, match="exceeds the tolerance"):
        tracking.compare("rf", 0.1478, 0.1478 + 2 * tracking.TOLERANCE["rf"])
    assert "original 0.1478" in capsys.readouterr().out


def test_reproduction_with_another_data_version_fails(tmp_path):
    from landcover import tracking

    dvc_file = tmp_path / "raw.dvc"
    dvc_file.write_text("outs:\n- md5: aaa.dir\n  path: raw\n")
    tracking.check_data_version(dvc_file, "aaa.dir")
    with pytest.raises(SystemExit, match="bbb.dir"):
        tracking.check_data_version(dvc_file, "bbb.dir")
