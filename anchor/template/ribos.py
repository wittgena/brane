# anchor.template.ribos
## @lineage: anchor.workflow.template.ribos
## @lineage: bound.template.ribos
## @lineage: hub.model.template.ribos
## @lineage: phase.hub.template.ribos
## @lineage: arch.proto.template.ribos
## @lineage: nexus.repo.template.ribos
## @lineage: nexus.exp.template.ribos
## @lineage: iso.domain.template.ribos
## @lineage: agent.domain.template.ribos
## @lineage: domain.template.ribos
## @lineage: hub.template.ribos
#!/usr/bin/env python3
from __future__ import annotations
import ast
import gc
import hashlib
import importlib.metadata
import json
import logging
import os
import random
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional, Union

import tyro

ribos_OUTPUT_SCHEMA = 1
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ribos")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
    return h.hexdigest()

def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)

def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): rows.append(json.loads(line))
    return rows

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_config(path: Path) -> dict:
    """Accept .yaml or .json config. PyYAML is required iff yaml is used."""
    suffix = path.suffix.lower()
    if suffix in (".json",):
        return read_json(path)
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError(
                "config is YAML but PyYAML is not installed. "
                "Either install pyyaml or convert config to JSON."
            ) from e
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    raise ValueError(f"unsupported config extension: {path.suffix}")

def pkg_version(name: str) -> Optional[str]:
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return None


# ============================================================================
# 2. Domain Models (Packet & Configuration)
# ============================================================================
@dataclass
class Packet:
    root: Path
    transcript: dict
    corpus_path: Path
    config_path: Path
    eval_path: Optional[Path]
    prev_adapter: Optional[Path]
    ribos_path: Path

    @property
    def packet_id(self) -> str:
        return self.transcript.get("packet_id") or self.root.name

def load_packet(packet_dir: Path) -> Packet:
    if not packet_dir.is_dir(): raise NotADirectoryError(packet_dir)
    
    transcript = read_json(packet_dir / "transcript.json")
    corpus = packet_dir / "corpus.jsonl"
    ribos = packet_dir / "ribos.py"
    
    config = next((packet_dir / cand for cand in ("config.yaml", "config.yml", "config.json") 
                   if (packet_dir / cand).exists()), None)
    
    if not all([corpus.exists(), config, ribos.exists()]):
        raise FileNotFoundError("Packet is missing essential files (corpus, config, or ribos.py)")

    eval_path = packet_dir / "eval_holdout.jsonl"
    prev = packet_dir / "prev_adapter"
    
    return Packet(
        root=packet_dir, transcript=transcript, corpus_path=corpus, config_path=config,
        eval_path=eval_path if eval_path.exists() else None,
        prev_adapter=prev if prev.is_dir() else None,
        ribos_path=ribos
    )

def verify_packet(packet: Packet) -> dict:
    """Re-hash every file declared in transcript.files and check against the declared sha256."""
    declared: dict = packet.transcript.get("files") or {}
    if not declared:
        return {"ok": False, "reason": "transcript missing 'files' map"}

    issues: list[dict] = []
    for relpath, meta in declared.items():
        expected = (meta or {}).get("sha256")
        local = packet.root / relpath
        if not local.exists():
            issues.append({"file": relpath, "issue": "missing_locally"})
            continue
        actual = sha256_file(local)
        if expected and actual != expected:
            issues.append({
                "file": relpath, "issue": "hash_mismatch",
                "expected": expected, "actual": actual,
            })

    self_path = Path(__file__).resolve()
    self_sha = sha256_file(self_path)
    transcript_ribo_sha = packet.transcript.get("ribos_version")
    packet_ribo_sha = sha256_file(packet.ribos_path)

    if transcript_ribo_sha and transcript_ribo_sha != packet_ribo_sha:
        issues.append({
            "file": "ribos.py", "issue": "transcript_vs_packet_mismatch",
            "transcript": transcript_ribo_sha, "packet": packet_ribo_sha,
        })

    running_matches_packet = (self_sha == packet_ribo_sha)

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "self_sha": self_sha,
        "packet_ribos_sha": packet_ribo_sha,
        "transcript_ribos_sha": transcript_ribo_sha,
        "running_matches_packet": running_matches_packet,
    }


