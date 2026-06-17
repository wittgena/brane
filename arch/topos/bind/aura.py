# arch.topos.bind.aura
## @lineage: gov.repo.node.aura
## @lineage: meta.reflector.cognitive.aura
## @lineage: bound.reflect.cognitive.aura
## @lineage: cognitive.node.aura
## @lineage: cognitive.aura.node
## @lineage: cognitive.nerve.aura.node
import asyncio
from typing import Dict, Any, Optional
from watcher.plane.emitter import get_emitter
from arch.topos.node.gan import Message, GanNode
from arch.topos.node.state import StateNode
from arch.topos.node.proxy import DistributedNodePool

log = get_emitter(__name__)

class Boundary:
    """노드 간 데이터(메시지/Flow)가 넘어가는 경계를 정의하는 추상 클래스"""
    async def emit(self, target_id: str, payload: Any):
        raise NotImplementedError

class LocalBoundary(Boundary):
    """같은 메모리/프로세스 내에 존재하는 노드 간의 경계 (기존 GanNode의 큐 방식)"""
    def __init__(self, local_registry: Dict[str, 'UnifiedNode']):
        self.registry = local_registry

    async def emit(self, target_id: str, payload: Any):
        if target_id in self.registry:
            target_node = self.registry[target_id]
            # 대상 노드의 로컬 큐로 직접 메시지 삽입
            await target_node.receive(payload)
        else:
            log.warning(f"[LocalBoundary] 타겟 노드 {target_id} 를 로컬에서 찾을 수 없습니다.")

class RemoteBoundary(Boundary):
    """다른 프로세스/네트워크에 존재하는 노드 간의 경계 (기존 Redis psi_queue 방식)"""
    def __init__(self, redis_pool: DistributedNodePool):
        self.pool = redis_pool

    async def emit(self, target_id: str, payload: Any):
        # Redis를 통해 원격 노드의 큐로 메시지/FlowState 전달
        await self.pool.base_node.psi_queue.put((target_id, payload))


class AuraNode:
    """
    DOM 트리 노드이든, DAG 그래프 노드이든 상관없이
    '경계를 통해 데이터를 흘려보내는 정점'이라는 동일한 본질을 가진 래퍼.
    """
    def __init__(self, node_id: str, instance: Any):
        self.node_id = node_id
        self.instance = instance  # AgentApp, PolicyNode, LinkerNode 등 원본 객체
        self.boundaries: Dict[str, Boundary] = {} # 대상별 경계 매핑

    def attach_boundary(self, target_id: str, boundary: Boundary):
        """특정 타겟으로 향하는 엣지(Edge)의 물리적 경계를 설정"""
        self.boundaries[target_id] = boundary

    async def receive(self, payload: Any):
        """이전 노드/경계로부터 데이터를 수신하여 원본 인스턴스에 전달"""
        if isinstance(self.instance, GanNode):
            # GanNode 기반 노드일 경우
            self.instance.post_message(payload)
        elif isinstance(self.instance, StateNode):
            # 기존 Topos 기반 노드일 경우 (FlowState 처리 등)
            await self.instance.process(payload)

    async def route(self, target_id: str, payload: Any):
        """원본 인스턴스가 연산을 마치고 다음 위상으로 데이터를 넘길 때 호출"""
        boundary = self.boundaries.get(target_id)
        if boundary:
            await boundary.emit(target_id, payload)
        else:
            log.error(f"[UnifiedNode] {target_id} 로 향하는 경계(Boundary)가 정의되지 않았습니다.")

class AuraTopos:
    def __init__(self, redis_pool: Optional[DistributedNodePool] = None):
        self.local_registry: Dict[str, AuraNode] = {}
        self.redis_pool = redis_pool
        self.local_boundary = LocalBoundary(self.local_registry)
        self.remote_boundary = RemoteBoundary(self.redis_pool) if self.redis_pool else None

    def organize(self, topology_spec: Dict[str, Any]) -> Dict[str, AuraNode]:
        """
        위상 스펙을 읽어 노드를 인스턴스화하고 경계를 연결합니다.
        스펙 예시: 
        {
            "AgentApp_1": {"type": "app_node", "location": "local", "edges": ["PolicyNode_1", "Linker_1"]},
            "PolicyNode_1": {"type": "app_node", "location": "local", "edges": []},
            "Linker_1": {"type": "logic_node", "location": "remote", "edges": ["Inversion_1"]}
        }
        """
        log.info("[Organizer] 통합 위상 구조 맵핑을 시작합니다...")

        ## 통합 정점(Unified Node) 생성 및 레지스트리 등록
        for node_id, spec in topology_spec.items():
            node_type = spec.get("type")
            
            ## 인스턴스 생성 로직 (팩토리 패턴 생략)
            instance = self._create_instance_by_type(node_type, node_id)
            unified_node = AuraNode(node_id, instance)
            
            if spec.get("location") == "local":
                self.local_registry[node_id] = unified_node
            
        ## 경계(Boundary) 기반 엣지(Edge) 연결
        for node_id, spec in topology_spec.items():
            source_node = self.local_registry.get(node_id)
            if not source_node:
                continue

            for target_id in spec.get("edges", []):
                target_spec = topology_spec.get(target_id, {})
                
                ## 목적지 노드의 위치에 따라 경계 결정
                if target_spec.get("location") == "local":
                    ## DOM 트리나 로컬 파이프라인의 수직/수평 연결
                    source_node.attach_boundary(target_id, self.local_boundary)
                    log.info(f"[Edge Bound] {node_id} --(LocalBoundary)--> {target_id}")
                else:
                    # 분산 환경으로 나가는 연결
                    if not self.remote_boundary:
                        raise RuntimeError("원격 경계를 형성하려면 Redis Pool이 필요합니다.")
                    source_node.attach_boundary(target_id, self.remote_boundary)
                    log.info(f"[Edge Bound] {node_id} --(RemoteBoundary)--> {target_id}")

        return self.local_registry

    def _create_instance_by_type(self, node_type: str, name: str) -> Any:
        """타입에 따라 기존 GanNode 기반 앱 노드나 Topos 기반 로직 노드를 생성"""
        from hand.config.app import AgentApp
        from hand.config.policy import PolicyNode
        
        if node_type == "agent_app":
            return AgentApp(name)
        elif node_type == "policy_node":
            return PolicyNode(name)
        elif node_type == "logic_node":
            return StateNode(spec={"name": name})
        return None