# arch.contract.state.spec
## @lineage: topos.state.rule.trans
import enum 
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple

class NodeType(enum.Enum):
    ANCHOR = "ANCHOR"
    CORE = "CORE"
    SYMLINK = "SYMLINK"
    ATTRACTOR = "ATTRACTOR"
    PULSE = "PULSE"
    RUPTURE = "RUPTURE"

class TransRule:
    def __init__(self, source_name: str, target_name: str, target_kind: NodeType, action: str = "INVERT"):
        self.source_name = source_name
        self.target_name = target_name
        self.target_kind = target_kind
        self.action = action

class PhaseSpec:
    def __init__(self, phase_name: str, structure: Dict[str, NodeType], rules: List[TransRule] = None):
        self.phase_name = phase_name
        self.structure = structure
        self.rules = rules or []
