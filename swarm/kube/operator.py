# swarm.kube.operator
## @lineage: sphere.kube.operator
## @lineage: debugger.sphere.kube.operator
## @lineage: debug.sphere.kube.operator
## @lineage: bound.sphere.kube.operator
## @lineage: gov.sphere.kube.operator
## @lineage: iso.sphere.kube.operator
import kopf
import tempfile
import os
import shutil
import yaml
from pathlib import Path
from kubernetes import client, config
from watcher.plane.emitter import get_emitter
from nexus.swarm.kube.deploy import OCIArtifactManager
from nexus.swarm.kube.transcript import TranscriptEngine, Projector

log = get_emitter("kube.operator")

# 클러스터 내/외부 접속 설정
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

apps_api = client.AppsV1Api()

# -------------------------------------------------------------------
# [Phase 1: Genesis] 전체 파이프라인 구동 (Build -> Push -> Transcribe -> Project)
# -------------------------------------------------------------------
@kopf.on.create('configmaps', labels={'type': 'surgent-compose'})
def execute_deploy_pipeline(data, name, logger, **kwargs):
    """
    ConfigMap에 담긴 docker-compose.yml과 관련된 소스(로컬 환경이라 가정)를 기반으로
    이미지 빌드, Zot 푸시, K8s 매니페스트 변환 및 클러스터 적용을 수행합니다.
    """
    compose_yaml = data.get('docker-compose.yml')
    if not compose_yaml:
        logger.error("[Ψ:abort] ConfigMap 내에 'docker-compose.yml'이 없습니다.")
        return

    logger.info(f"[Ψ:Genesis] 위상 파이프라인 시작: {name}")

    # 이 오퍼레이터가 로컬 환경이나 볼륨 마운트를 통해 프로젝트 소스에 접근할 수 있다고 가정합니다.
    # 만약 소스 디렉토리가 명시되어 있지 않다면 임시 디렉토리를 사용해 Compose만 처리합니다.
    project_dir_str = data.get('project_dir') 
    
    if project_dir_str and Path(project_dir_str).exists():
        project_path = Path(project_dir_str).resolve()
        logger.info(f"[Φ:Build] OCI Artifact 빌드 파이프라인 연동: {project_path}")
        
        # 1. 빌드 및 Zot(OCI) 푸시
        image_tag = OCIArtifactManager.build_and_push(project_path, name)
        if not image_tag:
            logger.error("[Φ:abort] OCI 푸시 실패로 파이프라인을 중단합니다.")
            return

        # 2. compose_yaml 내의 이미지를 Zot 레지스트리 경로로 교체 (매우 중요)
        try:
            compose_data = yaml.safe_load(compose_yaml)
            for svc_name, svc_conf in compose_data.get('services', {}).items():
                if 'image' in svc_conf:
                    # 기본 이미지를 Zot에 푸시한 이미지로 덮어쓰기
                    svc_conf['image'] = image_tag 
            compose_yaml = yaml.dump(compose_data)
        except Exception as e:
            logger.warning(f"Compose 이미지 태그 치환 중 오류 발생: {e}")

    # 3. Transcribe (Compose -> K8s YAML)
    engine = TranscriptEngine()
    output_path = engine.transcribe(name, compose_yaml)
    
    if output_path:
        # 4. Project (kubectl apply)
        Projector.apply(output_path)
        logger.info(f"[Ω:finish] '{name}' 클러스터 투영 완료.")

# -------------------------------------------------------------------
# [Phase 2: Isorhesis] 상태 관측 및 동적 평형 댐핑 (기존 유지)
# -------------------------------------------------------------------
@kopf.timer('deployments', labels={'isorhesis.target': 'true'}, interval=15.0)
def isorhesis_observer(name, namespace, logger, **kwargs):
    logger.info(f"## @observer: Scanning Topology Tension for '{name}'")
    
    try:
        deployment = apps_api.read_namespaced_deployment(name, namespace)
    except client.exceptions.ApiException:
        return

    replicas = deployment.spec.replicas
    ready_replicas = deployment.status.ready_replicas or 0

    # 텐션 계산 로직
    tension = 100.0 if ready_replicas < replicas else 50.0

    if tension > 80.0:
        logger.warning(f"  [WAVEFORM] High Tension ({tension}%) - System drifting. Shifting Boundaries...")
        
        # 댐핑 패치: Replicas 확장
        new_replicas = replicas + 1
        patch = {"spec": {"replicas": new_replicas}}
        
        apps_api.patch_namespaced_deployment(name, namespace, patch)
        logger.info(f"  [SHIFT] Damping applied. Expanded boundary to {new_replicas} replicas.")
    else:
        logger.info(f"  [STABLE] Homeostasis maintained at {tension}%.")