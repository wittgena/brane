# xphi.flow.logtail.workflow
## @lineage: meta.xor.task.trace.logtail.workflow
import sys
import json
import asyncio
import argparse
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from bound.inter.embeddings.huggingface import HuggingFaceEmbedding
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self, resolve_path
from phase.bind.folding import folding

log = get_emitter("logtail.workflow", phase="loop")

try:
    SELF_ROOT = find_current_self()
    SPEC_ROOT = resolve_path('spec')
    THEORIA_ROOT = SPEC_ROOT / "theoria"
except Exception as e:
    log.error(f"[Apoptosis] Missing boundary reference: {e}")

@dataclass
class PhagocytosedEvent:
    """@event: Raw text noise absorbed from the external environment."""
    raw_text: str
    source_id: str

@dataclass
class ReceptorBoundEvent:
    """@event: High-dimensional topological coordinates vectorized via embedding."""
    v_state: List[float]
    source_id: str

@dataclass
class TrackRoutedEvent:
    """@event: Execution spec derived from SVM routing."""
    track_id: str
    v_state: List[float]
    svm_w: List[float]
    svm_b: float
    action_template: Dict[str, Any]
    target_endpoint: str
    atp_cap: int

class TheoriaIngestWorkflow:
    """
    ### @project.regime("theoria.ingest")
    @flow: phagocytosis -> topic_receptor -> svm_router -> materialize
    @desc: Incinerates external civilization noise and refines it into pure v_state JSON specs
           (Refactored: Pure Async Pipeline, No LlamaIndex Workflow Dependency)
    """
    def __init__(self, timeout: float = 120.0, *args, **kwargs):
        self.timeout = timeout
        
        # @model.init: Absolute isolation from external APIs (e.g., OpenAI) via air-gapped local model
        log.info("## @init: Loading local HuggingFace embedding model...")
        self.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
        
        # @latent.topics: Virtual centroids and SVM weights mapped for each sub-track
        self.registry = {
            "trk_predictive": {
                "centroid": np.random.rand(384), # BGE-small dim
                "target_endpoint": "https://api.proxy-node.local/execute/alpha",
                "action": {"instruction": "0x8fa3...b1"},
                "svm_w": np.random.rand(384).tolist(),
                "svm_b": -0.65,
                "atp_cap": 19000
            },
            "trk_saas": {
                "centroid": np.random.rand(384),
                "target_endpoint": "https://api.proxy-node.local/execute/beta",
                "action": {"cmd": "provision_instance"},
                "svm_w": np.random.rand(384).tolist(),
                "svm_b": 0.0,
                "atp_cap": 19000
            },
            "trk_detritivore": {
                "centroid": np.random.rand(384),
                "target_endpoint": "https://api.proxy-node.local/execute/gamma",
                "action": {"method": "eth_sendTransaction"},
                "svm_w": np.random.rand(384).tolist(),
                "svm_b": -1.2,
                "atp_cap": 19000
            }
        }

    async def phagocytosis(self, raw_data: str, source_id: str) -> PhagocytosedEvent:
        """@step.1: Phagocytosis (Raw Stream Collection)"""
        if not raw_data:
            raise ValueError("No raw_data provided.")
            
        log.info(f"[Chamber 1] Phagocytosis: Ingested chaos from {source_id}")
        return PhagocytosedEvent(raw_text=raw_data, source_id=source_id)

    async def topic_receptor(self, ev: PhagocytosedEvent) -> ReceptorBoundEvent:
        """@step.2: Local LLM Embedding (Semantic Receptor Binding)"""
        log.info(f"[Chamber 2] Topic Receptor: Vectorizing semantic noise...")
        
        # @action.compress: Convert text into high-dimensional numerical arrays (hallucination eliminated).
        v_state = await asyncio.to_thread(self.embed_model.get_text_embedding, ev.raw_text)
        
        return ReceptorBoundEvent(v_state=v_state, source_id=ev.source_id)

    async def svm_router(self, ev: ReceptorBoundEvent) -> Optional[TrackRoutedEvent]:
        """@step.3: Topological Boundary Declaration (Deterministic Routing)"""
        log.info(f"[Chamber 3] SVM Router: Calculating topological distance...")
        vec = np.array(ev.v_state)
        
        best_track = None
        highest_similarity = -1.0
        
        # @match: Search for the nearest cluster (Topic) via Cosine Similarity
        for track_id, config in self.registry.items():
            centroid = config["centroid"]
            similarity = np.dot(vec, centroid) / (np.linalg.norm(vec) * np.linalg.norm(centroid))
            
            if similarity > highest_similarity:
                highest_similarity = float(similarity)
                best_track = track_id
        
        # @filter: Incinerate as Trash (Apoptosis) if similarity falls below survival threshold
        if highest_similarity < 0.75:
            log.warning(f"[Apoptosis] Signal attenuated (Similarity: {highest_similarity:.2f}). Dropping.")
            return None # 기존 StopEvent(result=None)을 대체하는 즉각 종료 시그널
            
        log.info(f"[Route] Signal matched to {best_track} (Sim: {highest_similarity:.2f})")
        config = self.registry[best_track]
        
        return TrackRoutedEvent(
            track_id=best_track,
            v_state=ev.v_state,
            svm_w=config["svm_w"],
            svm_b=config["svm_b"],
            action_template=config["action"],
            target_endpoint=config["target_endpoint"],
            atp_cap=config["atp_cap"]
        )

    async def normalize_and_materialize(self, ev: TrackRoutedEvent) -> Dict[str, Any]:
        """@step.04: Generate machine-readable spec file (JSON) for subordinate Surgents."""
        spec_payload = {
            "track_id": ev.track_id,
            "source_endpoint": "internal_memory_bus",
            "target_endpoint": ev.target_endpoint,
            "action_template": ev.action_template,
            "svm_w": ev.svm_w,
            "svm_b": ev.svm_b,
            "atp_cap": ev.atp_cap,
            "timeout_ms": 3000
        }
        
        # @material: Persist to physical filesystem for downstream container hooks.
        THEORIA_ROOT.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        out_file = THEORIA_ROOT / f"logtail_{ev.track_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(spec_payload, f, indent=2)
            
        # @log.stream: Write standalone v_state stream for debugging/logging purposes.
        stream_file = THEORIA_ROOT / f"stream_{ev.track_id}.jsonl"
        with open(stream_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"v_state": ev.v_state}) + "\n")
            
        log.info(f"[Materialize] Topos spec written to {out_file.name}")
        return {
            "status": "success",
            "track_id": ev.track_id,
            "spec_file": str(out_file)
        }

    async def _execute_pipeline(self, raw_data: str, source_id: str) -> Optional[Dict[str, Any]]:
        """순수 비동기 체이닝을 통한 워크플로우 명시적 실행"""
        ev1 = await self.phagocytosis(raw_data, source_id)
        ev2 = await self.topic_receptor(ev1)
        ev3 = await self.svm_router(ev2)
        
        if ev3 is None:
            return None # Apoptosis (임계점 미달로 폐기)
            
        result = await self.normalize_and_materialize(ev3)
        return result

    async def run(self, raw_data: str, source_id: str = "external_api") -> Optional[Dict[str, Any]]:
        """타임아웃이 적용된 외부 호출용 진입점"""
        try:
            return await asyncio.wait_for(
                self._execute_pipeline(raw_data, source_id),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            log.error("[System Failure] Workflow execution timed out.")
            return None


async def run_pipeline(mock_data: str):
    """@pipeline: Execute workflow within the isolated topological membrane."""
    workflow = TheoriaIngestWorkflow(timeout=120.0)
    
    # @bound.folding: 기존의 run() 시그니처가 유지되었으므로 folding 컨텍스트도 정상 동작합니다.
    with folding(workflow, re_entry_limit=5) as b_workflow:
        log.info(f"[System] Topological bounds active. Commencing digestion.")
        
        result = await b_workflow.run(
            raw_data=mock_data, 
            source_id="twitter_firehose_01"
        )
        
    log.info("\n" + "="*40)
    if result:
        log.info("[Digestion Complete]")
        log.info(f"- Routed Track : {result.get('track_id')}")
        log.info(f"- Spec Path    : {result.get('spec_file')}")
    else:
        log.info("[Digestion Halted] Signal fell below boundary threshold (Apoptosis).")
    log.info("="*40)

def main():
    parser = argparse.ArgumentParser(description="Theoria Logtail Ingest Pipeline")
    parser.add_argument("--test-input", default="Breaking: Protocol Alpha announces unexpected hard fork at block 192844.", help="Test raw text injection.")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_pipeline(args.test_input))
    except Exception as e:
        log.critical(f"[System Failure] Membrane Collapse: {e}")

if __name__ == "__main__":
    main()