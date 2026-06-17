# arch.topic.modeler
## @lineage: arch.model.topic.modeler
## @lineage: arch.project.topic.modeler
## @lineage: xphi.code.topic.modeler
## @lineage: topos.arch.code.topic.modeler
## @lineage: arch.model.code.topic.modeler
"""@role: Topic Clustering Engine for Code Topos (Bound Interface Integrated)"""
import sys
import json
import re
import os
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict, Counter
from gensim import corpora, models
from watcher.plane.emitter import get_emitter
from arch.topic.registry import TopicMap, TopicMetadata, ToposSpace, CoreModuleInfo
from phase.bind.resolver import find_current_self, resolve_path
from arch.xor.block.parser.topos import ToposAstParser

log = get_emitter("topic.modeler")

try:
    WORKSPACE_ROOT = find_current_self()
    OUTPUT_ROOT = resolve_path("code") / "topic"
except Exception as e:
    log.error(f"[Critical] 시스템 위상 로드 실패: {e}")
    sys.exit(1)

# Parameters
REPOS = ['subst', 'theoria']
NUM_spaces = 5
TOP_WORDS = 10
TOP_DOCS = 10
NO_BELOW = 2
NO_ABOVE = 0.6
SCORE_THRESHOLD = 0.1

CODE_STOPWORDS = {
    'def', 'class', 'import', 'from', 'return', 'self', 'if', 'in', 'for', 'while',
    'try', 'except', 'with', 'as', 'pass', 'none', 'true', 'false', 'and', 'or', 'not',
    'args', 'kwargs', 'init', 'str', 'int', 'list', 'dict', 'set', 'get', 'main', 'log.info'
}

def extract_text_from_md(section) -> str:
    texts = [section.title]
    for child in section.children:
        if hasattr(child, 'text'): 
            texts.append(child.text)
    for sub in section.subsections:
        texts.append(extract_text_from_md(sub))
    return " ".join(texts)

def load_py_topology(base_dir: Path):
    docs, paths = [], []
    py_files = list(base_dir.rglob("*.py"))
    
    for path in py_files:
        try:
            parser = ToposAstParser(path)
            md_doc = parser.parse()
            
            # 변경: 단순 문자열 변수로 텍스트 누적
            doc_text = ""
            for sec in md_doc.sections:
                doc_text += extract_text_from_md(sec) + " "
                
            if doc_text.strip():
                docs.append(doc_text)
                paths.append(path.relative_to(base_dir).as_posix())
        except Exception as e:
            log.warning(f"[Skip] {path.name}: {e}")
            
    return docs, paths

## Phase Space Clustering (LDA)
def extract_unique_interfaces(topics):
    keyword_counter = Counter()
    topic_keywords = {}
    for tid, info in topics.items():
        kws = set(info["topos_markers"])
        topic_keywords[tid] = kws
        keyword_counter.update(kws)
        
    unique_variants = {}
    shared_interfaces = sorted([k for k, c in keyword_counter.items() if c > 1])
    
    for tid, kws in topic_keywords.items():
        unique = sorted([k for k in kws if keyword_counter[k] == 1])
        unique_variants[tid] = unique
        
    return unique_variants, shared_interfaces

def tokenize_topos(text: str):
    pattern = r'[@Φ∂ΔΣ]+[a-zA-Z_0-9]*|=>|->|[a-zA-Z_][a-zA-Z_0-9]+'
    raw_tokens = re.findall(pattern, text)
    processed_tokens = []
    for t in raw_tokens:
        norm_t = t if any(sym in t for sym in "@Φ∂ΔΣ=>->") else t.lower()
        if (len(norm_t) > 1 or norm_t in "Φ∂ΔΣ") and norm_t.lower() not in CODE_STOPWORDS:
            processed_tokens.append(norm_t)
    return processed_tokens

