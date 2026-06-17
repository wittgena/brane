# phase.ator.bootstrap
## @lineage: phase.hub.ator.bootstrap
## @lineage: hub.ator.bootstrap
## @lineage: xe.ator.bootstrap
## @lineage: xphi.ator.bootstrap
## @lineage: cognitive.xphi.ator.bootstrap
## @lineage: topos.bound.ator.bootstrap
## @signal: 505
"""@flow: PHI(Φ_declared) → reflect → Ψ → materialize → Φ_materialized → entry(anchor)"""
import asyncio
import json
import inspect
import ast
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple
from watcher.plane.emitter import get_logger
from arch.proto.phase.flow import PhaseFlow, FlowState, Transduction
from arch.contract.registry.unified import contract, registry
from arch.contract.discovery import discover_modules
from phase.ator.transcript.phi import TranscriptPhi
from phase.ator.transcript.spec import TranscriptSpec
from phase.ator.runtime import AtorRuntime
from phase.runtime.node import NodeRuntime
from phase.bind.resolver import find_current_self, resolve_path, load_bound

log = get_logger("ator.bootstrap")
SELF_ROOT = find_current_self()
REPOS = load_bound(SELF_ROOT).get('around', None)

## @phase: Φ_declared
XPHI = {
  "activator": {
    "type": "ator",
    "spec": {
      "role": "planner",
      "next": "topos_validator",
      "context": {
        "instruction": "Create a 3-step project roadmap",
        "temperature": 0.2,
        "inject_state": ["project_id"]
      },
      "operator": "genai.transductor"
    }
  },
  "topos_validator": {
    "type": "resonance",
    "spec": {
      "role": "resonance.validator",
      "next": "evaluator",
      "operator": "resonance.validator"
    }
  },
  "evaluator": {
    "type": "ator",
    "spec": {
      "role": "security.auditor",
      "next": "interference",
      "context": {
        "instruction": "Perform OWASP Top 10 scan on the provided code",
        "metrics": ["injection", "broken_auth", "data_exposure"]
      }
    }
  },
  "interference": {
    "type": "resonance",
    "spec": {
      "next": "feedback",
      "operator": "security.resonance"
    }
  },
  "feedback": {
    "type": "judgment",
    "spec": {
      "rules": { "retry": "activator", "stable": "projection" },
      "operator": "resonance.judgment"
    }
  },
  "projection": {
    "type": "aligner",
    "spec": {
      "target": "./output/secure_api.py",
      "next": "UGA"
    }
  }
}

async def bootstrap(
    topology_path: str, 
    redis_url: str = "redis://localhost:6379",
    repos: List[str] = REPOS
) -> Tuple[NodeRuntime, AtorRuntime, str]:
    is_spec = topology_path.lower().endswith('.md')
    log_msg = "via Spec Transcript" if is_spec else "via Transcript"
    log.info(f">>> Launching Complex Phase-Field Task {log_msg}...")

    discover_modules(find_current_self())
    base_node = NodeRuntime(redis_url=redis_url, executor=None)
    bootstrap_flow = PhaseFlow(payload=topology_path, aspect="bootstrap")

    transcript_cls = TranscriptSpec if is_spec else TranscriptPhi
    transcript = transcript_cls(base_node)

    final_flow = transcript.transduce(bootstrap_flow, ator_node=transcript)
    runtime_nodes = final_flow.payload

    entry_node = next(iter(final_flow.payload))
    flow_controller = AtorRuntime(entry=entry_node, nodes=runtime_nodes, runtime_node=base_node)
    flow_controller.attach()
    return base_node, flow_controller, entry_node

async def main():
    topology_path = inspect.getsourcefile(lambda: None)
    base_node, flow_controller, entry_node = await bootstrap(topology_path)

    try:
        ## @emit: external task → Ψ injection into field
        initial_payload = {
            "task_id": "REQ-101",
            "requirement": "User profile update API with rate limiting",
            "security_level": "High"
        }
        initial_ctx = FlowState(PhaseFlow(payload=initial_payload, aspect="init"), state={})
        log.info(f"Submitting task {initial_payload['task_id']} to the local field...")
        
        ## 거시 엔진이 아닌 국소 흐름 제어기에 직접 자극(Task) 주입
        await flow_controller.psi_queue.put(("activator", initial_ctx))
        await flow_controller.psi_queue.join()
        
        log.info(">>> All tasks processed.")
    except Exception as e:
        ## @shutdown: field collapse / loop termination
        log.error(f"Execution Error: {e}", exc_info=True)
    finally:
        base_node.running = False
        await flow_controller.detach()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
