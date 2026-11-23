"""Fetch the course sample of FLAIR-HUB into data/raw/<batch_id>/{images,labels}/<tile_id>.tif.

For each domain, read the listings of the image and label ZIPs over HTTP range requests,
keep the patches present in both, sort them by tile ID and take every k-th so that
PAIRS_PER_BATCH pairs remain. Files are written unmodified; existing files are skipped,
and a domain that already holds all its pairs is not requested at all.
The result is checked as a whole by `make data` against the DVC hash in data/raw.dvc.
"""

import io
import urllib.request
import zipfile
from pathlib import Path

REVISION = "37d52ec88c72b5961de6ba3a6fae67686b0c2355"  # IGNF/FLAIR-HUB commit, 2026-11-08
BASE_URL = f"https://huggingface.co/datasets/IGNF/FLAIR-HUB/resolve/{REVISION}/data"
DOMAINS = ["D080-2017", "D033-2018", "D065-2019", "D045-2020", "D017-2021", "D073-2022"]
PAIRS_PER_BATCH = 16
MODALITIES = {"images": "AERIAL_RGBI", "labels": "AERIAL_LABEL-COSIA"}
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, enough for zipfile."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
            self.size = int(r.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence] + offset
        return self.pos

    def readinto(self, buffer):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        request = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(request) as r:
            data = r.read()
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


def open_zip(domain, modality):
    url = f"{BASE_URL}/{domain}_{modality}.zip"
    return zipfile.ZipFile(io.BufferedReader(HttpRangeFile(url), buffer_size=1 << 20))


def members_by_tile(archive, domain, modality):
    prefix = f"{domain}_{modality}_"
    return {
        Path(info.filename).name.removeprefix(prefix).removesuffix(".tif"): info
        for info in archive.infolist()
        if info.filename.endswith(".tif")
    }


def fetch_domain(domain):
    if all(
        len(list((RAW / domain / kind).glob("*.tif"))) == PAIRS_PER_BATCH for kind in MODALITIES
    ):
        print(f"{domain}: {PAIRS_PER_BATCH} pairs already present, nothing downloaded")
        return
    archives = {kind: open_zip(domain, modality) for kind, modality in MODALITIES.items()}
    members = {
        kind: members_by_tile(archives[kind], domain, MODALITIES[kind]) for kind in MODALITIES
    }
    paired = sorted(members["images"].keys() & members["labels"].keys())
    step = len(paired) // PAIRS_PER_BATCH
    sample = paired[::step][:PAIRS_PER_BATCH]
    downloaded = 0
    for tile_id in sample:
        for kind, archive in archives.items():
            target = RAW / domain / kind / f"{tile_id}.tif"
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".part")
            partial.write_bytes(archive.read(members[kind][tile_id]))
            partial.rename(target)
            downloaded += 1
    print(f"{domain}: {len(sample)} pairs from {len(paired)}, {downloaded} files downloaded")


if __name__ == "__main__":
    for domain in DOMAINS:
        fetch_domain(domain)
