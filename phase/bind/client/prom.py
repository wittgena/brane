# phase.bind.client.prom
## @lineage: phase.bound.client.prom
## @lineage: phase.reflect.client.prom
import httpx
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("prom.client")

class PrometheusClient:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    async def query(self, promql: str) -> List[Dict[str, Any]]:
        """
        실제 Prometheus /api/v1/query 엔드포인트를 호출하여 결과를 반환
        """
        url = f"{self.endpoint}/api/v1/query"
        params = {"query": promql}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, timeout=5.0)
                response.raise_for_status()
                data = response.json()
                
                ## Prometheus API 정상 응답 검증
                if data.get("status") == "success":
                    ## data["data"]["result"] 배열 반환
                    ## 형태: [{"metric": {"pod": "..."}, "value": [1612345678, "75.5"]}, ...]
                    return data["data"].get("result", [])
                else:
                    logger.warning(f"Prometheus query failed: {data}")
                    return []
                    
            except httpx.RequestError as e:
                logger.error(f"HTTP Request error while querying Prometheus: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error in Prometheus query: {e}")
                return []

    async def query_spec(self, spec: 'MetricSpec'):
        """
        정의된 MetricSpec을 기반으로 쿼리를 실행하고 규격화된 포맷으로 변환
        """
        raw_results = await self.query(spec.promql)
        formatted_results = []
        
        for item in raw_results:
            try:
                ## [적용] extractor를 통해 값 추출 (예: float(item["value"][1]))
                val = spec.extractor(item) 

                if spec.normalize:
                    val = spec.normalize(val)

                ## [개선] 원본 Prometheus 데이터의 '__name__' 레이블은 충돌을 방지하기 위해 제거
                raw_labels = item.get("metric", {})
                clean_labels = {k: v for k, v in raw_labels.items() if k != "__name__"}

                formatted_results.append({
                    "metric": spec.name,
                    "labels": clean_labels,
                    "value": val
                })
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Error extracting metric '{spec.name}': {e} | Raw data: {item}")
                
        return formatted_results