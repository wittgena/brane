# hub.sphere.observer.prom
## @lineage: sphere.observer.prom
## @lineage: meta.sphere.observer.prom
## @lineage: bound.sphere.observer.prom
## @lineage: gov.sphere.observer.prom
## @lineage: iso.sphere.observer.prom
## @lineage: bound.observer.cloud.prom
## @lineage: iso.sphere.cloud.prom
import asyncio
from typing import Dict, Any, List
from arch.proto.event.psi import PsiEvent
from arch.contract.interface import IPhaseAtor, IPhaseField
from arch.proto.event.bus import AsyncEventBus
from watcher.plane.emitter import get_logger
from arch.contract.registry.unified import contract
from phase.bind.client.prom import PrometheusClient 

log = get_logger("receptor.prom")

@contract.ator("prom.receptor")
class PromReceptor(IPhaseAtor):
    """
    @role: Φ(ext) → Φ(int) Transducer
    @desc: Prometheus 매트릭을 수집하여 시스템 내부 Field의 Tension으로 변환/주입하는 에이전트
    """
    def __init__(self, ator_id: str, prom_url: str = "http://prometheus:9090", metric_specs: List[Dict] = None, **kwargs):
        self._id = ator_id
        self._state = "IDLE"
        self.prom_url = prom_url
        self.client = None
        
        # 선언적으로 주입받은 메트릭 스펙 (없을 시 기본값)
        self.metric_specs = metric_specs or [
            {"name": "cpu_usage", "promql": "rate(container_cpu_usage_seconds_total[1m])", "resource_key": "pod"}
        ]
        self.max_emit = kwargs.get("max_emit", 50)

    @property
    def ator_id(self) -> str: return self._id
    
    @property
    def state(self) -> str: return self._state
    
    def set_state(self, new_state: str) -> None: self._state = new_state

    async def _initialize_client(self):
        """이벤트 루프 내 지연 초기화"""
        if self.client is None:
            self.client = PrometheusClient(base_url=self.prom_url)
            log.info(f"[emitter] Connected to Prometheus at {self.prom_url}")

    async def react(self, event: PsiEvent, field: IPhaseField, bus: AsyncEventBus) -> None:
        # 1. 단일 전역 시계(Global Clock)에 동기화
        if event.carrier.kind not in ["TICK", "SYSTEM_TICK"]:
            return

        await self._initialize_client()

        # 2. 비동기 쿼리 병렬 실행
        tasks = [self.client.query(spec["promql"]) for spec in self.metric_specs]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        emit_count = 0
        for spec, results in zip(self.metric_specs, results_list):
            if isinstance(results, Exception):
                log.error(f"PromQL Query failed for {spec['name']}: {results}")
                continue

            for r in results:
                if emit_count >= self.max_emit: 
                    break
                
                # 프로메테우스 결과 파싱
                val = float(r["value"][1])
                labels = r["labels"]
                resource_id = labels.get(spec["resource_key"], "global")
                
                # 3. 데이터 주입 (Φ_ext -> Φ_int)
                # Field 내에 해당 노드(Pod)가 없다면 동적으로 생성
                if resource_id not in field.nodes_state:
                    field.nodes_state[resource_id] = {"state": "NORMAL", "tension": 0.0}
                
                node_data = field.nodes_state[resource_id]
                
                # 메트릭 원본 저장
                node_data[spec["name"]] = val
                
                # [합성 로직] 외부 메트릭을 시스템 내부의 '모순(Tension)' 에너지로 치환
                # 예: CPU 사용량을 0~100 사이의 텐션 값으로 매핑
                if spec["name"] == "cpu_usage":
                    node_data["tension"] = val * 100.0 
                    
                emit_count += 1
                
        self.set_state("SYNCED")
        log.debug(f"[emitter] Digested {emit_count} metrics into Systemic Field.")