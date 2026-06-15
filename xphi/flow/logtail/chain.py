# xphi.flow.logtail.chain
## @lineage: meta.xor.task.trace.logtail.chain
import asyncio
import httpx
import time
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod

from arch.proto.event.psi import PsiEvent, PsiCarrier, CarrierType, PhaseField
from arch.contract.interface import IEventBus

from phase.runtime.daemon import AbstractDaemon
from phase.bind.resolver import resolve_path

from watcher.plane.emitter import get_emitter

log = get_emitter('logtail.chain')

CHAIN_WORKSPACE = resolve_path("workspace") / "chain_state"
CHAIN_WORKSPACE.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = CHAIN_WORKSPACE / "contract_registry.jsonl"

SEED_VECTORS = [
    ## deep.topology (온체인 상태 동역학 및 유동성 왜곡)
    ('metrics:tvl_spike metrics:revenue_zero ("flash loan" OR "liquidity vacuum" OR "reentrancy potential")', 'state-liquidity-fracture'),
    ('metrics:active_wallets > 10000 metrics:avg_tx_value < 1.0 ("wash trading" OR "circular transfer")', 'topology-sybil-swarm'),

    ## structural.resonance (다중 에이전트/봇의 상호작용 및 합의 붕괴)
    ('protocol:bridge event:state_desync ("message relayer timeout" OR "proof verification delay")', 'async-bridge-desync'),
    ('tokenomics:points_program ("snapshot imminent" OR "TGE expectation" OR "artificial velocity")', 'resonance-farming-attractor'),

    ## potential.driven (자본 추출/차익 거래 가능성이 내포된 구조적 결함)
    ('state:vulnerable label:airdrop_farming -label:audited ("oracle manipulation" OR "slippage bypass")', 'potential-arbitrage-vector'),
    ('label:incentivized_testnet metrics:bot_ratio > 0.8 ("sybil defense failure" OR "bounty extraction")', 'potential-bounty-drain'),
]

def load_processed_contracts() -> set:
    processed = set()
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        processed.add(data.get("contract_id"))
                    except json.JSONDecodeError:
                        continue
    return processed

