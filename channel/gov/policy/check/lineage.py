# channel.gov.policy.check.lineage
## @lineage: gov.gateway.policy.check.lineage
## @lineage: gov.gateway.check.lineage
from __future__ import annotations
import argparse
import calendar
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from watcher.plane.emitter import get_emitter

log = get_emitter("check.lineage")

@dataclass
class AdapterRecord:
    gen_id: str
    path: Path
    manifest: dict

    @property
    def created_at(self) -> str:
        return self.manifest.get("created_at", "")

    @property
    def promoted(self) -> bool:
        return bool(self.manifest.get("promoted", False))

    @property
    def eval_score(self) -> Optional[float]:
        rep = self.manifest.get("eval_report") or {}
        return rep.get("score")

    @property
    def parent_adapter(self) -> Optional[str]:
        return self.manifest.get("parent_adapter")

class LineageManager:
    def __init__(self, adapters_dir: Path):
        self.dir = adapters_dir

    def list(self) -> list[AdapterRecord]:
        records: list[AdapterRecord] = []
        if not self.dir.exists():
            return records
        for child in sorted(self.dir.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            mf = child / "lineage_manifest.json"
            if not mf.exists():
                continue
            try:
                records.append(AdapterRecord(gen_id=child.name, path=child, manifest=read_json(mf)))
            except Exception as e:
                log.warning(f"unreadable manifest in {child}: {e}")
        return records

    def get(self, gen_id: str) -> AdapterRecord:
        path = self.dir / gen_id
        mf = path / "lineage_manifest.json"
        if not mf.exists():
            raise FileNotFoundError(f"no manifest for {gen_id}")
        return AdapterRecord(gen_id=gen_id, path=path, manifest=read_json(mf))

    def next_gen_id(self) -> str:
        nums = []
        for r in self.list():
            if r.gen_id.startswith("gen-"):
                try:
                    nums.append(int(r.gen_id.split("-", 1)[1]))
                except ValueError:
                    continue
        return f"gen-{(max(nums) + 1) if nums else 1:04d}"

    def set_promoted(self, gen_id: str, promoted: bool) -> None:
        rec = self.get(gen_id)
        rec.manifest["promoted"] = promoted
        rec.manifest["promoted_at"] = now_iso() if promoted else None
        atomic_write_json(rec.path / "lineage_manifest.json", rec.manifest)

    def update_latest_symlink(self, gen_id: str, link_path: Path) -> None:
        target = self.dir / gen_id
        if not target.exists():
            raise FileNotFoundError(target)
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
        link_path.symlink_to(target.name)  # relative symlink

    def current_latest(self, link_path: Path) -> Optional[str]:
        if not link_path.is_symlink():
            return None
        return os.readlink(link_path)

    def previous_promoted(self, link_path: Path) -> Optional[AdapterRecord]:
        current = self.current_latest(link_path)
        promoted = [r for r in self.list() if r.promoted and r.gen_id != current]
        if not promoted:
            return None
        return sorted(promoted, key=lambda r: r.created_at)[-1]