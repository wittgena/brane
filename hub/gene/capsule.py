# hub.gene.capsule
## @lineage: gov.hub.capsule
from __future__ import annotations
import os
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self, resolve_path
from arch.contract.exp.atomic import sha256_file, atomic_write_text, atomic_write_json, now_iso, now_compact

log = get_emitter("hub.capsule")

CAPSULE_SCHEMA_VERSION = 2
TRANSCRIPT_EXCLUDED: frozenset[str] = frozenset({"transcript.json"})

## Survival Kit (최후의 보루: 하드코딩 폴백)
FALLBACK_REQUIREMENTS = """\
torch>=2.0
unsloth
transformers
trl
peft
datasets
accelerate
bitsandbytes
safetensors
pyyaml
optuna
"""

FALLBACK_RUN_SH = """\
#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "=== ribos run ==="
if [[ "${SKIP_INSTALL:-0}" != "1" ]]; then
    pip install -q -r requirements.txt
fi

OUT_DIR="${OUT_DIR:-$HERE/_output}"
python ribos.py run --packet "$HERE" --out "$OUT_DIR"

echo "=== Done. Adapter at: $OUT_DIR ==="
"""

def get_template_content(filename: str, fallback_content: str, override_path: Path | None = None) -> str:
    target_path = resolve_template_path(filename, override_path)
    if target_path:
        log.debug(f"Resolved template {filename} at {target_path}")
        return target_path.read_text(encoding="utf-8")
        
    log.warning(f"Template {filename} not found. Using embedded fallback.")
    return fallback_content

def get_template_content(filename: str, fallback_content: str, override_path: Optional[Path] = None) -> str:
    target_path = resolve_template_path(filename, override_path)
    if target_path:
        log.debug(f"Resolved template {filename} at {target_path}")
        return target_path.read_text(encoding="utf-8")
        
    log.warning(f"Template {filename} not found. Using embedded fallback.")
    return fallback_content

@dataclass
class CapsuleContext:
    """패키징에 필요한 시스템 경로 및 환경 문맥"""
    out_dir: Path = field(default_factory=lambda: Path("./_capsules").resolve())
    
    # Transcript에 기록될 시스템 버전 정보
    nexus_version: str = "2.0.0"
    capsule_version: str = "2.0.0"
    ribos_version: str = "2.0.0"
    schema_version: int = 1


class CapsuleBuilder:
    """
    원격 워커(ribos)가 독립적으로 실행될 수 있도록
    데이터, 설정, 실행 템플릿을 하나의 밀봉된 캡슐(tar.gz)로 조립합니다.
    """
    def __init__(self, context: CapsuleContext):
        self.context = context
        self.context.out_dir.mkdir(parents=True, exist_ok=True)

    def build_capsule(
        self,
        trial_id: str | int,
        config: Dict[str, Any],
        corpus_path: Path,
        ribos_script_path: Path,
        prev_adapter_path: Optional[Path] = None,
        custom_requirements: Optional[Path] = None,
        custom_run_sh: Optional[Path] = None,
        make_tarball: bool = True
    ) -> Path:
        """
        캡슐 디렉토리를 조립하고, 원한다면 tar.gz로 압축하여 경로를 반환합니다.
        """
        corpus_sha = sha256_file(corpus_path)
        packet_id = f"trial-{trial_id}-{now_compact()}-{corpus_sha[:6]}"
        packet_dir = self.context.out_dir / f"capsule-{packet_id}"
        
        # 이전 작업의 잔재가 있다면 초기화
        if packet_dir.exists():
            shutil.rmtree(packet_dir)
        packet_dir.mkdir(parents=True)

        try:
            ## 핵심 로직 파일 및 데이터 복사
            shutil.copy2(ribos_script_path, packet_dir / "ribos.py")
            shutil.copy2(corpus_path, packet_dir / "corpus.jsonl")
            
            ## Dict 형태의 Config를 JSON 파일로 기록
            atomic_write_json(packet_dir / "config.json", config)
            
            if prev_adapter_path and prev_adapter_path.exists():
                shutil.copytree(prev_adapter_path, packet_dir / "prev_adapter", symlinks=False)

            ## 템플릿(생존 배낭) 시스템 가동
            req_content = get_template_content("requirements.txt", FALLBACK_REQUIREMENTS, custom_requirements)
            run_content = get_template_content("run.sh", FALLBACK_RUN_SH, custom_run_sh)
            atomic_write_text(packet_dir / "requirements.txt", req_content)
            atomic_write_text(packet_dir / "run.sh", run_content, mode=0o755)
            os.chmod(packet_dir / "run.sh", 0o755)

            ## 매니페스트 (Transcript) 작성 - 추적 및 무결성 검증용
            transcript = {
                "trial_id": trial_id,
                "packet_id": packet_id,
                "created_at": now_iso(),
                "capsule_schema": CAPSULE_SCHEMA_VERSION,
                "schema_version": self.context.schema_version,
                "nexus_version": self.context.nexus_version,
                "capsule_version": self.context.capsule_version,
                "ribos_version": self.context.ribos_version,
            }
            atomic_write_json(packet_dir / "transcript.json", transcript)

        except Exception as e:
            shutil.rmtree(packet_dir, ignore_errors=True)
            log.error(f"Failed to build capsule for trial {trial_id}: {e}")
            raise

        ## 압축 처리 (Data Plane 전송 최적화)
        if make_tarball:
            tar_path = packet_dir.with_suffix(".tar.gz")
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(packet_dir, arcname=packet_dir.name)
            
            shutil.rmtree(packet_dir)  # 원본 폴더 삭제 (용량 절약)
            log.info(f"Capsule packed successfully → {tar_path}")
            return tar_path

        log.info(f"Capsule directory created successfully → {packet_dir}")
        return packet_dir