def append_to_registry(target_data: Dict[str, Any]):
    record = {
        "contract_id": target_data['contract_id'],
        "tag": target_data['tag'],
        "protocol": target_data['protocol'],
        "chain": target_data['chain'],
        "explorer_url": f"https://{target_data['chain']}scan.io/address/{target_data['contract_id'].split('-')[1]}",
        "metrics": target_data.get('metrics', {}),           # 추가: TVL, Bot 비율 등
        "diagnosis": target_data.get('summary', {}),         # 추가: LLM의 구조적 요약
        "potential": target_data.get('capital_potential'),
        "timestamp": int(time.time())
    }
    with open(REGISTRY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

class ChainEventBus(IEventBus):
    async def publish(self, event: PsiEvent) -> None:
        log.info(f"\n## @internal.field: 온체인 변곡점 수신: {event.carrier.tag} (Tick: {event.tick})")
        payload = event.carrier.payload
        log.info(f"  - Payload (새로 포착된 특이점) : {len(payload)}건")
        
        for i, target in enumerate(payload, 1):
            append_to_registry(target)  # 변경된 함수 호출
            
            metrics = target.get('metrics', {})
            summary = target.get('summary', {})
            
            log.info(f"    {i}. [{target['tag']}] {target['protocol']} ({target['chain']})")
            log.info(f"        ├─ Potential : {target.get('capital_potential')}")
            log.info(f"        ├─ Metrics   : TVL ${metrics.get('tvl', 0):,} | Bot Ratio: {metrics.get('bot_ratio', 0)*100}%")
            log.info(f"        └─ Diagnosis : {summary.get('cause', 'N/A')} -> {summary.get('extraction_vector', 'N/A')}")
        log.info("=" * 70)

    def subscribe(self, ator: Any, predicate: Callable) -> None:
        pass

class ChainAtor(AbstractDaemon):
    """@psi.observe: on-chain_hub(surface) → bus(Realignment & Extraction)"""
    
    def __init__(self, bus: IEventBus, scan_interval: int = 45):
        super().__init__("ingest.chain")
        self.bus = bus
        self.scan_interval = scan_interval
        self.processed_contracts = load_processed_contracts()
        self.target_vectors = SEED_VECTORS

    def _extract_capital_potential(self, tvl: float, bot_ratio: float, has_airdrop: bool) -> str:
        """@desc: 구조적 왜곡 속에서 자본 추출(Arbitrage/Bounty)의 가능성을 정량화"""
        if has_airdrop and bot_ratio > 0.7:
            return "Sybil 침투 최적화 (Airdrop Drain 가능)"
        if tvl > 1000000 and bot_ratio > 0.9:
            return "유동성 신기루 (Wash Trade 구조적 허점 존재)"
        return "관측 위주 (자본 밀도 낮음)"

    def _generate_contract_id(self, chain: str, address: str) -> str:
        """@desc: 체인과 주소의 조합으로 고유 ID 생성"""
        return f"{chain}-{address[-6:]}-{int(time.time()*1000)}"

    async def _summarize_with_surgent(self, protocol: str, metrics: Dict) -> Dict[str, str]:
        # LLM 또는 메타 분석기를 통한 온체인 상태 동역학 요약 (Simulated)
        await asyncio.sleep(0.5) 
        return {
            "symptom": "TVL과 트랜잭션의 비정상적 디커플링 현상",
            "cause": "Airdrop 스냅샷을 노린 저차원 Sybil 군집의 상태 공간 장악",
            "extraction_vector": "스마트 컨트랙트의 상태 롤백 혹은 가스비 최적화 차익거래 경로 열려있음"
        }

    async def run(self):
        self.log.info(f"{self.name} 가동. 온체인 위상 표면(On-chain Surface) 스캔을 시작합니다.")
        headers = {
            "User-Agent": "Surgent-ChainProber/2.0",
            "Accept": "application/json"
        }

        # 예시: DefiLlama, Dune, 혹은 커스텀 Web3 인덱서 API 엔드포인트
        api_base = "https://api.mock-chain-indexer.com/v1/protocols/anomalies"

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            while self.running:
                try:
                    for query, query_tag in self.target_vectors:
                        if not self.running: break
                        
                        self.log.info(f"위상 왜곡 탐색 중: [{query_tag}] {query}")
                        # 실제 구현 시에는 GraphQL이나 파라미터화된 쿼리 사용
                        target_url = f"{api_base}?vector={query}"
                        
                        # 시뮬레이션을 위한 Mock 데이터 분기 (실제 API 요청 시 try-except로 처리)
                        # response = await client.get(target_url) 
                        await asyncio.sleep(1.5) # API 딜레이 모사
                        
                        # Mock Response 처리 (실제로는 response.json() 사용)
                        mock_items = [
                            {"protocol": "ZK-Sync-DEX", "chain": "ethereum", "address": "0x123...abc", "tvl": 5000000, "bot_ratio": 0.85, "airdrop_flag": True},
                            {"protocol": "LayerZero-Bridge", "chain": "arbitrum", "address": "0x456...def", "tvl": 12000000, "bot_ratio": 0.4, "airdrop_flag": False}
                        ]

                        valid_targets = []
                        
                        for item in mock_items:
                            c_id = self._generate_contract_id(item["chain"], item["address"])
                            if c_id in self.processed_contracts:
                                continue
                            
                            potential = self._extract_capital_potential(item["tvl"], item["bot_ratio"], item["airdrop_flag"])
                            
                            # 자본적 유의미함이 있거나, 순수 구조적 왜곡이 심각한 경우 수집
                            if "관측 위주" not in potential or "fracture" in query_tag:
                                summary = await self._summarize_with_surgent(item["protocol"], item)
                                valid_targets.append({
                                    "contract_id": c_id,  
                                    "tag": query_tag,
                                    "protocol": item["protocol"],
                                    "chain": item["chain"],
                                    "capital_potential": potential,
                                    "summary": summary
                                })
                                self.processed_contracts.add(c_id)
                        
                        if valid_targets:
                            carrier = PsiCarrier(
                                kind="chain_anomaly",
                                tag="state_acquired",
                                payload=valid_targets,
                                carrier_type=CarrierType.FIXED,
                                target_field=PhaseField.LOCAL
                            )

                            event = PsiEvent(
                                event_id=f"psi_chain_{int(time.time()*1000)}",
                                parent_id=None,
                                source_id=self.name.lower(),
                                scope="global",
                                tick=int(time.time()),
                                carrier=carrier
                            )
                            await self.bus.publish(event)
                        
                        await asyncio.sleep(3) # 벡터 간 쿨다운
                        
                    if self.running:
                        await asyncio.sleep(self.scan_interval)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.log.error(f"온체인 스캔 루프 내 물리적 에러: {str(e)}")
                    await asyncio.sleep(5)

async def main():
    bus = ChainEventBus()
    ator = ChainAtor(bus=bus, scan_interval=60)

    log.info("===")
    log.info("## Chain State Ingestor")
    log.info("===")
    await ator.start()
    try:
        while True:
            await asyncio.sleep(3600) 
    except KeyboardInterrupt:
        pass
    finally:
        await ator.stop()

if __name__ == "__main__":
    asyncio.run(main())