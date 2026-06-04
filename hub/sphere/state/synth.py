# hub.sphere.state.synth
## @lineage: sphere.state.manager.synth
## @lineage: nexus.manager.self.synth
## @lineage: nexus.swarm.self.synth
## @lineage: swarm.self.synth
## @lineage: hub.spec.synth
## @lineage: scripts.xyz.xor.spec.node.synth
## @lineage: abcd.node.synth
import sys
import json
import time

class SelfSynth:
    """@desc: 외부에서 주입된 JSON spec을 동적으로 샌드박스 내에서 번역하고 실행"""
    def __init__(self, spec_path: str):
        self.spec_path = spec_path
        self.accumulated = 0

    def ingest_and_catalyze(self):
        try:
            with open(self.spec_path, 'r') as f:
                spec = json.load(f)
        except Exception as e:
            print(f"Spec read failure: {e}")
            sys.exit(1)

        ## TTL Check
        current_time = int(time.time())
        if current_time - spec.get("created_at", 0) > (spec.get("ttl_ms", 0) / 1000):
            print("Spec expired. Decaying.")
            sys.exit(0)

        env = {
            "__builtins__": __builtins__,
            "context": spec.get("context", {})
        }

        ## code-as-data
        try:
            code_obj = compile(spec["logic"], "<synthetic>", "exec")
            exec(code_obj, env)
            if "catalyze" in env:
                yield_delta = env["catalyze"](env["context"])
                self.accumulated += yield_delta
                print(f"Reaction complete. Yield: {yield_delta} | Total: {self.accumulated}")
        except Exception as e:
            print(f"rejection during catalysis: {e}")
            sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python self <spec.json>")
        sys.exit(1)
        
    node = SelfSynth(sys.argv[1])
    node.ingest_and_catalyze()