# ============================================================================
# 3. Core ML Logic (Colab 최적화 및 학습 평가 엔진)
# ============================================================================
def seed_everything(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError: pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    except ImportError: pass
    try:
        from transformers import set_seed
        set_seed(seed)
    except ImportError: pass

def make_chat_text(tokenizer, prompt: str, completion: str, context: str = "") -> str:
    system_msg = "Surgent Topology Resolver"
    if context: system_msg += f"\nContext: {context}"
    full_msgs = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": completion},
    ]
    try:
        return tokenizer.apply_chat_template(full_msgs, tokenize=False, add_generation_prompt=False)
    except Exception:
        merged = (f"[Context: {context}]\n\n{prompt}") if context else prompt
        msgs = [{"role": "user", "content": merged}, {"role": "assistant", "content": completion}]
        return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)

def build_dataset(corpus_path: Path, tokenizer):
    from datasets import Dataset
    raw = read_jsonl(corpus_path)
    if not raw: raise RuntimeError(f"corpus is empty: {corpus_path}")

    def to_text(ex: dict) -> dict:
        return {"text": make_chat_text(
            tokenizer, prompt=ex.get("prompt", ""),
            completion=ex.get("completion", ""),
            context=ex.get("topology_context", "") or "",
        )}
    ds = Dataset.from_list(raw).map(to_text, remove_columns=Dataset.from_list(raw).column_names)
    return ds

def load_base_with_adapter(config: dict, prev_adapter: Optional[Path]):
    from unsloth import FastLanguageModel
    parent_model = config["parent_model"]
    max_seq_length = int(config.get("max_seq_length", 2048))
    lora_cfg = config.get("lora", {}) or {}
    
    log.info(f"loading base model: {parent_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = parent_model,
        max_seq_length = max_seq_length,
        dtype = None,
        load_in_4bit = True,
    )

    if prev_adapter is not None and prev_adapter.exists():
        log.info(f"continuing from prev adapter: {prev_adapter}")
        model.load_adapter(str(prev_adapter), adapter_name="default")
    else:
        log.info("creating fresh LoRA adapter")
        model = FastLanguageModel.get_peft_model(
            model,
            r = int(lora_cfg.get("r", 16)),
            target_modules = lora_cfg.get("target_modules", ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]),
            lora_alpha = int(lora_cfg.get("alpha", 16)),
            lora_dropout = float(lora_cfg.get("dropout", 0.0)),
            bias = "none",
            use_gradient_checkpointing = "unsloth",
            random_state = int(config.get("training", {}).get("seed", 3407)),
        )
    return model, tokenizer, max_seq_length

def train(model, tokenizer, dataset, config: dict, max_seq_length: int, work_dir: Path) -> dict:
    import torch
    from trl import SFTTrainer
    from transformers import TrainingArguments

    t = config.get("training", {}) or {}
    use_bf16 = bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported())
    
    targs = TrainingArguments(
        per_device_train_batch_size = int(t.get("per_device_train_batch_size", 2)),
        gradient_accumulation_steps = int(t.get("gradient_accumulation_steps", 4)),
        warmup_steps = int(t.get("warmup_steps", 5)),
        max_steps = int(t.get("max_steps", 60)),
        learning_rate = float(t.get("learning_rate", 2e-4)),
        fp16 = not use_bf16, bf16 = use_bf16,
        logging_steps = int(t.get("logging_steps", 1)),
        optim = t.get("optim", "adamw_8bit"),
        weight_decay = float(t.get("weight_decay", 0.0)),
        lr_scheduler_type = t.get("lr_scheduler_type", "linear"),
        seed = int(t.get("seed", 3407)),
        output_dir = str(work_dir / "trainer"),
        save_strategy = "no", report_to = [], disable_tqdm = False,
    )

    trainer = SFTTrainer(
        model = model, tokenizer = tokenizer, train_dataset = dataset,
        dataset_text_field = "text", max_seq_length = max_seq_length,
        args = targs, packing = False,
    )
    log.info(f"training started (max_steps={targs.max_steps})")
    train_result = trainer.train()

    metrics = dict(train_result.metrics) if hasattr(train_result, "metrics") else {}
    try:
        for entry in reversed(trainer.state.log_history):
            if "loss" in entry:
                metrics["final_loss"] = float(entry["loss"])
                break
    except Exception: pass
    return metrics

