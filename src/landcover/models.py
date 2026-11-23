"""Tile loader, the one evaluation and the three segmentation models.

Every model is used through a predictor: a function from an RGB array (height x width x 3,
uint8) to a mask of internal class IDs (height x width, uint8). torch is imported only by the
U-Net functions, so the rule and the forest run without it.
"""

import json
import sys

import numpy as np
import rasterio

from landcover.pipeline import BATCH_ROLES, IGNORE, LUT, NUM_CLASSES, batch_dir, extract

CLASS_NAMES = ["bareland", "rangeland", "developed", "road", "tree", "water", "agriculture",
               "building"]
SCORED = [0, 1, 4, 5, 6, 7]  # the classes crosswalk v1 can produce from FLAIR-HUB labels
MODEL_FILES = {"rule": "model.json", "rf": "model.joblib", "unet": "model.pt"}

ENCODER = "tu-tf_efficientnet_b4.in1k"
ENCODER_REPO = "timm/tf_efficientnet_b4.in1k"
ENCODER_REVISION = "c474abe5a8689bd017e9a50b41aa72ac253a63e1"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def batches(role):
    return [batch_id for batch_id, r in BATCH_ROLES.items() if r == role]


def load_tiles(batch_ids):
    """(rgb, internal label) per tile of the batches, in batch and tile-ID order."""
    tiles = []
    for batch_id in batch_ids:
        directory = batch_dir(batch_id)
        for tile_id in extract(directory):
            with rasterio.open(directory / "images" / f"{tile_id}.tif") as image:
                rgb = image.read([1, 2, 3]).transpose(1, 2, 0)
            with rasterio.open(directory / "labels" / f"{tile_id}.tif") as label:
                tiles.append((rgb, LUT[label.read(1)]))
    return tiles


# Evaluation


def confusion(label, prediction):
    """8x8 pixel counts, rows true class, columns predicted class; ignored pixels left out."""
    valid = label != IGNORE
    predicted = prediction[valid]
    # Class 2 is an unscored column, so out-of-range predictions still count against support.
    predicted = np.where((predicted >= 0) & (predicted < NUM_CLASSES), predicted, 2)
    index = label[valid].astype(np.int64) * NUM_CLASSES + predicted.astype(np.int64)
    return np.bincount(index, minlength=NUM_CLASSES**2).reshape(NUM_CLASSES, NUM_CLASSES)


def scores(matrix, ignored_px, total_px):
    """Six-class mean IoU and its parts. A prediction of class 2 or 3 is a miss of the true class."""
    support = matrix.sum(axis=1)
    missing = [CLASS_NAMES[c] for c in SCORED if support[c] == 0]
    if missing:
        raise ValueError(f"evaluation incomplete: no labelled pixel of {', '.join(missing)}")
    result = {}
    for c in SCORED:
        union = matrix[c, :].sum() + matrix[:, c].sum() - matrix[c, c]
        result[f"iou_{CLASS_NAMES[c]}"] = float(matrix[c, c] / union)
        result[f"px_{CLASS_NAMES[c]}"] = int(support[c])
    result["miou"] = float(np.mean([result[f"iou_{CLASS_NAMES[c]}"] for c in SCORED]))
    result["pixel_accuracy"] = float(np.trace(matrix) / matrix.sum())
    result["ignored_share"] = ignored_px / total_px
    return result


def evaluate(predict, tiles):
    """Score a predictor on tiles with one confusion matrix over all their labelled pixels."""
    return evaluate_masks((label, predict(rgb)) for rgb, label in tiles)


def evaluate_masks(pairs):
    """Score already computed (label, prediction) pairs the same way as a predictor."""
    matrix = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
    ignored = total = 0
    for label, prediction in pairs:
        matrix += confusion(label, prediction)
        ignored += int((label == IGNORE).sum())
        total += label.size
    return scores(matrix, ignored, total), matrix.tolist()


# Majority-class rule


def fit_rule(tiles):
    counts = sum(np.bincount(label.ravel(), minlength=256)[:NUM_CLASSES] for _, label in tiles)
    return int(np.argmax(counts))


def rule_predictor(class_id):
    return lambda rgb: np.full(rgb.shape[:2], class_id, dtype=np.uint8)


# Random forest on pixel texture features


def pixel_features(rgb):
    """Intensity, edge and texture features at scales 1, 2, 4 and 8 px: (pixels, features)."""
    from skimage.feature import multiscale_basic_features

    features = multiscale_basic_features(rgb, channel_axis=-1, sigma_min=1, sigma_max=8)
    return features.reshape(-1, features.shape[-1]).astype(np.float32)


