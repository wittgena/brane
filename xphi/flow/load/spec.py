# xphi.flow.load.spec
## @lineage: xphi.spec.loader
## @lineage: bound.node
import os
import sys
import json
import argparse
import requests
import numpy as np
from requests.exceptions import Timeout, ConnectionError
from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_emitter

class SpecLoader:
    """@desc: Class-based boundary actuator preventing global-scope import crashes"""
    def __init__(self):
        self.log = get_emitter("self.node", phase="theoria")
        self.initialized = False
        
        ## @state: Structural attributes
        self.stream_source = None
        self.execute_target = None
        self.action_payload = None
        self.svm_weights = None
        self.svm_bias = None
        self.cap = 59
        self.timeout_sec = 3.0
        self.current = 0

    def _resolve_paths(self, spec_name: str):
        """@topos: Resolve storage mapping limits cleanly inside a method context"""
        try:
            self.self_root = find_current_self()
            self.spec_root = resolve_path('spec')
            self.logtail_file = self.spec_root / "theoria" / spec_name
        except Exception as e:
            self.log.error(f"Missing boundary reference: {e}")
            sys.exit(1)

    def load_spec(self, spec_name: str = "self.json") -> bool:
        """@injection: Inject domain mapping values. Returns false instead of killing the system on import"""
        self._resolve_paths(spec_name)
        
        if not self.logtail_file.exists():
            self.log.error(f"[Config] Target spec file missing: {self.logtail_file.name}")
            return False
            
        try:
            with open(self.logtail_file, 'r', encoding='utf-8') as f:
                instruction = json.load(f)
                
            self.stream_source = instruction['source_endpoint']
            self.execute_target = instruction['target_endpoint']
            self.action_payload = instruction['action_template']
            
            ## @math: Dimension mapping
            self.svm_weights = np.array(instruction['svm_w'], dtype=float)
            self.svm_bias = float(instruction['svm_b'])
            
            ## @meta: Param allocation
            self.cap = int(instruction.get('cap', 59))
            self.timeout_sec = float(instruction.get('timeout_ms', 3000)) / 1000.0
            
            self.initialized = True
            return True
            
        except (KeyError, json.JSONDecodeError) as e:
            self.log.error(f"Invalid Topos Coordinate format: {e}")
            return False

    def is_over_hyperplane(self, feature_vector: list) -> bool:
        """@logic: Deterministic classification matrix multiplication."""
        if not self.initialized:
            return False
        vec = np.array(feature_vector, dtype=float)
        
        if vec.shape != self.svm_weights.shape:
            return False
            
        return np.dot(self.svm_weights, vec) + self.svm_bias > 0

    def loop(self, spec_name: str = "self.json"):
        """@flow: Runtime execution surface layer."""
        if not self.initialized and not self.load_spec(spec_name):
            self.log.error("Node runtime aborted due to initialization failure.")
            sys.exit(1)

        self.log.info(f"## @init: Surgent Node Active. ATP Target: {self.cap}")
        with requests.Session() as session:
            try:
                response = session.get(self.stream_source, stream=True, timeout=self.timeout_sec)
                for raw_line in response.iter_lines():
                    if not raw_line: continue
                    
                    try:
                        data = json.loads(raw_line.decode('utf-8'))
                        vector_signal = data.get("v_state", [])
                    except json.JSONDecodeError:
                        continue 
                    
                    if not vector_signal: continue
                    if self.is_over_hyperplane(vector_signal):
                        self.log.info("## @reflex: Signal crossed hyperplane. Executing payload.")
                        resp = session.post(self.execute_target, json=self.action_payload, timeout=self.timeout_sec)
                        if resp.status_code == 200:
                            acquired = resp.json().get("yield", 0)
                            self.current += acquired
                            self.log.info(f"[Yield] Acquired: {acquired} | Total: {self.current}/{self.cap}")
                            
                            if self.current >= self.cap:
                                self.log.info(f"[Hibernate] Cap ({self.cap}) reached. Shutting down.")
                                sys.exit(0)
                        else:
                            raise ConnectionError(f"Target rejected with status {resp.status_code}")
                            
            except (Timeout, ConnectionError) as e:
                self.log.error(f"Env friction ({e}). Decaying.")
                sys.exit(1)
            except Exception as e:
                self.log.error(f"Unknown Anomaly ({e}). Self-destructing.")
                sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="self.json", help="Target spec JSON file name")
    args, _ = parser.parse_known_args()
    
    ## Instance instantiation and runtime triggering
    node = SpecLoader()
    node.loop(spec_name=args.spec)