def build_topos_structure(lda, corpus, paths) -> dict:
    """LDA 결과를 interface 규격에 맞는 dict 구조로 빌드"""
    topic_to_docs = defaultdict(list)
    for i, bow in enumerate(corpus):
        scores = lda.get_document_topics(bow)
        for tid, score in scores:
            if score >= SCORE_THRESHOLD:
                topic_to_docs[int(tid)].append((float(score), paths[i]))
    
    spaces = {}
    for tid in range(lda.num_topics):
        words = [w for w, _ in lda.show_topic(tid, topn=TOP_WORDS)]
        top_docs = sorted(topic_to_docs[tid], key=lambda x: -x[0])[:TOP_DOCS]
        spaces[f"Phase_{tid}"] = {
            "topos_markers": words,
            "core_modules": [
                {"path": p, "density": round(float(s), 3)} for s, p in top_docs
            ]
        }
    
    module_map = {}
    for i, bow in enumerate(corpus):
        scores = lda.get_document_topics(bow)
        if scores:
            dominant = max(scores, key=lambda x: x[1])
            module_map[paths[i]] = {
                "dominant_phase": f"Phase_{int(dominant[0])}",
                "alignment_score": round(float(dominant[1]), 3)
            }
    return spaces, module_map

def run_topos_clustering(repo_name: str):
    repo_path = WORKSPACE_ROOT / repo_name
    if not repo_path.exists(): return

    log.info(f"Targeting Repository: [{repo_name}]")
    docs, paths = load_py_topology(repo_path)
    if not docs: return

    tokenized = [tokenize_topos(doc) for doc in tqdm(docs, desc=f"Tokenizing [{repo_name}]")]
    dictionary = corpora.Dictionary(tokenized)
    dictionary.filter_extremes(no_below=NO_BELOW, no_above=NO_ABOVE)
    if len(dictionary) == 0: return
        
    corpus = [dictionary.doc2bow(text) for text in tokenized]
    lda = models.LdaModel(corpus, num_topics=NUM_spaces, id2word=dictionary, passes=15, random_state=42)
    
    raw_spaces, module_map = build_topos_structure(lda, corpus, paths)
    keyword_counter = Counter()
    for info in raw_spaces.values():
        keyword_counter.update(info["topos_markers"])
    
    shared_interfaces = sorted([k for k, c in keyword_counter.items() if c > 1])
    unique_variants = {
        tid: sorted([k for k in info["topos_markers"] if keyword_counter[k] == 1])
        for tid, info in raw_spaces.items()
    }

    ## TopicMap 모델을 통한 데이터 최종 결속(Binding)
    topic_map = TopicMap(
        metadata=TopicMetadata(
            repository=repo_name,
            analyzed_modules=len(docs),
            global_interfaces=shared_interfaces,
            local_variants=unique_variants
        ),
        spaces={ tid: ToposSpace(**info) for tid, info in raw_spaces.items() },
        module_alignment=module_map
    )
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_ROOT / f"{repo_name}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(topic_map.model_dump(), f, indent=2, ensure_ascii=False)
    
    ## [Output Projection] TopicMap 객체를 참조하여 분석 결과 가독 출력
    log.info(f"\n## [Code Topos] Subsystem Phase Space: {topic_map.metadata.repository.upper()}")

    g_interfaces = topic_map.metadata.global_interfaces
    bus_preview = ", ".join(g_interfaces[:10]) + (" ..." if len(g_interfaces) > 10 else "")
    log.info(f"- Global Interfaces (System Bus): {bus_preview}")
    log.info("\n- Detected Phase Spaces (Subsystems):")
    for pid, phase in topic_map.spaces.items():
        markers = ", ".join(phase.topos_markers)
        log.info(f"  [{pid}] Markers: {markers}")
        
        if phase.core_modules:
            primary_core = phase.core_modules[0] # 첫 번째 모듈이 가장 밀도가 높음
            log.info(f"      Primary Core: {primary_core.path} (Density: {primary_core.density})")
    log.info(f"Topos for [{repo_name}] saved to: {output_file}")

def main():
    for repo in REPOS:
        run_topos_clustering(repo)

if __name__ == "__main__":
    main()