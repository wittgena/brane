# anchor.model.llm.dummy
## @lineage: anchor.provider.llm.dummy
## @lineage: anchor.surface.model.lm.dummy
## @lineage: anchor.model.lm.dummy
## @lineage: anchor.base.lm.dummy
## @lineage: bound.xor.lm.dummy
## @lineage: anchor.xor.lm.dummy
## @lineage: meta.xor.adapter.lm.dummy
## @lineage: meta.ops.trainer.dummy
## @lineage: gov.trainer.dummy
## @lineage: bound.langcom.trainer.dummy
## @lineage: bound.langcom.manager.client.lm.dummy
import random
from collections import defaultdict
from typing import Any
import numpy as np
from xphi.xor.opt.chat import FieldInfoWithName, field_header_pattern
from anchor.model.llm.base import BaseLM
from arch.topos.bind.block.residue import dotdict
from arch.xor.manifold.sign.field import OutputField

class DummyLM(BaseLM):
    def __init__(
        self,
        answers: list[dict[str, Any]] | dict[str, dict[str, Any]],
        follow_examples: bool = False,
        reasoning: bool = False,
        adapter=None,
    ):
        super().__init__("dummy", "chat", 0.0, 1000, True)
        self.answers = answers
        if isinstance(answers, list):
            self.answers = iter(answers)
        self.follow_examples = follow_examples
        self.reasoning = reasoning

        # Set adapter, defaulting to ChatAdapter
        if adapter is None:
            from xphi.xor.opt.chat import ChatAdapter
            adapter = ChatAdapter()
        self.adapter = adapter

    def _use_example(self, messages):
        # find all field names
        fields = defaultdict(int)
        for message in messages:
            if "content" in message:
                if ma := field_header_pattern.match(message["content"]):
                    fields[message["content"][ma.start() : ma.end()]] += 1
        # find the fields which are missing from the final turns
        max_count = max(fields.values())
        output_fields = [field for field, count in fields.items() if count != max_count]

        # get the output from the last turn that has the output fields as headers
        final_input = messages[-1]["content"].split("\n\n")[0]
        for input, output in zip(reversed(messages[:-1]), reversed(messages), strict=False):
            if any(field in output["content"] for field in output_fields) and final_input in input["content"]:
                return output["content"]

    def _format_answer_fields(self, field_names_and_values: dict[str, Any]):
        fields_with_values = {
            FieldInfoWithName(name=field_name, info=OutputField()): value
            for field_name, value in field_names_and_values.items()
        }
        # The reason why DummyLM needs an adapter is because it needs to know which output format to mimic.
        # Normally LMs should not have any knowledge of an adapter, because the output format is defined in the prompt.
        adapter = self.adapter

        # Try to use role="assistant" if the adapter supports it (like JSONAdapter)
        try:
            return adapter.format_field_with_value(fields_with_values, role="assistant")
        except TypeError:
            # Fallback for adapters that don't support role parameter (like ChatAdapter)
            return adapter.format_field_with_value(fields_with_values)

    def forward(self, prompt=None, messages=None, **kwargs):
        messages = messages or [{"role": "user", "content": prompt}]
        kwargs = {**self.kwargs, **kwargs}

        choices = []
        for _ in range(kwargs.get("n", 1)):
            if self.follow_examples:
                current_output = self._use_example(messages)
            elif isinstance(self.answers, dict):
                current_output = next(
                    (self._format_answer_fields(v) for k, v in self.answers.items() if k in messages[-1]["content"]),
                    "No more responses",
                )
            else:
                current_output = self._format_answer_fields(next(self.answers, {"answer": "No more responses"}))

            message = dotdict(content=current_output, tool_calls=None)
            if self.reasoning:
                message.reasoning_content = "Some reasoning"
            choices.append(dotdict(message=message, finish_reason="stop"))

        return dotdict(
            choices=choices,
            usage=dotdict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            model="dummy",
        )

    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

    def get_convo(self, index):
        """Get the prompt + answer from the ith message."""
        return self.history[index]["messages"], self.history[index]["outputs"]


def dummy_rm(passages=()) -> callable:
    if not passages:

        def inner(query: str, *, k: int, **kwargs):
            raise ValueError("No passages defined")

        return inner
    max_length = max(map(len, passages)) + 100
    vectorizer = DummyVectorizer(max_length)
    passage_vecs = vectorizer(passages)

    def inner(query: str, *, k: int, **kwargs):
        assert k <= len(passages)
        query_vec = vectorizer([query])[0]
        scores = passage_vecs @ query_vec
        largest_idx = (-scores).argsort()[:k]

        return [dotdict(long_text=passages[i]) for i in largest_idx]

    return inner


class DummyVectorizer:
    """Simple vectorizer based on n-grams."""

    def __init__(self, max_length=100, n_gram=2):
        self.max_length = max_length
        self.n_gram = n_gram
        self.P = 10**9 + 7  # A large prime number
        random.seed(123)
        self.coeffs = [random.randrange(1, self.P) for _ in range(n_gram)]

    def _hash(self, gram):
        """Hashes a string using a polynomial hash function."""
        h = 1
        for coeff, c in zip(self.coeffs, gram, strict=False):
            h = h * coeff + ord(c)
            h %= self.P
        return h % self.max_length

    def __call__(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for text in texts:
            grams = [text[i : i + self.n_gram] for i in range(len(text) - self.n_gram + 1)]
            vec = [0] * self.max_length
            for gram in grams:
                vec[self._hash(gram)] += 1
            vecs.append(vec)

        vecs = np.array(vecs, dtype=np.float32)
        vecs -= np.mean(vecs, axis=1, keepdims=True)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-10  # Added epsilon to avoid division by zero
        return vecs
