# swarm.kube.transcript
## @lineage: sphere.kube.transcript
## @lineage: debugger.sphere.kube.transcript
## @lineage: debug.sphere.kube.transcript
## @lineage: bound.sphere.kube.transcript
## @lineage: gov.sphere.kube.transcript
## @lineage: iso.sphere.kube.transcript
"""@flow: Φ(config surface) → Ψ(transcription) → Ψ′(k8s projection)"""
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path

log = get_emitter("kube.transcript")

def sanitize_name(name: str) -> str:
    """한글 및 특수문자를 제거하고 시스템 안전한 이름으로 변환"""
    name = name.lower()
    name = re.sub(r'[^a-z0-9\-]', '-', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name or "unnamed-service"

class TranscriptEngine:
    def __init__(self):
        self.outlet_root = resolve_path("k8s")

    def transcribe(self, service_id: str, compose_content: str) -> Optional[Path]:
        target_dir = self.outlet_root / service_id
        target_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"[Ψ:transcribe] '{service_id}' Compose -> K8s 변환 시작")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
            tmp.write(compose_content)
            tmp_path = tmp.name

        try:
            subprocess.run(
                ["kompose", "convert", "-f", tmp_path, "--out", str(target_dir)],
                check=True, capture_output=True, text=True
            )
            log.info(f"  [success] K8s 매니페스트 생성 완료 -> {target_dir}")
            return target_dir
        except subprocess.CalledProcessError as e:
            log.error(f"  [fail] Kompose 변환 오류:\n{e.stderr}")
            return None
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)

class Projector:
    @staticmethod
    def apply(manifest_dir: Path):
        log.info(f"[Ψ':project] 클러스터 반영 시작: {manifest_dir.name}")
        try:
            subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_dir)],
                check=True, capture_output=True, text=True
            )
            log.info(f"  [success] 클러스터 투영 완료.")
        except subprocess.CalledProcessError as e:
            log.error(f"  [fail] kubectl apply 오류:\n{e.stderr.strip()}")