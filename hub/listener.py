# hub.listener
## @lineage: gov.hub.node.agent
import json
import logging
import subprocess
import shutil
import tarfile
from pathlib import Path
from typing import Optional
from hub.comm.broker import RedisBroker, SporeManifest
from meta.xor.residue.drop import DeadDropper

log = logging.getLogger("node_agent")

class AgentListener:
    def __init__(self, redis_uri: str, dead_drop_uri: str, work_dir: str = "./_workspace"):
        self.broker = RedisBroker(redis_uri)
        self.drop = DeadDropper(dead_drop_uri)
        self.work_dir = Path(work_dir).resolve()
        self.work_dir.mkdir(exist_ok=True)

    def start_listening(self):
        log.info("Node Agent started. Listening for tasks...")
        # 큐에서 작업을 대기 (Event-Driven)
        for raw_message, manifest in self.broker.consume_pending():
            self.process_task(manifest)

    def process_task(self, manifest: SporeManifest):
        capsule_dir = self.work_dir / f"capsule_{manifest.trial_id}"
        
        try:
            # 1. 캡슐 다운로드 및 압축 해제
            log.info(f"Downloading capsule for Trial {manifest.trial_id}...")
            tar_path = self.drop.download(manifest.capsule_uri, dest_dir=self.work_dir)
            
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=capsule_dir)
            tar_path.unlink() # 압축 파일 삭제

            # 2. ML Executor 서브프로세스 실행 (격리)
            executor_script = capsule_dir / "ml_executor.py"
            log.info(f"Executing ML task: {executor_script}")
            
            result = subprocess.run(
                ["python", str(executor_script), "--capsule", str(capsule_dir)],
                cwd=str(capsule_dir),
                capture_output=True,
                text=True
            )

            # 3. 결과 처리
            if result.returncode == 0:
                log.info(f"Trial {manifest.trial_id} ML execution successful.")
                # 성공 시 가중치를 업로드하고 ACK 처리
                weight_uri = self.drop.upload_dir(capsule_dir / "_output", prefix=f"results/{manifest.trial_id}")
                self.broker.mark_completed(manifest.trial_id, weight_uri=weight_uri, status="COMPLETED")
            else:
                log.error(f"Trial {manifest.trial_id} ML execution failed.\n{result.stderr}")
                self.broker.mark_completed(manifest.trial_id, status="FAILED", error_message=result.stderr[-500:])

        except Exception as e:
            log.exception(f"Agent-level error processing Trial {manifest.trial_id}")
            self.broker.mark_completed(manifest.trial_id, status="FAILED", error_message=str(e))
        finally:
            # 워크스페이스 정리
            if capsule_dir.exists():
                shutil.rmtree(capsule_dir, ignore_errors=True)

if __name__ == "__main__":
    agent = AgentListener(redis_uri="redis://...", dead_drop_uri="s3://...")
    agent.start_listening()