# arch.contract.registry.unified
## @lineage: topos.contract.registry.unified
## @lineage: phase.runtime.contract.registry.unified
import sys
import importlib
from types import SimpleNamespace
from typing import Any, Dict, List, Set, Type, Protocol, runtime_checkable, FrozenSet, Callable, Optional, Mapping
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict
from arch.contract.protocol import Proto

@runtime_checkable
class PhaseNode(Protocol):
    def align(self, surface: Dict[str, Any]) -> None: ...
    def transform(self) -> None: ...
    def project(self) -> Dict[str, Any]: ...

@dataclass(frozen=True)
class ContractSpec:
    requires: FrozenSet[str]
    emits: FrozenSet[str]
    proto: Optional[Proto] = None

@dataclass(frozen=True)
class NodeMeta:
    node_class: Type[PhaseNode]
    contract: ContractSpec

class UnifiedRegistry:
    """단일 진실 공급원 (SSOT) 레지스트리 - 가소성(Plasticity) 지원"""
    def __init__(self):
        self._nodes: Dict[str, NodeMeta] = {}
        self._cli_tasks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._kernels: Dict[str, Type] = {} 
        self._fields: Dict[str, Type] = {}
        self._watchers: Dict[str, Type] = {}
        self._regimes: Dict[str, Type] = {}
        self._ators: Dict[str, Type] = {}

    def __len__(self) -> int:
        """등록된 위상 노드(PhaseNode)의 개수를 반환"""
        return len(self._nodes)

    @property
    def registered_nodes(self) -> Mapping[str, NodeMeta]:
        return self._nodes

    @property
    def registered_cli_tasks(self) -> Mapping[str, List[Dict[str, Any]]]:
        return self._cli_tasks

    def register_node(self, name: str, cls: Type[PhaseNode], requires: list, emits: list, proto: Optional[Proto] = None):
        contract = ContractSpec(
            requires=frozenset(requires), emits=frozenset(emits), proto=proto
        )
        cls.__manifold_contract__ = contract
        self._nodes[name] = NodeMeta(node_class=cls, contract=contract)
    
    def register_cli_task(self, name: str, module_fqn: str, args: Optional[List[str]] = None, 
                          tags: Optional[List[str]] = None, entry: str = "", recept: Optional[List[str]] = None,
                          task_type: str = "cli"):
        """[개선] 핫 리로딩 안전성 (Idempotency) 보장 - 동일한 module_fqn이 이미 존재한다면 제거 후 새로 등록하여 리스트 중복 팽창을 방지"""
        self._cli_tasks[name] = [
            task for task in self._cli_tasks[name] 
            if task.get("module_fqn") != module_fqn
        ]
        
        self._cli_tasks[name].append({
            "module_fqn": module_fqn, 
            "args": args or [],
            "tags": tags or [],
            "entry": entry,
            "recept": recept or [],
            "type": task_type 
        })

    def add_dynamic_route(self, route_name: str, component_config: Dict[str, Any]):
        """
        [추가] 런타임 동적 가소성 (Runtime Plasticity)
        파이썬 파일(.py) 로드 없이, 실행 중인 시스템에 새로운 위상 라우팅(Config 조합)을 즉시 생성합니다.
        """
        # 강제 덮어쓰기 (가장 최신의 동적 주입이 우선권을 가짐)
        self._cli_tasks[route_name] = [component_config]
        print(f"[Registry] Dynamic Route Formed: {route_name}")

    def register_component(self, category: str, name: str, cls: Type):
        target = getattr(self, f"_{category}s")
        name_key = name.lower()

        if name_key in target and target[name_key].__name__ == cls.__name__:
            ## 핫 리로드 혹은 중복 임포트 상황. 조용히 넘어감.
            target[name_key] = cls
            return
            
        target[name_key] = cls
        print(f"[Registry] Component Registered: [{category}] {name} -> {cls.__name__}")

    def create_component(self, category: str, config: Any, **extra_kwargs):
        """범용 컴포넌트 팩토리"""
        if isinstance(config, dict):
            c_type = config.get('type', '').lower()
            params = config.get('params', {})
            extra_kwargs = {**params, **extra_kwargs}
        else:
            c_type = getattr(config, 'type', '').lower()
            
        target_map = getattr(self, f"_{category}s")
        
        if c_type not in target_map:
            raise ValueError(f"[Registry] Unknown {category}: {c_type}")

        node_class = target_map[c_type]
        try:
            return node_class(**extra_kwargs)
        except TypeError as e:
            raise TypeError(f"[Registry] Failed to init {node_class.__name__} due to signature mismatch: {e}")

registry = UnifiedRegistry()

def manifold_node(name: str, *, requires: List[str] = None, emits: List[str] = None):
    requires = requires or []
    emits = emits or []
    def decorator(cls: Type):
        proto_meta = getattr(cls, "__proto_meta__", None) 
        registry.register_node(name, cls, requires, emits, proto_meta)
        return cls
    return decorator

def cli_contract(name: str, args: List[str] = None, tags: List[str] = None, entry: str = "entry_task", recept: List[str] = None):
    """일반적인 단일 반환(Discrete) 형태의 작업을 위한 수용체"""
    def decorator(func: Callable):
        registry.register_cli_task(name, func.__module__, args, tags, entry, recept, task_type="cli")
        return func
    return decorator

def flow_contract(name: str, args: List[str] = None, tags: List[str] = None, entry: str = "entry_task", recept: List[str] = None):
    """RMFlow, GanNode 등 연속적인 스트림(Continuous stream) 형태의 작업을 위한 수용체"""
    def decorator(func: Callable):
        registry.register_cli_task(name, func.__module__, args, tags, entry, recept, task_type="flow")
        return func
    return decorator

def kernel_contract(name: str):
    def decorator(cls: Type): registry.register_component("kernel", name, cls); return cls
    return decorator

def field_contract(name: str):
    def decorator(cls: Type): registry.register_component("field", name, cls); return cls
    return decorator

def watcher_contract(name: str):
    def decorator(cls: Type): registry.register_component("watcher", name, cls); return cls
    return decorator

def regime_contract(name: str):
    def decorator(cls: Type): registry.register_component("regime", name, cls); return cls
    return decorator

def ator_contract(name: str):
    def decorator(cls: Type): registry.register_component("ator", name, cls); return cls
    return decorator

contract = SimpleNamespace(
    cli=cli_contract,
    flow=flow_contract,
    kernel=kernel_contract,
    field=field_contract,
    watcher=watcher_contract,
    regime=regime_contract,
    ator=ator_contract,
    node=manifold_node
)