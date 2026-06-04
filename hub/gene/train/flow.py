# hub.gene.train.flow
## @lineage: hub.memory.train.flow
## @lineage: scripts.xyz.xor.code.context.train.flow
## @lineage: spec.code.train.flow
## @lineage: spec.script.train.flow
import dspy
from dspy.teleprompt import MIPROv2
from foldbox.runtime.flow.learn import ResonanceTranscription, TensionEvaluation

class AlignerBrain(dspy.Module):
    """MIPROv2가 파고들 수 있는 DSPy 전용 뇌 구조 (Facade)"""
    def __init__(self):
        super().__init__()
        self.projector = dspy.ChainOfThought(ResonanceTranscription)
        self.evaluator = dspy.ChainOfThought(TensionEvaluation)

    def forward(self, resonance_signal):
        proj = self.projector(resonance_signal=resonance_signal)
        eval_res = self.evaluator(topology_map=proj.topology_map)
        tension = float(eval_res.tension_score) if hasattr(eval_res, 'tension_score') else 1.0
        return dspy.Prediction(topology=proj.topology_map, tension=tension)

def compile_and_extract_logos(trainset):
    """최적화 후, 지능을 순수 JSON 파일로 방출(Emit)하고 DSPy 프로세스를 종료"""
    optimizer = MIPROv2(metric=lambda g, p, trace=None: 1.0 - p.tension)
    compiled_brain = optimizer.compile(AlignerBrain(), trainset=trainset, num_trials=10)
    
    # 💡 [핵심] DSPy 객체를 메모리에 남기지 않고, 물리적 파일(JSON)로 결정화(Crystallization)
    compiled_brain.save("res/topology_brain_state.json")
    print("Optimization Complete. Brain state serialized to JSON.")

if __name__ == "__main__":
    # 이 스크립트는 런타임 서버와 무관하게 백그라운드나 CI/CD 파이프라인에서 돕니다.
    compile_and_extract_logos(mock_trainset)