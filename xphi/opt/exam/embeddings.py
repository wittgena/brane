# xphi.opt.exam.embeddings
## @lineage: bound.xor.exam.embeddings
## @lineage: xor.exam.embeddings
## @lineage: anchor.xor.exam.embeddings
## @lineage: meta.xor.adapter.exam.embeddings
## @lineage: xor.adapter.exam.embeddings
## @lineage: xor.dsp.adapter.exam.embeddings
import json
import os
from typing import Any
import numpy as np
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable
from xphi.opt.exam.prediction import Prediction

class Embeddings:
    def __init__(
        self,
        corpus: list[str],
        embedder,
        k: int = 5,
        callbacks: list[Any] | None = None,
        cache: bool = False,
        brute_force_threshold: int = 20_000,
        normalize: bool = True,
    ):
        assert cache is False, "Caching is not supported for embeddings-based retrievers"

        self.embedder = embedder
        self.k = k
        self.corpus = corpus
        self.normalize = normalize

        self.corpus_embeddings = self.embedder(self.corpus)
        self.corpus_embeddings = self._normalize(self.corpus_embeddings) if self.normalize else self.corpus_embeddings

        self.index = self._build_faiss() if len(corpus) >= brute_force_threshold else None
        self.search_fn = Unbatchify(self._batch_forward)

    def __call__(self, query: str):
        return self.forward(query)

    def forward(self, query: str):
        passages, indices, _scores = self.search_fn(query)
        return Prediction(passages=passages, indices=indices)

    def _batch_forward(self, queries: list[str]):
        q_embeds = self.embedder(queries)
        q_embeds = self._normalize(q_embeds) if self.normalize else q_embeds

        pids = self._faiss_search(q_embeds, self.k * 10) if self.index else None
        pids = np.tile(np.arange(len(self.corpus)), (len(queries), 1)) if pids is None else pids

        return self._rerank_and_predict(q_embeds, pids)

    def _build_faiss(self):
        nbytes = 32
        partitions = int(2 * np.sqrt(len(self.corpus)))
        dim = self.corpus_embeddings.shape[1]

        try:
            import faiss
        except ImportError:
            raise ImportError("Please `pip install faiss-cpu` or increase `brute_force_threshold` to avoid FAISS.")

        quantizer = faiss.IndexFlatL2(dim)
        index = faiss.IndexIVFPQ(quantizer, dim, partitions, nbytes, 8)

        print(
            f"Training a {nbytes}-byte FAISS index with {partitions} partitions, based on "
            f"{len(self.corpus)} x {dim}-dim embeddings"
        )
        index.train(self.corpus_embeddings)
        index.add(self.corpus_embeddings)
        index.nprobe = min(16, partitions)

        return index

    def _faiss_search(self, query_embeddings: np.ndarray, num_candidates: int):
        return self.index.search(query_embeddings, num_candidates)[1]

    def _rerank_and_predict(self, q_embeds: np.ndarray, candidate_indices: np.ndarray):
        candidate_embeddings = self.corpus_embeddings[candidate_indices]
        scores = np.einsum("qd,qkd->qk", q_embeds, candidate_embeddings)

        top_k_indices = np.argsort(-scores, axis=1)[:, : self.k]
        top_indices = candidate_indices[np.arange(len(q_embeds))[:, None], top_k_indices]
        top_scores = scores[np.arange(len(q_embeds))[:, None], top_k_indices]

        results = []
        for indices, query_scores in zip(top_indices, top_scores, strict=True):
            passages = [self.corpus[idx] for idx in indices]
            results.append((passages, indices.tolist(), query_scores.tolist()))
        return results

    def _normalize(self, embeddings: np.ndarray):
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.maximum(norms, 1e-10)

    def save(self, path: str):
        """
        Save the embeddings index to disk.

        This saves the corpus, embeddings, FAISS index (if present), and configuration
        to allow for fast loading without recomputing embeddings.

        Args:
            path: Directory path where the embeddings will be saved
        """
        os.makedirs(path, exist_ok=True)

        # Save configuration and corpus
        config = {
            "k": self.k,
            "normalize": self.normalize,
            "corpus": self.corpus,
            "has_faiss_index": self.index is not None,
        }

        with open(os.path.join(path, "config.json"), "w") as f:
            json.dump(config, f, indent=2)

        # Save embeddings
        np.save(os.path.join(path, "corpus_embeddings.npy"), self.corpus_embeddings)

        # Save FAISS index if it exists
        if self.index is not None:
            try:
                import faiss
                faiss.write_index(self.index, os.path.join(path, "faiss_index.bin"))
            except ImportError:
                # If FAISS is not available, we can't save the index
                # but we can still save the embeddings for brute force search
                pass

    def load(self, path: str, embedder):
        """
        Load the embeddings index from disk into the current instance.

        Args:
            path: Directory path where the embeddings were saved
            embedder: The embedder function to use for new queries

        Returns:
            self: Returns self for method chaining

        Raises:
            FileNotFoundError: If the save directory or required files don't exist
            ValueError: If the saved config is invalid or incompatible
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Save directory not found: {path}")

        config_path = os.path.join(path, "config.json")
        embeddings_path = os.path.join(path, "corpus_embeddings.npy")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        if not os.path.exists(embeddings_path):
            raise FileNotFoundError(f"Embeddings file not found: {embeddings_path}")

        # Load configuration and corpus
        with open(config_path) as f:
            config = json.load(f)

        # Validate required config fields
        required_fields = ["k", "normalize", "corpus", "has_faiss_index"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Invalid config: missing required field '{field}'")

        # Restore configuration
        self.k = config["k"]
        self.normalize = config["normalize"]
        self.corpus = config["corpus"]
        self.embedder = embedder

        # Load embeddings
        self.corpus_embeddings = np.load(embeddings_path)

        # Load FAISS index if it was saved and FAISS is available
        faiss_index_path = os.path.join(path, "faiss_index.bin")
        if config["has_faiss_index"] and os.path.exists(faiss_index_path):
            try:
                import faiss
                self.index = faiss.read_index(faiss_index_path)
            except ImportError:
                # If FAISS is not available, fall back to brute force
                self.index = None
        else:
            self.index = None

        return self

    @classmethod
    def from_saved(cls, path: str, embedder):
        # Create a minimal instance without triggering embedding computation
        instance = cls.__new__(cls)
        # Initialize the search function (required since we bypassed __init__)
        instance.search_fn = Unbatchify(instance._batch_forward)
        instance.load(path, embedder)
        return instance


class EmbeddingsWithScores(Embeddings):
    """
    This class extends the Embeddings retriever to also return similarity scores alongside passages and indices.
    Similarity scores enable downstream such as thresholding and re-ranking.
    """

    def forward(self, query: str):
        passages, indices, scores = self.search_fn(query)
        return Prediction(passages=passages, indices=indices, scores=scores)


import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

class Unbatchify:
    def __init__(
        self,
        batch_fn: Callable[[list[Any]], list[Any]],
        max_batch_size: int = 32,
        max_wait_time: float = 0.1
    ):
        self.batch_fn = batch_fn
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.input_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._worker)
        self.worker_thread.daemon = True  # Ensures thread exits when main program exits
        self.worker_thread.start()

    def __call__(self, input_item: Any) -> Any:
        future = Future()
        self.input_queue.put((input_item, future))
        try:
            result = future.result()
        except Exception as e:
            raise e
        return result

    def _worker(self):
        while not self.stop_event.is_set():
            batch = []
            futures = []
            start_time = time.time()
            while len(batch) < self.max_batch_size and (time.time() - start_time) < self.max_wait_time:
                try:
                    input_item, future = self.input_queue.get(timeout=self.max_wait_time)
                    batch.append(input_item)
                    futures.append(future)
                except queue.Empty:
                    break

            if batch:
                try:
                    outputs = self.batch_fn(batch)
                    for output, future in zip(outputs, futures, strict=False):
                        future.set_result(output)
                except Exception as e:
                    for future in futures:
                        future.set_exception(e)
            else:
                time.sleep(0.01)

        # Clean up remaining items when stopping
        while True:
            try:
                _, future = self.input_queue.get_nowait()
                future.set_exception(RuntimeError("Unbatchify is closed"))
            except queue.Empty:
                break

        print("Worker thread has been terminated.")

    def close(self):
        if not self.stop_event.is_set():
            self.stop_event.set()
            self.worker_thread.join()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        self.close()