def evaluate_adapter(model, tokenizer, eval_path: Optional[Path], max_examples: int = 64) -> dict:
    if eval_path is None or not eval_path.exists():
        return {"score": None, "mode": "absolute", "n_eval": 0, "avg_loss": None, "note": "no eval_holdout.jsonl provided"}

    import torch
    rows = read_jsonl(eval_path)[:max_examples]
    if not rows: return {"score": None, "n_eval": 0, "note": "eval set empty"}

    model.eval()
    device = next(model.parameters()).device
    total_loss, n = 0.0, 0
    
    with torch.no_grad():
        for ex in rows:
            text = make_chat_text(tokenizer, prompt=ex.get("prompt", ""), completion=ex.get("completion", ""), context=ex.get("topology_context", "") or "")
            enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=2048)
            input_ids = enc.input_ids.to(device)
            if input_ids.shape[1] < 2: continue
            
            out = model(input_ids=input_ids, labels=input_ids)
            total_loss += float(out.loss.item())
            n += 1

    if n == 0: return {"score": None, "n_eval": 0, "note": "all eval items were empty/too-short"}
    
    avg_loss = total_loss / n
    return {"score": -avg_loss, "mode": "absolute", "n_eval": n, "avg_loss": avg_loss, "note": "score = -avg_loss; higher is better"}


# ============================================================================
# 4. Manifest & System Info
# ============================================================================
def collect_library_versions() -> dict:
    return {pkg: pkg_version(pkg) for pkg in ("torch", "unsloth", "transformers", "trl", "peft", "datasets", "accelerate", "bitsandbytes", "safetensors")}

def collect_gpu_info() -> dict:
    try:
        import torch
        if not torch.cuda.is_available(): return {"available": False}
        return {
            "available": True, "name": torch.cuda.get_device_name(0),
            "count": torch.cuda.device_count(), "capability": list(torch.cuda.get_device_capability(0)),
            "total_mem_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2),
        }
    except Exception as e: return {"available": False, "error": str(e)}

def write_lineage_manifest(out_dir: Path, packet: Packet, config: dict, train_metrics: dict, eval_report: dict, seed: int, self_sha: str, gen_id: str) -> Path:
    transcript = packet.transcript
    manifest = {
        "gen_id": gen_id, "created_at": now_iso(), "packet_id": packet.packet_id,
        "output_schema_version": ribos_OUTPUT_SCHEMA,
        "nexus_version": transcript.get("nexus_version"), "mrna_version": transcript.get("messenger_version"), "ribos_version": self_sha,
        "parent_model": config.get("parent_model"), "parent_adapter": str(packet.prev_adapter.name) if packet.prev_adapter else None,
        "training_corpus": {"filename": packet.corpus_path.name, "sha256": sha256_file(packet.corpus_path), "n_examples": len(read_jsonl(packet.corpus_path))},
        "hyperparameters": config, "seed": seed,
        "library_versions": collect_library_versions(), "gpu": collect_gpu_info(),
        "train_metrics": train_metrics, "eval_report": eval_report,
        "promoted": False, "promoted_at": None,
    }
    path = out_dir / "lineage_manifest.json"
    atomic_write_json(path, manifest)
    return path


