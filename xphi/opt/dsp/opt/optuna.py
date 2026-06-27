# xphi.opt.dsp.opt.optuna
## @lineage: bound.xor.dsp.opt.optuna
## @lineage: xor.dsp.opt.optuna
## @lineage: meta.xor.opt.optuna
# meta/xor/opt/optuna.py
from __future__ import annotations
import optuna
from typing import Any, Dict, Tuple, Optional
from watcher.plane.emitter import get_emitter

log = get_emitter(__name__)

class OptunaOptimizer:
    """
    Optuna를 활용한 Ask-and-Tell 방식의 비동기 최적화 래퍼.
    분산 환경에서의 하이퍼파라미터 튜닝을 지원합니다.
    """
    def __init__(
        self, 
        study_name: str, 
        storage_uri: Optional[str] = None, 
        direction: str = "maximize"
    ) -> None:
        self.study = optuna.create_study(
            study_name=study_name,
            storage=storage_uri,
            direction=direction,
            load_if_exists=True
        )

    def ask(self, space_schema: Dict[str, Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        """주어진 탐색 공간(space_schema)에 기반하여 새로운 파라미터 세트를 제안"""
        trial = self.study.ask()
        params = {}
        for key, config in space_schema.items():
            p_type = config.get("type")
            try:
                if p_type == "float":
                    params[key] = trial.suggest_float(
                        key, config["low"], config["high"], log=config.get("log", False)
                    )
                elif p_type == "int":
                    params[key] = trial.suggest_int(
                        key, config["low"], config["high"], step=config.get("step", 1)
                    )
                elif p_type == "categorical":
                    params[key] = trial.suggest_categorical(key, config["choices"])
                else:
                    log.warning(f"알 수 없는 파라미터 타입입니다: {p_type} for {key}")
            except Exception as e:
                log.error(f"파라미터 {key} 샘플링 중 에러 발생: {e}")
                self.study.tell(trial, state=optuna.trial.TrialState.FAIL)
                raise

        return trial.number, params

    def tell(self, trial_id: int, value: float) -> None:
        """원격 노드에서 계산된 최종 평가 점수(Elo 등)를 업데이트합니다."""
        self.study.tell(trial_id, value)
        log.debug(f"Trial {trial_id} completed with score: {value}")