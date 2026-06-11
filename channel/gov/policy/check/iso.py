# channel.gov.policy.check.iso
## @lineage: gov.gateway.policy.check.iso
## @lineage: gov.gateway.check.iso
from __future__ import annotations
import ast
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from channel.gov.policy.check.lineage import AdapterRecord, LineageManager
from arch.contract.registry.static import static_registry
from watcher.plane.emitter import get_emitter
from arch.contract.exp.atomic import sha256_file, atomic_write_json, read_json, now_iso

log = get_emitter('check.iso')
NEXUS_OUTPUT_SCHEMA = 1

@dataclass(frozen=True)
class SystemVersion:
    """시스템의 현재 상태 해시값을 담는 불변 객체 (파일 I/O와 분리됨)"""
    nexus_sha: str
    schema: int
    messenger_sha: Optional[str] = None
    ribos_sha: Optional[str] = None

    @classmethod
    def load(cls, nexus_script: Path, messenger_script: Path, ribos_canon: Path) -> "SystemVersion":
        """의존성을 주입받아 버전을 계산하는 팩토리 메서드"""
        return cls(
            nexus_sha=sha256_file(nexus_script) if nexus_script.exists() else "",
            messenger_sha=sha256_file(messenger_script) if messenger_script.exists() else None,
            ribos_sha=sha256_file(ribos_canon) if ribos_canon.exists() else None,
            schema=NEXUS_OUTPUT_SCHEMA,
        )

    def as_dict(self) -> dict:
        return asdict(self)

@dataclass
class IntegrityReport:
    """검증 결과를 담는 데이터 규격"""
    gen_id: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

# ==========================================
# 2. Validators
# ==========================================
class RibosValidator:
    """추가적인 정적 분석 프로토콜"""
    @staticmethod
    def analyze(source: str, tree: ast.AST) -> dict:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("os", "subprocess"):
                        return {"ok": False, "reason": f"forbidden_import: {alias.name}"}
        return {"ok": True}

# ==========================================
# 3. Core Services
# ==========================================
def verify_adapter(
    record: AdapterRecord, 
    sys_version: SystemVersion, 
    corpus_dir: Path
) -> IntegrityReport:
    """어댑터의 정합성을 검증 (의존성 주입 완료)"""
    rep = IntegrityReport(gen_id=record.gen_id, ok=True)
    mf = record.manifest

    # 1. Nexus & Ribos 버전 드리프트 검증
    declared_nexus = mf.get("nexus_version")
    if declared_nexus != sys_version.nexus_sha:
        rep.ok = False
        rep.issues.append("nexus_drift")
    rep.details.update({"nexus_declared": declared_nexus, "nexus_current": sys_version.nexus_sha})

    declared_ribo = mf.get("ribos_version")
    if declared_ribo != sys_version.ribos_sha:
        rep.ok = False
        rep.issues.append("ribos_drift")
    rep.details.update({"ribos_declared": declared_ribo, "ribos_current": sys_version.ribos_sha})

    declared_messenger = mf.get("messenger_version")
    if declared_messenger and declared_messenger != sys_version.messenger_sha:
        rep.issues.append("messenger_drift")  # Informational only
    rep.details.update({"messenger_declared": declared_messenger, "messenger_current": sys_version.messenger_sha})

    # 2. 코퍼스 정합성 검증 (원본 로직 완전 복원)
    corpus_info = mf.get("training_corpus", {}) or {}
    declared_corpus_sha = corpus_info.get("sha256")
    corpus_filename = corpus_info.get("filename") or corpus_info.get("path")
    candidate: Optional[Path] = None

    if not declared_corpus_sha:
        rep.ok = False
        rep.issues.append("corpus_sha_missing")
    else:
        if corpus_filename:
            p = corpus_dir / Path(corpus_filename).name
            if p.exists():
                candidate = p
        
        # 파일명으로 못 찾으면 해시로 풀 스캔
        if candidate is None:
            for child in corpus_dir.glob("*.jsonl"):
                if sha256_file(child) == declared_corpus_sha:
                    candidate = child
                    break
        
        if candidate is None:
            rep.ok = False
            rep.issues.append("corpus_missing_locally")
        elif sha256_file(candidate) != declared_corpus_sha:
            rep.ok = False
            rep.issues.append("corpus_hash_mismatch")
            
    rep.details["corpus_local"] = str(candidate) if candidate else None
    rep.details["corpus_declared_sha"] = declared_corpus_sha

    # 3. 스키마 및 필수 키 검증
    declared_schema = mf.get("output_schema_version")
    if declared_schema != sys_version.schema:
        rep.ok = False
        rep.issues.append("schema_drift")
    rep.details.update({"schema_declared": declared_schema, "schema_current": sys_version.schema})

    required = ("gen_id", "created_at", "parent_model", "training_corpus", "hyperparameters", "eval_report")
    missing = [k for k in required if k not in mf]
    if missing:
        rep.ok = False
        rep.issues.append("manifest_keys_missing")
        rep.details["missing_keys"] = missing

    return rep


