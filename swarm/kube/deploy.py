# swarm.kube.deploy
## @lineage: sphere.kube.deploy
## @lineage: debugger.sphere.kube.deploy
## @lineage: debug.sphere.kube.deploy
## @lineage: bound.sphere.kube.deploy
## @lineage: gov.sphere.kube.deploy
## @lineage: iso.sphere.kube.deploy
"""
@flow: Ψ(source) → Φ(artifact/image) → Φx(registry) → Ω(projection)
@topos: detect → build → oci_push → validate → transcribe → project
"""
import sys
import subprocess
import shutil
import re
from pathlib import Path
from typing import Optional
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self, resolve_path
from swarm.kube.transcript import TranscriptEngine, Projector
from hub.sphere.validator.compose import FlowValidator, SelfExtractor

log = get_emitter("kube.deploy")

def sanitize_id(name: str) -> str:
    """한글/특수문자 경로 문제를 방지하기 위한 ID 정규화"""
    clean = re.sub(r'[^a-z0-9\-]', '-', name.lower())
    return re.sub(r'-+', '-', clean).strip('-')

class OCIArtifactManager:
    """@role: 빌드된 결과물을 Zot(OCI)으로 전송"""
    REGISTRY = "host.minikube.internal:5000"

    @classmethod
    def build_and_push(cls, project_dir: Path, service_id: str):
        image_tag = f"{cls.REGISTRY}/{service_id}:latest"
        log.info(f"[Φ:OCI] 이미지 생성 및 Zot 푸시: {image_tag}")
        
        try:
            # 1. Docker Build
            subprocess.run(["docker", "build", "-t", image_tag, str(project_dir)], check=True)
            # 2. Zot Push
            subprocess.run(["docker", "push", image_tag], check=True)
            log.info(f"  [success] OCI Artifact 준비 완료.")
            return image_tag
        except subprocess.CalledProcessError as e:
            log.error(f"  [fail] 이미지 처리 실패: {e}")
            return None

class FinalDeployFlow:
    """@role: 전체 파이프라인 오케스트레이션"""
    def __init__(self, project_dir: str):
        self.project_path = Path(project_dir).resolve()
        self.validator = FlowValidator()
        self.engine = TranscriptEngine()

    def run(self, task: Optional[str] = None):
        log.info(f"[Ψ:init] 대상 프로젝트: {self.project_path.name}")

        # 1. 환경 및 런타임 빌드 (Gradle 등)
        if (self.project_path / "gradlew").exists():
            log.info("[Φ:build] Gradle 빌드 시작...")
            subprocess.run(["./gradlew", task or "build"], cwd=self.project_path, check=True)

        # 2. 설계도(.self.md) 탐색 및 식별자 확정
        md_files = list(self.project_path.glob("*.self.md"))
        if not md_files:
            log.error("[error] 배포 설계도(.self.md)를 찾을 수 없습니다.")
            return

        md_path = md_files[0]
        service_id = sanitize_id(self.project_path.name) # 기본값은 폴더명

        # 3. OCI 프로세스 (Zot 연동)
        if not OCIArtifactManager.build_and_push(self.project_path, service_id):
            return

        # 4. 검증 & 변환 (Validator + Transcript)
        log.info(f"[Φx:transcribe] 설계도 변환: {md_path.name}")
        # 내부적으로 KubeFlowValidator를 거쳐 K8s YAML 생성
        # 생성된 YAML의 이미지는 'host.minikube.internal:5000/...'를 바라봐야 함
        from phase.bind.res.transcript import run_pipeline
        run_pipeline(str(md_path)) 

        log.info(f"[Ω:finish] '{service_id}' 배포 사이클 완료.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Final Kube-Self Deployer")
    parser.add_argument("--dir", required=True, help="프로젝트 경로")
    parser.add_argument("--task", help="Gradle 태스크 (기본: build)")
    args = parser.parse_args()

    try:
        flow = FinalDeployFlow(args.dir)
        flow.run(args.task)
    except Exception as e:
        log.error(f"[X] 시스템 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()