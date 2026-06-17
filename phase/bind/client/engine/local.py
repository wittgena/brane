# phase.bind.client.engine.local
import os
import time
import subprocess
import requests
import json
from arch.proto.schema.resonance import BridgeEvent
from watcher.plane.emitter import get_emitter

log = get_emitter('local.engine')
MODEL_HF = os.getenv("LLAMA_MODEL_HF", "ggml-org/gemma-3-1b-it-GGUF")
MODEL_NAME = os.getenv("LLAMA_MODEL_NAME", "gemma-3-1b-it-Q4_K_M.gguf")
SERVER_PORT = int(os.getenv("LLAMA_PORT", "8080"))

SERVER_URL = f"http://localhost:{SERVER_PORT}/v1/chat/completions"
HEALTH_URL = f"http://localhost:{SERVER_PORT}/health"

LLAMA_SERVER_CMD = [
    "llama-server",
    "-hf", MODEL_HF,
    "--port", str(SERVER_PORT),
]

class LLMEngine:
    """
    Infra layer:
    - llama-server lifecycle
    - HTTP transport
    - no structural logic
    """
    def __init__(self):
        self.model_name = MODEL_NAME
        self.server_url = SERVER_URL
        self.health_url = HEALTH_URL
        self._process = None

    def is_alive(self) -> bool:
        try:
            r = requests.get(self.health_url, timeout=2)
            return r.status_code == 200
        except Exception:
            # 상태 체크 중 발생하는 에러는 정상적인 대기 과정일 수 있으므로 디버그 레벨로 낮춤
            log.debug('[monitor] llama-server not ready yet...')
            return False

    def ensure_server(self):
        if self.is_alive():
            return

        log.info("[*] Starting llama-server process...")
        self._process = subprocess.Popen(
            LLAMA_SERVER_CMD,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(30): # 대기 시간을 좀 더 넉넉히(15->30초) 부여
            if self.is_alive():
                log.info("[+] llama-server is online.")
                return
            time.sleep(1)

        self._process.terminate()
        raise RuntimeError("llama-server failed to start within timeout.")

    def ask(self, prompt: str, callback: callable = None) -> str:
        """기존 chat을 대체/확장: 스트리밍 및 루처(Rupture) 지원"""
        self.ensure_server()

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True # 스트리밍 활성화
        }

        full_text = ""
        try:
            with requests.post(self.server_url, json=payload, stream=True, timeout=60) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line: continue
                    
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        content = line_str[6:]
                        if content == "[DONE]": break
                        
                        try:
                            # [FIX] JSON 모듈을 사용해 정상 파싱
                            chunk = json.loads(content)["choices"][0]["delta"].get("content", "")
                            if chunk:
                                full_text += chunk
                                if callback:
                                    # [FIX] analyzer가 무시하지 않도록 source="agent" 지정 
                                    # [FIX] 파편(chunk)이 아닌 누적된 전체 텍스트(full_text)를 전달
                                    callback(BridgeEvent(source="agent", content=full_text))
                        except Exception as e:
                            # [FIX] 무지성 continue 대신 파싱 에러 로깅
                            log.error(f"SSE JSON parsing error: {e}, Payload: {content}")
                            continue
        except Exception as e:
            log.error(f"Failed during LLM ask request: {e}")
            
        return full_text

    def chat(self, system_prompt: str, user_prompt: str, timeout: int = 30) -> str:
        self.ensure_server()

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        r = requests.post(self.server_url, json=payload, timeout=timeout)
        r.raise_for_status()

        data = r.json()
        return data["choices"][0]["message"]["content"]

if __name__ == "__main__":
    client = LLMEngine()
    try:
        log.info("Starting LLM Client test...")
        system_msg = "You are a concise assistant."
        user_msg = "Hello, tell me a short joke about robots."
        print(f"\n[Requesting to {MODEL_NAME}...]")
        
        response = client.chat(system_msg, user_msg)
        print(f"Response:\n{response}")
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.error(f"Test failed: {e}")
    finally:
        if client._process:
            log.info("Terminating llama-server...")
            client._process.terminate()