# ============================================================================
# 5. Commands (Tyro CLI 기반 워크플로우 제어)
# ============================================================================
@dataclass
class RunCommand:
    """execute a packet → adapter"""
    packet: Path
    out: Path

    def execute(self):
        packet_dir, out_dir = self.packet.resolve(), self.out.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 사후 디버깅용 로깅
        log_file = out_dir / "ribos_run.log"
        log.addHandler(logging.FileHandler(log_file, encoding="utf-8"))
        self_sha = sha256_file(Path(__file__).resolve())
        
        try:
            # 1. 패킷 검증
            pkt = load_packet(packet_dir)
            log.info(f"packet loaded: {pkt.packet_id}")
            vp = verify_packet(pkt)
            if not vp["ok"]:
                atomic_write_json(out_dir / "packet_verification.json", vp)
                raise RuntimeError(f"Packet verification FAILED: {vp['issues']}")
            atomic_write_json(out_dir / "packet_verification.json", vp)

            # 2. 모델 및 데이터 로드
            config = load_config(pkt.config_path)
            seed = int((config.get("training") or {}).get("seed", 3407))
            seed_everything(seed)
            model, tokenizer, max_seq_length = load_base_with_adapter(config, pkt.prev_adapter)
            dataset = build_dataset(pkt.corpus_path, tokenizer)

            # 3. 학습 및 저장
            train_metrics = train(model, tokenizer, dataset, config, max_seq_length, out_dir)
            log.info(f"saving adapter → {out_dir}")
            model.save_pretrained(str(out_dir))
            tokenizer.save_pretrained(str(out_dir / "tokenizer"))

            # 🔥 Colab VRAM 안전장치 (학습 끝난 모델을 메모리에서 강제 제거)
            import torch
            del model
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            log.info("VRAM cleared for evaluation")

            # 4. 재평가를 위한 모델 리로드 및 Eval 수행
            from unsloth import FastLanguageModel
            eval_model, _ = FastLanguageModel.from_pretrained(
                model_name=config["parent_model"], max_seq_length=max_seq_length, dtype=None, load_in_4bit=True
            )
            eval_model.load_adapter(str(out_dir), adapter_name="default")
            
            eval_cfg = config.get("eval", {}) or {}
            eval_report = evaluate_adapter(eval_model, tokenizer, pkt.eval_path, int(eval_cfg.get("max_eval_examples", 64)))
            atomic_write_json(out_dir / "eval_report.json", eval_report)

            # 5. 매니페스트 작성 및 종료
            gen_id = config.get("gen_id") or f"gen-from-{pkt.packet_id}"
            manifest_path = write_lineage_manifest(out_dir, pkt, config, train_metrics, eval_report, seed, self_sha, gen_id)

            print(json.dumps({"status": "ok", "out": str(out_dir), "manifest": str(manifest_path), "eval": eval_report}, indent=2))
            
        except Exception as e:
            atomic_write_json(out_dir / "ribos_error.json", {
                "error": str(e), "traceback": traceback.format_exc(),
                "self_sha": self_sha, "at": now_iso(),
            })
            log.exception("run_genesis crashed")
            sys.exit(1)


@dataclass
class VerifyPacketCommand:
    """check packet integrity (no training)"""
    packet: Path
    def execute(self):
        rep = verify_packet(load_packet(self.packet))
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        sys.exit(0 if rep["ok"] else 2)


@dataclass
class SelfCheckCommand:
    """report ML deps + GPU availability"""
    def execute(self):
        out = {"ok": True, "self_sha": sha256_file(Path(__file__).resolve()), "schema": ribos_OUTPUT_SCHEMA, "deps": {}}
        for name in ("torch", "unsloth", "transformers", "trl", "peft", "datasets"):
            v = pkg_version(name)
            out["deps"][name] = v
            if v is None: out["ok"] = False
        out["gpu"] = collect_gpu_info()
        print(json.dumps(out, indent=2, ensure_ascii=False))
        sys.exit(0 if out["ok"] else 2)

# ============================================================================
# 6. Entrypoint
# ============================================================================
RibosApp = Union[
    Annotated[RunCommand, tyro.conf.subcommand("run")],
    Annotated[VerifyPacketCommand, tyro.conf.subcommand("verify-packet")],
    Annotated[SelfCheckCommand, tyro.conf.subcommand("self-check")],
]

def main(argv: Optional[list[str]] = None) -> None:
    try:
        command = tyro.cli(RibosApp, args=argv)
        command.execute()
    except SystemExit:
        raise
    except Exception as e:
        log.error(f"ribos error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()