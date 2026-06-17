# arch.contract.context.prompt.input
## @lineage: arch.context.prompt.input
## @lineage: cognitive.context.prompt.input
from dataclasses import dataclass
from typing import Dict, List
import argparse
import json

## @data.contracts
@dataclass
class InputBundle:
    anchor: str
    query: str
    state: List[str]
    evidence: List[str]
    max_tokens: int = 4000

@dataclass
class ResolvedContext: # AssembledContext -> ResolvedContext로 위상적 의미 강화
    anchor: str
    query: str
    state: List[str]
    evidence: List[str]

# 불필요했던 define_bound 함수 완전 제거 (InputBundle을 직접 활용)

## @state_consolidation
def consolidate_state(states: List[str], max_items: int = 8) -> List[str]:
    """State compression with order preservation."""
    unique = []
    seen = set()

    for s in states:
        s_clean = s.strip()
        if s_clean and s_clean not in seen:
            unique.append(s_clean)
            seen.add(s_clean)

    return unique[:max_items]

## @evidence_selection
def score_evidence(text: str) -> int:
    """Simple structural scoring heuristic."""
    score = 0
    if "def " in text: score += 3
    if "class " in text: score += 3
    if "IR" in text or "Anchoring" in text: score += 2
    if len(text) > 500: score += 1
    return score

def select_evidence(evidences: List[str], max_items: int = 6) -> List[str]:
    """Priority-based evidence selection."""
    return sorted(evidences, key=score_evidence, reverse=True)[:max_items]

## @budget_resolution
def estimate_tokens(texts: List[str]) -> int:
    """
    단순 글자 수를 토큰 수로 근사치 변환 
    (문자열 길이의 합을 3으로 나누어 보수적인 토큰 크기로 근사)
    """
    return sum(len(x) for x in texts) // 3

def resolve_budget(bundle: InputBundle,
                   state: List[str],
                   evidence: List[str]) -> ResolvedContext:
    """
    Budget logic:
    1. Anchor NEVER removed
    2. Query NEVER removed
    3. Evidence reduced first
    4. State reduced second
    """
    anchor = bundle.anchor.strip()
    query = bundle.query.strip()
    max_tokens = bundle.max_tokens

    def get_current_tokens() -> int:
        return estimate_tokens([anchor, query] + state + evidence)

    # 1. Reduce evidence first
    while evidence and get_current_tokens() > max_tokens:
        evidence.pop()

    # 2. Then reduce state
    while state and get_current_tokens() > max_tokens:
        state.pop()

    return ResolvedContext(
        anchor=anchor,
        query=query,
        state=state,
        evidence=evidence
    )

## @projection
def render_messages(context: ResolvedContext) -> List[Dict]:
    """Strict hierarchical rendering (구 emit_ordered)."""
    messages = []

    # 1. Anchor (System Persona/Rules)
    if context.anchor:
        messages.append({
            "role": "system",
            "content": f"@anchor: {context.anchor}"
        })

    # 2. State (Runtime Context)
    if context.state:
        messages.append({
            "role": "system",
            "content": "@state.context:\n" + "\n".join(context.state)
        })

    # 3. Evidence (Knowledge/Blocks)
    if context.evidence:
        messages.append({
            "role": "system",
            "content": "primary.target:\n" + "\n\n".join(context.evidence)
        })

    # 4. Query (항상 마지막 User 메시지)
    messages.append({
        "role": "user",
        "content": context.query
    })
    return messages

## @entry
def build_prompt(bundle: InputBundle) -> List[Dict]:
    """순수 데이터 파이프라인의 진입점 (기존 entry -> build_prompt 로 변경하여 연결 복구)"""
    state = consolidate_state(bundle.state)
    evidence = select_evidence(bundle.evidence)

    # Dictionary 래핑 없이 bundle 자체를 넘겨 투명한 흐름 보장
    resolved = resolve_budget(bundle, state, evidence)

    return render_messages(resolved)

## @main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", default="")
    parser.add_argument("--query", required=True)
    parser.add_argument("--max_tokens", type=int, default=4000)

    args = parser.parse_args()

    bundle = InputBundle(
        anchor=args.anchor,
        query=args.query,
        state=[],
        evidence=[],
        max_tokens=args.max_tokens
    )

    messages = build_prompt(bundle)
    print(json.dumps(messages, indent=2, ensure_ascii=False))

## @runtime
if __name__ == "__main__":
    main()