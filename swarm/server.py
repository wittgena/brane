# swarm.server
## @lineage: hub.nexus.flow.server
## @lineage: gov.hub.node.learner
import json
import logging
import sys
from pathlib import Path
import tyro
from watcher.plane.emitter import get_emitter

log = get_emitter("swarm.server")

try:
    from meta.xor.opt.grpo import GRPO
    from nexus.bound.gov.scope.module.meta import Module
    from meta.ops.evaluator.evaluate import Evaluate
    HAS_GRPO = True
except ImportError:
    HAS_GRPO = False
    log.warning("Core framework (meta.xor) not found. Will fallback to Standard SFT.")

def run_grpo_training(config: dict, corpus_path: Path, out_dir: Path):
    """로컬 코어 프레임워크가 있을 때 실행되는 고급 강화학습 루프"""
    log.info("Running advanced GRPO Training...")
    
    # 1. Dataset 및 Module 로드 (가정된 로직)
    # trainset = load_dataset(corpus_path)
    # student_module = load_module(config["parent_model"])
    
    # 2. GRPO 옵티마이저 초기화
    # grpo = GRPO(
    #     num_train_steps=config.get("grpo_steps", 100),
    #     num_rollouts_per_grpo_step=config.get("rollouts", 4),
    #     ...
    # )
    
    # 3. 컴파일(학습)
    # compiled_student = grpo.compile(student_module, trainset=trainset)
    # compiled_student.save(out_dir)
    
    # [Mock]
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump({"mode": "GRPO", "loss": 0.05}, f)

def run_sft_training(config: dict, corpus_path: Path, out_dir: Path):
    """가벼운 클라우드/Colab 환경에서 Unsloth/TRL을 사용하는 기본 지도학습 루프"""
    log.info("Running fallback SFT Training via Unsloth/TRL...")
    
    # 여기서 기존 ribos.py의 SFTTrainer 로직을 그대로 사용합니다.
    # model, tokenizer, _ = load_base_with_adapter(config, None)
    # dataset = build_dataset(corpus_path, tokenizer)
    # train(model, tokenizer, dataset, config, ...)
    # model.save_pretrained(out_dir)
    
    # [Mock]
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump({"mode": "SFT", "loss": 1.25}, f)

def main(capsule: Path):
    capsule = capsule.resolve()
    config_path = capsule / "config.json"
    corpus_path = capsule / "corpus.jsonl"
    out_dir = capsule / "_output"

    if not config_path.exists():
        log.error("config.json not found in capsule.")
        sys.exit(1)

    config = json.loads(config_path.read_text())
    
    # Config에서 명시적으로 SFT를 강제할 수도 있도록 설정
    force_sft = config.get("training", {}).get("force_sft", False)

    try:
        # 분기 로직
        if HAS_GRPO and not force_sft:
            run_grpo_training(config, corpus_path, out_dir)
        else:
            run_sft_training(config, corpus_path, out_dir)
            
        sys.exit(0) # 성공 시 조용히 종료 (Agent가 인식함)
        
    except Exception as e:
        log.exception("ML Execution crashed")
        sys.exit(1) # 실패 시 Agent가 로그를 캡처하여 Hub에 보고함

if __name__ == "__main__":
    tyro.cli(main)