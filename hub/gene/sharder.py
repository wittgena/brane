# hub.gene.sharder
## @lineage: gov.hub.gene.shader
from __future__ import annotations
import hashlib
import tempfile
from pathlib import Path
from typing import List
from arch.contract.exp.promise import future

class DataSharder:
    """
    @desc: Slices the target corpus to prevent raw data exposure and distribute compute
    @strategy: hash-based (line-level blake2b → modulo num_shards)
    @invariant: 같은 입력에 대해 항상 같은 분배. 한 라인은 정확히 한 shard에만 속함.
    """
    HASH_DIGEST_SIZE = 8

    def shard_corpus(self, corpus_path: Path, num_shards: int) -> List[Path]:
        if num_shards < 1:
            raise ValueError(f"num_shards must be ≥ 1, got {num_shards}")
        if not corpus_path.exists():
            raise FileNotFoundError(f"corpus not found: {corpus_path}")

        # [FIX] swarm_ 접두사를 worker_ 로 변경
        tmp_dir = Path(tempfile.mkdtemp(prefix="worker_shard_")) 
        shard_paths = [tmp_dir / f"shard_{i:04d}.jsonl" for i in range(num_shards)]
        shard_handles = [p.open("w", encoding="utf-8") for p in shard_paths]
        
        try:
            with corpus_path.open("r", encoding="utf-8") as src:
                for line in src:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    shard_idx = self._assign_shard(line, num_shards)
                    shard_handles[shard_idx].write(line + "\n")
        finally:
            for h in shard_handles:
                h.close()

        for p in shard_paths:
            assert p.exists(), f"shard file missing: {p}"
        return shard_paths

    def _assign_shard(self, line: str, num_shards: int) -> int:
        """라인을 num_shards 중 하나에 결정론적으로 할당."""
        h = hashlib.blake2b(line.encode("utf-8"), digest_size=self.HASH_DIGEST_SIZE)
        return int.from_bytes(h.digest(), "big") % num_shards

    @future(
        "Semantic-cluster sharding: embed each line, k-means with k=num_shards, "
        "assign by cluster. Used when corpus has strong topical structure and "
        "hash-based sharding creates unbalanced learning signals across nodes."
    )
    def shard_corpus_semantic(self, corpus_path: Path, num_shards: int) -> List[Path]:
        pass