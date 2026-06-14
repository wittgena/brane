# bound.token.encoding
## @lineage: channel.bridge.litellm.default_encoding
import tiktoken
import time
import random
from functools import lru_cache
from watcher.plane.emitter import get_emitter

log = get_emitter("config.encoding")

@lru_cache(maxsize=1)
def get_default_encoding(model_name: str = "cl100k_base") -> tiktoken.Encoding:
    """
    tiktoken의 내장 표준 캐싱 매커니즘을 사용합니다.
    (기본적으로 OS의 표준 임시 디렉토리를 알아서 활용합니다)
    """
    max_retries = 5
    retry_delay = 0.1  

    for attempt in range(max_retries):
        try:
            # 외부 경로 주입 없이 순수하게 표준 API만 호출합니다.
            return tiktoken.get_encoding(model_name)
            
        except (FileExistsError, OSError) as e:
            # Gunicorn 등 다중 워커가 동시에 최초 부팅될 때 
            # OS 임시 폴더에 캐시 파일을 동시에 쓰려다 발생하는 충돌(Race Condition) 방어
            if attempt == max_retries - 1:
                log.error(f"Failed to load tiktoken encoding '{model_name}' after {max_retries} attempts. Error: {e}")
                raise
            
            delay = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
            log.debug(f"[Encoding] Cache collision. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
            time.sleep(delay)