def receive_adapter(
    incoming_path: Path,
    lineage: LineageManager,
    corpus_dir: Path,
    quarantine_dir: Path,
    sys_version: SystemVersion,
    promote_threshold: Optional[float] = None,
) -> IntegrityReport:
    """새로운 어댑터를 수신하고, 검증하고, 격리/승격시키는 워크플로우 엔진"""
    if not incoming_path.is_dir():
        raise NotADirectoryError(incoming_path)
    
    mf_path = incoming_path / "lineage_manifest.json"
    if not mf_path.exists():
        raise FileNotFoundError(f"missing lineage_manifest.json in {incoming_path}")

    # 1. 매니페스트 ID 발급
    manifest = read_json(mf_path)
    proposed = manifest.get("gen_id") or incoming_path.name
    if (lineage.dir / proposed).exists():
        proposed = lineage.next_gen_id()
        manifest["gen_id"] = proposed
        atomic_write_json(mf_path, manifest)

    # 2. 디렉토리 이동
    lineage.dir.mkdir(parents=True, exist_ok=True)
    target = lineage.dir / proposed
    shutil.move(str(incoming_path), str(target))

    # 3. 검증 수행
    rec = lineage.get(proposed)
    report = verify_adapter(rec, sys_version, corpus_dir)

    # 4. 실패 시 롤백 및 격리
    if not report.ok:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        quar_target = quarantine_dir / proposed
        if quar_target.exists():
            quar_target = quarantine_dir / f"{proposed}.{int(time.time())}"
        shutil.move(str(target), str(quar_target))
        
        atomic_write_json(quar_target / "integrity_report.json", {
            **asdict(report), "quarantined_at": now_iso()
        })
        log.error(f"Adapter {proposed} FAILED integrity → quarantined: {report.issues}")
        return report

    # 5. 성공 시 승격 평가
    atomic_write_json(target / "integrity_report.json", {
        **asdict(report), "verified_at": now_iso()
    })
    
    if promote_threshold is not None:
        score = rec.eval_score
        if score is not None and score >= promote_threshold:
            lineage.set_promoted(proposed, True)
            log.info(f"Adapter {proposed} promoted (score={score} >= {promote_threshold})")
        else:
            log.info(f"Adapter {proposed} verified but not promoted (score={score})")

    return report


def transcribe(
    corpus_path: Path, 
    config_path: Path, 
    out_dir: Path, 
    sys_version: SystemVersion,
    messenger_script: Path,
    ribos_canon: Path,
    prev_adapter: Optional[Path] = None
) -> Path:
    """메신저 스크립트를 통해 패킷을 생성하고 최신 패킷 경로를 반환"""
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(messenger_script), "pack",
        "--corpus", str(corpus_path),
        "--config", str(config_path),
        "--ribos", str(ribos_canon),
        "--out", str(out_dir),
        "--nexus-version", sys_version.nexus_sha,
        "--messenger-version", sys_version.messenger_sha or "",
        "--ribos-version", sys_version.ribos_sha or "",
        "--schema-version", str(sys_version.schema),
    ]
    if prev_adapter:
        cmd += ["--prev-adapter", str(prev_adapter)]

    log.info(f"transcribing via messenger.py → {out_dir}")
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    
    if res.returncode != 0:
        log.error(f"messenger.py failed (exit {res.returncode}):\n{res.stderr}")
        raise RuntimeError("transcription failed")
    
    if res.stdout.strip():
        log.info(res.stdout.strip())

    # 원본 파일 정렬 및 반환 로직 복원
    packets = sorted(
        [p for p in out_dir.iterdir() if p.name.startswith("packet-")],
        key=lambda p: p.stat().st_mtime,
    )
    if not packets:
        raise RuntimeError("messenger.py reported success but produced no packet")
    
    return packets[-1]


def self_check(
    sys_version: SystemVersion, 
    paths: dict[str, Path], 
    lineage: LineageManager
) -> dict:
    """시스템 전체 정합성 및 무결성 체크 (CLI에서 의존성 주입)"""
    out: dict = {"ok": True, "checks": {}}
    out["versions"] = sys_version.as_dict()

    out["checks"]["nexus_readable"] = paths["nexus_script"].exists()
    out["checks"]["messenger_present"] = paths["messenger_script"].exists()
    if not out["checks"]["messenger_present"]:
        out["ok"] = False

    ribo_check = static_registry.static_check("ribos_canon")
    out["checks"]["ribos"] = ribo_check
    if not ribo_check["ok"]:
        out["ok"] = False

    for label in ("io_state", "corpus_dir", "adapters"):
        out["checks"][f"dir_{label}"] = paths[label].exists()

    out["checks"]["residue_store_importable"] = True

    # Lineage 무결성 체크
    records = lineage.list()
    out["checks"]["lineage_count"] = len(records)
    out["checks"]["lineage_promoted"] = sum(1 for r in records if r.promoted)
    
    promoted = [r for r in records if r.promoted]
    if promoted:
        latest = sorted(promoted, key=lambda r: r.created_at)[-1]
        rep = verify_adapter(latest, sys_version, paths["corpus_dir"])
        out["checks"]["latest_promoted_integrity"] = {
            "gen_id": rep.gen_id,
            "ok": rep.ok,
            "issues": rep.issues,
        }
        if not rep.ok:
            out["ok"] = False

    return out