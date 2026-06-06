# bound.template.transcript
import asyncio
import logging
import inspect
from typing import Any, Dict, List, Optional
from pathlib import Path
from arch.proto.phase.flow import PhaseFlow, FlowState, Transduction, Align
from watcher.plane.emitter import get_emitter
from dataclasses import dataclass, field
from phase.bind.resolver import find_current_self, resolve_path
from arch.contract.registry.unified import registry, contract
from phase.ator.runtime import AtorRuntime
from phase.ator.bootstrap import bootstrap
from phase.runtime.node import NodeRuntime

SPEC_ROOT = resolve_path("spec")
log = get_emitter("template.transcript")

XPHI = {
    "entry": "transcriptor",
    "nodes": {
        "transcriptor": {
            "type": "ator",
            "spec": {
                "role": "transform_script_to_topology",
                "next": "END",
                "operator": "ator.generator"
            }
        }
    }
}

@dataclass
class CodeBlock:
    block_type: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NormalizedOp:
    name: str
    op_type: str
    effect: str
    inputs: List[str]
    outputs: List[str]
    raw_block: CodeBlock

class BlockExtractor:
    """일반 스크립트의 텍스트 블록을 AST나 정규식으로 위상 단위로 파편화(Fragmentation)"""
    def extract(self, file_path: str) -> List[CodeBlock]:
        log.info(f"  [Extractor] Extracting fragments from {file_path}")
        # 임시 Mock 데이터 (실제로는 ast를 사용해 함수/클래스를 분리하게 됩니다)
        dummy_code = "def sample_function():\n    with open('test.txt', 'r') as f:\n        return f.read()"
        return [CodeBlock(block_type="python", content=dummy_code)]

class BlockNormalizer:
    """파편화된 코드를 Ator가 소화할 수 있는 NormalizedOp(규격화된 작용소)로 정렬"""
    def normalize(self, blocks: List[CodeBlock]) -> List[NormalizedOp]:
        ops = []
        for block in blocks:
            if block.block_type == "python":
                ops.append(self._normalize_python(block))
        return [op for op in ops if op is not None]

    def _normalize_python(self, block: CodeBlock) -> Optional[NormalizedOp]:
        code = block.content
        if "open(" in code or "Path(" in code:
            return NormalizedOp(
                name=f"file_io_op",
                op_type="transduction",
                effect="filesystem",
                inputs=["file_path"],
                outputs=["file_content"],
                raw_block=block
            )
        return None

class ScriptSynthesizer:
    """추출된 연산자들을 엮어 새로운 대상 스크립트의 XPHI 구조(위상)를 합성"""
    def synthesize(self, ops: List[NormalizedOp]) -> Dict[str, Any]:
        script_topology = {
            "entry": f"step_00_{ops[0].name}" if ops else "END",
            "nodes": {}
        }
        for i, op in enumerate(ops):
            node_id = f"step_{i:02d}_{op.name}"
            next_node = f"step_{i+1:02d}_{ops[i+1].name}" if i + 1 < len(ops) else "END"
            
            script_topology["nodes"][node_id] = {
                "type": "ator" if op.op_type == "transduction" else "resonance",
                "spec": {
                    "role": f"auto_{op.name}",
                    "next": next_node,
                    "operator": op.name
                }
            }
        return script_topology

class CodeGenerator:
    """일반 순차 코드를 @contract.ator로 감싸 독립된 실행체(Phage)로 평탄화(Flatten)"""
    def generate_code(self, op: NormalizedOp) -> str:
        class_name = op.name.replace("_", " ").title().replace(" ", "")
        code = f"""
@contract.ator("{op.name}")
class {class_name}(Transduction):
    def _execute_transformation(self, data, instruction):
        # [Auto-Extracted Code from Legacy Script]
{self._indent_code(op.raw_block.content, indent=8)}
        return data
"""
        return code.strip()

    def _indent_code(self, code: str, indent: int) -> str:
        spaces = " " * indent
        return "\n".join(spaces + line for line in code.split("\n"))

class MetaTranscriptor:
    def __init__(self):
        self.extractor = BlockExtractor()   
        self.normalizer = BlockNormalizer()
        self.synthesizer = ScriptSynthesizer()
        self.generator = CodeGenerator()

    def ingest(self, file_path: str):
        blocks = self.extractor.extract(file_path)
        ops = self.normalizer.normalize(blocks)
        script_topology = self.synthesizer.synthesize(ops)
        ator_codes = {op.name: self.generator.generate_code(op) for op in ops}
        return script_topology, ator_codes

@contract.ator("ator.generator")
class AtorGenerator(Transduction):
    def transduce(self, flow: PhaseFlow, ator_node: Any) -> PhaseFlow:
        log.info(f"  [Generator] Initiating Meta-Transcription Process...")
        
        target_file = flow.payload.get("target_file", "./dummy_source.py")
        transcriptor = MetaTranscriptor()
        
        # 전체 파이프라인 실행
        script_topology, ator_codes = transcriptor.ingest(find_current_self() / target_file)
        
        # ==============================================================================
        # [2] Output Formatting: 일반 코드를 엔진이 실행 가능한 XPHI 구조체로 변환 출력
        # ==============================================================================
        output_code = f"from topos.bound.proto.flow import Transduction\n"
        output_code += f"from phase.runtime.contract.registry.unified import contract\n\n"
        output_code += f"# --- GENERATED SCRIPT TOPOS (XPHI) ---\n"
        output_code += f"XPHI = {script_topology}\n\n"
        output_code += f"# --- GENERATED ATORS ---\n"
        
        for name, code in ator_codes.items():
            output_code += f"\n{code}\n"
            
        log.info("  [Transcriptor] Transcription successful. Handing over to Aligner.")
        
        # 터미널이나 파일로 출력하기 위해 Payload에 탑재
        return PhaseFlow(
            payload={"code": output_code},
            aspect="transcribed",
            id=flow.id
        )

async def main():
    log.info(">>> Launching Ator Meta Transcript <<<")
    # 1. 자신(meta.py)을 부트스트랩 (상단에 정의한 XPHI를 읽어들임)
    current_script_path = inspect.getsourcefile(lambda: None)
    base_node, flow_controller, entry_id = await bootstrap(current_script_path)

    TARGET_SCRIPT = SPEC_ROOT / "script" / "os" / 'machine.py'
    try:
        initial_payload = {
            "task_id": "GEN-303",
            "requirement": "Extract and generate Ators",
            "target_file": TARGET_SCRIPT
        }
        initial_ctx = FlowState(PhaseFlow(payload=initial_payload, aspect="init"), state={})
        
        log.info(f"Submitting target script to Meta-Transcriptor entry node [{entry_id}]...")
        
        # [수정됨] 거시 엔진(NodeRuntime)이 아닌 국소 흐름 제어기(AtorRuntime)에 자극 주입
        await flow_controller.psi_queue.put((entry_id, initial_ctx))
        await flow_controller.psi_queue.join()
        
        log.info(">>> Field Stabilized: Meta-Transcription Complete.")
    except Exception as e:
        log.error(f"Execution Error: {e}", exc_info=True)
    finally:
        base_node.running = False
        await flow_controller.detach()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    asyncio.run(main())