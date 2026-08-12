from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

USER_AGENT = "Radar-SII/0.1 (+GitHub OSINT research; public SII data)"


@dataclass
class Snapshot:
    source_id: str
    url: str
    path: str
    sha256: str
    bytes: int
    downloaded_at: str
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def http_metadata(url: str, timeout: int = 45) -> dict:
    r = requests.head(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return {
        "url": r.url,
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
        "content_length": r.headers.get("Content-Length"),
        "content_type": r.headers.get("Content-Type"),
    }


def download(source_id: str, url: str, target_dir: Path, timeout: int = 180) -> Snapshot:
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?", 1)[0]).suffix or ".bin"
    path = target_dir / f"{source_id}{suffix}"
    sha = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                sha.update(chunk)
                size += len(chunk)
        return Snapshot(
            source_id=source_id,
            url=r.url,
            path=str(path),
            sha256=sha.hexdigest(),
            bytes=size,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
            etag=r.headers.get("ETag"),
            last_modified=r.headers.get("Last-Modified"),
            content_type=r.headers.get("Content-Type"),
        )


def extract_primary_text(snapshot: Snapshot, target_dir: Path) -> Path:
    source = Path(snapshot.path)
    target_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            candidates = [i for i in zf.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in {".txt", ".csv", ".tsv"}]
            if not candidates:
                candidates = [i for i in zf.infolist() if not i.is_dir()]
            if not candidates:
                raise ValueError(f"ZIP vacío: {source}")
            member = max(candidates, key=lambda i: i.file_size)
            out = target_dir / f"{snapshot.source_id}_{Path(member.filename).name}"
            with zf.open(member) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            return out
    out = target_dir / source.name
    shutil.copy2(source, out)
    return out


def write_manifest(snapshots: list[Snapshot], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([s.to_dict() for s in snapshots], ensure_ascii=False, indent=2), encoding="utf-8")
