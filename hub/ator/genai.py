# hub.ator.genai
## @lineage: bound.ator.genai
import json
import asyncio
import inspect
from typing import Any
from watcher.plane.emitter import get_logger
from arch.proto.phase.flow import PhaseFlow, FlowState, Transduction, Resonance, Judgment, Align
from arch.contract.registry.unified import contract
from arch.contract.discovery import discover_modules
from phase.bind.resolver import find_current_self
from phase.runtime.node import NodeRuntime
from phase.hub.ator.runtime import AtorRuntime
from phase.hub.ator.bootstrap import bootstrap 
from phase.bind.client.engine.local import LLMEngine
from phase.bind.resolver import resolve_path

log = get_logger("ator.genai")

@contract.ator("trans.genai")
class TransGenai(Transduction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm_client = LLMEngine()

    def _project(self, flow: PhaseFlow, ator_node: Any) -> dict:
        log.info(f"  [Projection] Opening state for LLM inference: {ator_node.role}")
        payload = flow.payload
        
        context = ator_node.spec.get("context", {})
        system_prompt = context.get("instruction", "You are a helpful expert.")
        if "metrics" in context:
            system_prompt += f"\nTarget metrics: {context['metrics']}"
            
        input_data = payload.get('raw_input') or payload
        user_prompt = f"Input Context:\n{json.dumps(input_data, indent=2, ensure_ascii=False)}"

        log.info(f"  [LLM] Requesting completion for role: {ator_node.role}")
        
        try:
            response = self.llm_client.chat(
                system_prompt=system_prompt, 
                user_prompt=user_prompt,
                timeout=60
            )
            log.info(f"  [LLM] Inference successful for {ator_node.role}")
        except Exception as e:
            log.error(f"  [LLM] Inference failed: {e}", exc_info=True)
            response = f"ERROR_DURING_INFERENCE: {str(e)}"
        return { **payload, "llm_output": response }

async def main():
    input_path = resolve_path('jobs') / 'transcript' / 'meta_debug.py'
    # current_script_path = inspect.getsourcefile(lambda: None)
    base_node, flow_controller, entry_id = await bootstrap(input_path)

    try:
        initial_payload = {
            "task_id": "REQ-101",
            "requirement": "User profile update API with rate limiting",
            "security_level": "High"
        }
        initial_ctx = FlowState(PhaseFlow(payload=initial_payload, aspect="init"), state={})
        log.info(f"Submitting task to entry node [{entry_id}]...")
        
        await base_node.psi_queue.put((entry_id, initial_ctx))
        await base_node.psi_queue.join()
        log.info(">>> Field Stabilized: Execution Complete.")
    except Exception as e:
        log.error(f"Execution Error: {e}", exc_info=True)
    finally:
        base_node.running = False

if __name__ == "__main__":
    asyncio.run(main())