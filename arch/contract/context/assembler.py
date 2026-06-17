# arch.contract.context.assembler
## @lineage: theoria.arch.contract.context.assembler
import json
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, runtime_checkable, Protocol
from collections import defaultdict
from arch.contract.context.prompt.input import InputBundle, build_prompt 
from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_logger

log = get_logger("context.assembler")

@runtime_checkable
class IResidueProvider(Protocol):
    """
    @role: 외부의 물리적 도구(Xor, Scanner 등)가 Theoria에 결합되기 위해 지켜야 할 최소 규격
    """
    def fetch(self, query: str, **kwargs) -> List[Any]:
        ...

class ContextAssembler:
    """
    @role: Context orchestrator & Prompt fabricator
    @flow: [Data] → Assembler(Schema/YAML/Injected_Search) → InputBundle → Prompt
    @invariant: Must remain agnostic to physical search implementations (e.g., Xor, Redis).
    """
    def __init__(self):
        self.self_root = find_current_self()
        self.blocks_root = resolve_path("blocks")
        self.schema_root = resolve_path("schemas")
        self.config_root = resolve_path("configs")

        self._providers: Dict[str, IResidueProvider] = {}

    def _fetch_unstructured(self, query: str, top_k: int = 20) -> List[str]:
        """
        ## @phase: Unstructured knowledge projection
        ## @flow: search_provider(Ψ) → duck_typing(score, text) → formatted_string
        """
        """등록된 모든 Provider를 순회하며 잔여물(Residue)을 채집"""
        formatted = []
        for name, provider in self._providers.items():
            try:
                # Duck-typing 호출
                raw_results = provider.fetch(query)
                for r in raw_results[:top_k]:
                    score = getattr(r, 'score', 0.0)
                    text = getattr(r, 'text', str(r))
                    formatted.append(f"// @source: {name}\n// @relevance: {score}\n{text}")
            except Exception as e:
                log.warning(f"Provider [{name}] failed to fetch: {e}")
                
        return formatted

    def _load_structured_json(self, file_name: str) -> Optional[str]:
        """정형 데이터(JSON): 무결성 검증 후 구조화된 텍스트로 반환"""
        file_path = (self.schema_root / file_name).with_suffix('.json')
        if not file_path.exists():
            log.warning(f"JSON schema not found: {file_path}")
            return None
            
        try:
            content = file_path.read_text(encoding="utf-8")
            parsed = json.loads(content)
            normalized_content = json.dumps(parsed, indent=2, ensure_ascii=False)
            return f"// @source: registry/{file_name}.json\n// @format: JSON Schema\n```json\n{normalized_content}\n```"
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON format in {file_path}: {e}")
            return None

    def _load_structured_yaml(self, file_name: str) -> Optional[str]:
        """정형 데이터(YAML): 무결성 검증 후 구조화된 텍스트로 반환"""
        file_path = (self.config_root / file_name).with_suffix('.yaml')
        if not file_path.exists():
            file_path = (self.config_root / file_name).with_suffix('.yml')
            if not file_path.exists():
                log.warning(f"YAML config not found: {file_name}")
                return None
                
        try:
            content = file_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)
            normalized_content = yaml.dump(parsed, allow_unicode=True, sort_keys=False)
            return f"// @source: configs/{file_name}.yaml\n// @format: YAML Config\n```yaml\n{normalized_content}\n```"
        except yaml.YAMLError as e:
            log.error(f"Invalid YAML format in {file_path}: {e}")
            return None

    def assemble(self, 
                 query: str, 
                 anchor: str, 
                 state: List[str], 
                 structured_json: Optional[List[str]] = None,
                 structured_yaml: Optional[List[str]] = None,
                 use_xor: bool = True) -> List[Dict]:
        """@flow: Route requests to respective data facets and synthesize InputBundle"""
        evidence_list = []

        if structured_json:
            for j_file in structured_json:
                data = self._load_structured_json(j_file)
                if data: evidence_list.append(data)

        if structured_yaml:
            for y_file in structured_yaml:
                data = self._load_structured_yaml(y_file)
                if data: evidence_list.append(data)

        if use_xor and query and self.search_provider:
            x_data = self._fetch_unstructured(query)
            if x_data: evidence_list.extend(x_data)

        bundle = InputBundle(
            anchor=anchor,
            query=query,
            state=state,
            evidence=evidence_list,
            max_tokens=8000
        )
        return build_prompt(bundle)