# arch.topic.pos.sensor
## @lineage: arch.model.pos.sensor
## @lineage: topos.model.pos.sensor
"""
@role: Class-based Boundary-driven Model Binder
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from konlpy.tag import Mecab

class PosSensor:
    """∂Φ(Bound) 감지 및 Φ seed 추출을 담당하는 센서 계층"""
    
    ## axis.map 
    POS_MAP = {
        "적": {"group": "structural", "pos": "XSN", "group_desc": "phi_x 구조 귀속자 - 개념 고정 / 안정화"},
        "의": {"group": "possessive", "pos": "JKG", "group_desc": "dPhi 경계 귀속 - 소속 / 종속 구조"},
        "을": {"group": "objective", "pos": "JKO", "group_desc": "psi_i 작용 대상 - 의미 흐름 목적지"},
        "를": {"group": "objective", "pos": "JKO", "group_desc": "psi_i 작용 대상 - 의미 흐름 목적지"},
        "이": {"group": "subject", "pos": "JKS", "group_desc": "psi_i 발생원 - 작용 주체"},
        "가": {"group": "subject", "pos": "JKS", "group_desc": "psi_i 발생원 - 작용 주체"},
        "은": {"group": "topic", "pos": "JX", "group_desc": "위상 attractor - 문맥 중심점"},
        "는": {"group": "topic", "pos": "JX", "group_desc": "위상 attractor - 문맥 중심점"},
        "에서": {"group": "ablative", "pos": "JKB", "group_desc": "출발 경계 (from)"},
        "에": {"group": "locative", "pos": "JKB", "group_desc": "위치 고정점 (at / in)"},
        "으로": {"group": "directional", "pos": "JKB", "group_desc": "방향 유도 (to / toward)"},
        "로": {"group": "directional", "pos": "JKB", "group_desc": "방향 유도 (to / toward)"},
        "와": {"group": "instrumental", "pos": "JC", "group_desc": "수단 / 매개 / 동반"},
        "과": {"group": "instrumental", "pos": "JC", "group_desc": "수단 / 매개 / 동반"},
        "로써": {"group": "instrumental", "pos": "JKB", "group_desc": "수단 / 매개 / 동반"},
        "까지": {"group": "terminative", "pos": "JX", "group_desc": "종착점 (endpoint)"},
        "부터": {"group": "originative", "pos": "JX", "group_desc": "시작점 (source)"},
    }

    def __init__(self, dic_path="/opt/homebrew/lib/mecab/dic/mecab-ko-dic"):
        try:
            self.mecab = Mecab(dic_path)
        except Exception as e:
            log.warn(f"Mecab load failed: {e}")
            self.mecab = None

    def sense(self, text):
        """텍스트에서 (phi_seed, boundary_group) 쌍을 추출"""
        if not self.mecab: return []
        tokens = self.mecab.pos(text)
        candidates = []
        for i in range(len(tokens) - 1):
            cur_word, cur_tag = tokens[i]
            next_word, next_tag = tokens[i+1]
            meta = self.POS_MAP.get(next_word)
            if cur_tag.startswith("NN") and meta and next_tag == meta["pos"]:
                normalized_node = cur_word.strip().lower()
                candidates.append((cur_word, meta["group"]))
        return candidates
