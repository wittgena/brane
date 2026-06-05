# hub.manager
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Protocol
from watcher.plane.emitter import get_emitter
from arch.contract.exp.promise import future
from arch.contract.exp.atomic import sha256_file
from meta.xor.opt.optuna import OptunaOptimizer
from nexus.hub.gene.capsule import CapsuleBuilder, CapsuleContext 
from nexus.hub.gene.mutator import SwarmMutator
from nexus.hub.gene.sharder import DataSharder
from nexus.hub.gene.tracker import TribunalValidator, LineageTracker
from nexus.hub.comm.broker import RedisBroker, SporeManifest
from meta.xor.residue.drop import DeadDropper
from phase.bind.resolver import resolve_path

log = get_emitter("hub.manager")

@dataclass
class HubContext:
    """커맨드 실행에 필요한 공통 인프라 및 환경 변수를 캡슐화합니다."""
    db_uri: str = "sqlite:///nexus.db"
    dead_drop_uri: str = "s3://nexus-dead-drop/spores"
    redis_uri: str = "redis://localhost:6379/0"
    
    # [FIX] 캡슐화에 필요한 핵심 에셋 경로 추가
    ribos_script_path: Path = resolve_path("template") / "ribos.py"

class CommCommand(Protocol):
    """Command Pattern의 표준 인터페이스"""
    def execute(self, context: HubContext) -> None:
        ...

@dataclass
class ScatterCommand(CommCommand):
    """새로운 돌연변이 패킷을 캡슐화하여 배포하는 명령"""
    base_config: Path
    corpus: Path
    population: int = 5

    def execute(self, context: HubContext) -> None:
        log.info(f"Initiating Scatter phase for {self.population} spores...")
        
        optimizer = OptunaOptimizer(study_name="nexus_core", storage_uri=context.db_uri)
        broker = RedisBroker(context.redis_uri)
        drop = DeadDropper(context.dead_drop_uri)

        mutation_schema = {"learning_rate": {"type": "float", "low": 1e-5, "high": 1e-2, "log": True}} 
        mutator = SwarmMutator(optimizer, mutation_schema)

        config_data = json.loads(self.base_config.read_text(encoding="utf-8"))
        mutants = mutator.spawn_next_generation(config_data, self.population)
        shards = DataSharder().shard_corpus(self.corpus, self.population)

        # [FIX] CapsuleBuilder 초기화
        capsule_builder = CapsuleBuilder(CapsuleContext())

        for mutant_config, shard_path in zip(mutants, shards):
            gene_meta = mutant_config.pop("_gene_metadata", {})
            trial_id = gene_meta.get("trial_id")
            parent_hash = gene_meta.get("parent_hash")
            
            if trial_id is None:
                log.warning("Mutant missing trial_id, skipping.")
                continue

            # 1. Capsule 빌드 (run.sh, requirements.txt, config, 데이터 압축)
            capsule_tar_path = capsule_builder.build_capsule(
                trial_id=trial_id,
                config=mutant_config,
                corpus_path=shard_path,
                ribos_script_path=context.ribos_script_path,
                make_tarball=True
            )
            
            # 2. Data Plane (S3): 캡슐화된 단일 파일 업로드
            capsule_uri = drop.upload_file(capsule_tar_path, prefix=f"trials/{trial_id}/capsule.tar.gz")
            
            # 3. Control Plane (Redis): 매니페스트 생성 및 큐 푸시 (개별 config/shard 대신 capsule_uri 1개만 전달)
            manifest = SporeManifest(
                trial_id=trial_id,
                parent_hash=parent_hash,
                capsule_uri=capsule_uri,  # [FIX] Schema 변경 필요 (config_uri -> capsule_uri)
                status="PENDING"
            )
            broker.dispatch_task(manifest)
            log.info(f"Dispatched Spore (Trial ID: {trial_id}) to Redis Queue.")


@dataclass
class HarvestCommand(CommCommand):
    """Event-Driven 방식으로 워커 노드의 완료 메시지를 수신하여 후처리하는 명령"""
    inbox_dir: Path = Path("./inbox")

    def execute(self, context: HubContext) -> None:
        log.info("Initiating Event-Driven Harvest phase. Listening to Redis queue...")
        
        drop = DeadDropper(context.dead_drop_uri)
        optimizer = OptunaOptimizer(study_name="nexus_core", storage_uri=context.db_uri)
        broker = RedisBroker(context.redis_uri)
        tracker = LineageTracker(context.db_uri)
        validator = TribunalValidator(tracker)
        
        for raw_message, manifest in broker.consume_completed():
            trial_id = manifest.trial_id
            log.info(f"Received event for Trial {trial_id} [Status: {manifest.status}]")
            
            try:
                if manifest.status == "FAILED":
                    log.warning(f"Trial {trial_id} failed on worker. Reason: {manifest.error_message}")
                    optimizer.tell(trial_id, value=0.0, state="FAIL")
                
                else:
                    local_weight_path = drop.download(manifest.weight_uri, dest_dir=self.inbox_dir)
                    
                    if not validator.validate_weight_integrity(local_weight_path):
                        log.warning(f"Trial {trial_id} failed integrity check. Marking as FAIL.")
                        optimizer.tell(trial_id, value=0.0, state="FAIL")
                    
                    else:
                        log.info(f"Integrity passed for Trial {trial_id}. Running Sandbox Eval...")
                        score = validator.execute_blind_sandbox_test(local_weight_path)
                        
                        # [FIX] 올바른 파일 해시 계산 함수 사용
                        weight_hash = sha256_file(local_weight_path) 
                        tracker.record_birth(parent_id=manifest.parent_hash, child_id=weight_hash)
                        
                        optimizer.tell(trial_id, value=score)
                        log.info(f"Trial {trial_id} successfully harvested. Score: {score:.4f}")

                broker.ack_completed(trial_id)
            except Exception as e:
                log.error(f"Error processing Trial {trial_id}: {e}", exc_info=True)


@dataclass
class PruneCommand(CommCommand):
    """오래된 노드 또는 좀비 프로세스를 정리하는 명령"""
    older_than_days: int = 7

    @future("Delete heavy .safetensors but preserve lineage_manifest.json (Tombstoning).")
    def execute(self, context: HubContext) -> None:
        log.info("Initiating Prune phase...")
        broker = RedisBroker(context.redis_uri)
        optimizer = OptunaOptimizer(study_name="nexus_core", storage_uri=context.db_uri)

        zombie_trials = broker.find_zombie_trials()
        for trial_id in zombie_trials:
            log.warning(f"Zombie worker detected for Trial {trial_id}. Forcing FAIL state.")
            optimizer.tell(trial_id, value=0.0, state="FAIL")
            broker.cleanup_zombie_trial(trial_id)
        pass


class HubManager:
    """명령(Command)을 받아 실행하는 Invoker 객체."""
    def __init__(self, context: HubContext):
        self.context = context

    def submit_command(self, command: CommCommand) -> None:
        cmd_name = command.__class__.__name__
        log.info(f"[HubManager] Executing {cmd_name}...")
        try:
            command.execute(self.context)
            log.info(f"[HubManager] {cmd_name} completed successfully.")
        except Exception as e:
            log.error(f"[HubManager] {cmd_name} failed: {e}", exc_info=True)


if __name__ == "__main__":
    global_context = HubContext()
    manager = HubManager(global_context)
    
    cmd_scatter = ScatterCommand(
        base_config=Path("base.json"), 
        corpus=Path("data.jsonl"), 
        population=10
    )
    manager.submit_command(cmd_scatter)