def draw_pixels(labels, per_class, seed):
    """Sorted positions in the concatenated labels: at most per_class of each class, none ignored."""
    flat = np.concatenate([label.ravel() for label in labels])
    rng = np.random.default_rng(seed)
    drawn = []
    for c in range(NUM_CLASSES):
        positions = np.flatnonzero(flat == c)
        if len(positions) > per_class:
            positions = rng.choice(positions, per_class, replace=False)
        drawn.append(positions)
    return np.sort(np.concatenate(drawn))


def fit_forest(tiles, per_class, trees, depth, seed):
    from sklearn.ensemble import RandomForestClassifier

    positions = draw_pixels([label for _, label in tiles], per_class, seed)
    x, y, offset = [], [], 0
    for rgb, label in tiles:  # features of one tile at a time; only the drawn pixels are kept
        size = label.size
        local = positions[(positions >= offset) & (positions < offset + size)] - offset
        if len(local):
            x.append(pixel_features(rgb)[local])
            y.append(label.ravel()[local])
        offset += size
    forest = RandomForestClassifier(
        n_estimators=trees, max_depth=depth, random_state=seed, n_jobs=-1
    )
    return forest.fit(np.concatenate(x), np.concatenate(y))


def forest_predictor(forest):
    def predict(rgb):
        return forest.predict(pixel_features(rgb)).reshape(rgb.shape[:2]).astype(np.uint8)

    return predict


# U-Net


def pick_device():
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def build_unet(pretrained, revision=ENCODER_REVISION):
    import segmentation_models_pytorch as smp

    kwargs = {}
    if pretrained:
        kwargs["pretrained_cfg_overlay"] = {
            "source": "hf-hub", "hf_hub_id": f"{ENCODER_REPO}@{revision}",
        }
    return smp.Unet(encoder_name=ENCODER, encoder_weights="imagenet" if pretrained else None,
                    in_channels=3, classes=NUM_CLASSES, activation=None, **kwargs)


def to_tensor(rgbs, device):
    """uint8 (n, h, w, 3) -> normalised float (n, 3, h, w)."""
    import torch

    x = (np.asarray(rgbs, dtype=np.float32) / 255 - MEAN) / STD
    return torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2))).to(device)


def unet_predictor(model, device):
    import torch

    model.eval()

    def predict(rgb):
        h, w = rgb.shape[:2]
        padded = np.pad(rgb, ((0, -h % 32), (0, -w % 32), (0, 0)), mode="reflect")
        with torch.no_grad():
            logits = model(to_tensor(padded[np.newaxis], device))
        return logits.argmax(1)[0, :h, :w].cpu().numpy().astype(np.uint8)

    return predict


def augment(images, labels, rng):
    """The same random flip and quarter turn for each image and its mask."""
    out_images, out_labels = [], []
    for image, label in zip(images, labels):
        k, flip = rng.integers(4), rng.integers(2)
        image, label = np.rot90(image, k), np.rot90(label, k)
        if flip:
            image, label = image[:, ::-1], label[:, ::-1]
        out_images.append(image)
        out_labels.append(label)
    return np.stack(out_images), np.stack(out_labels)


def fit_unet(train_tiles, dev_tiles, epochs, batch_size, lr, weight_decay, seed, device,
             encoder_revision=ENCODER_REVISION):
    """Fixed epochs, last weights kept. History: per-epoch training loss and development mIoU."""
    import time

    import torch

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    images = np.stack([rgb for rgb, _ in train_tiles])
    labels = np.stack([label for _, label in train_tiles])
    model = build_unet(pretrained=True, revision=encoder_revision).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = torch.nn.CrossEntropyLoss(ignore_index=IGNORE)
    amp = device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    history = []
    for epoch in range(1, epochs + 1):
        start = time.monotonic()
        model.train()
        order = rng.permutation(len(images))
        total = 0.0
        for i in range(0, len(order), batch_size):
            batch = order[i : i + batch_size]
            x, y = augment(images[batch], labels[batch], rng)
            x = to_tensor(x, device)
            y = torch.from_numpy(y.astype(np.int64)).to(device)
            with torch.autocast(device_type=device, enabled=amp):
                loss = loss_fn(model(x), y)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total += loss.item() * len(batch)
        dev, _ = evaluate(unet_predictor(model, device), dev_tiles)
        history.append({"epoch": epoch, "train_loss": total / len(images),
                        "dev_miou": dev["miou"], "seconds": time.monotonic() - start})
        print(f"epoch {epoch}: loss {total / len(images):.4f}, dev mIoU {dev['miou']:.4f},"
              f" {history[-1]['seconds']:.0f} s", file=sys.stderr, flush=True)
    return model, history


# Saved models


def load_predictor(kind, path, device="cpu"):
    """The predictor of a saved model file; used by logging and by the stored MLflow model."""
    if kind == "rule":
        with open(path) as f:
            return rule_predictor(json.load(f)["class_id"])
    if kind == "rf":
        import joblib

        return forest_predictor(joblib.load(path))
    import torch

    model = build_unet(pretrained=False)
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    return unet_predictor(model.to(device), device)
