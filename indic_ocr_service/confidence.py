"""How sure the recognizer was of the text it read, measured from the model itself.

The recognizer writes each block's text one token at a time, choosing the most likely token (greedy decoding). The
probability it gave the token it chose is its certainty at that step: near 1 where the print is clear, low where it
was torn between readings (a smudged letter, an unclear stroke). As in Tesseract and Google Vision:
  word   the probability of the whole word: the product of its tokens' probabilities
  block  the mean of its word confidences, with the words below LOW_WORD listed so a reader can see where it doubted

Only the chosen token's probability is kept per step (not the full score table: 2048 steps x a 248k vocabulary is
gigabytes per batch).
"""
from __future__ import annotations
import math
import threading

LOW_WORD = 0.6  # a word read with less certainty than this is listed in the block's low_words
_MAX_LOW_WORDS = 20
_SPACE_MARKS = ("▁", "Ġ", "Ċ", " ", "\n")  # a token starting with one of these starts a new word

_local = threading.local()  # per request: the crops' block orders and their measured confidences, in request order


def start() -> None:
    _local.orders, _local.stats = [], []


def results() -> dict:
    """{block order: {"text_conf", "low_words"}} for the page just read."""
    orders, stats = getattr(_local, "orders", []), getattr(_local, "stats", [])
    return dict(zip(orders, stats)) if len(orders) == len(stats) else {}


def words(ids: list[int], logprobs: list[float], starts_word, decode) -> list[tuple[str, float]]:
    """(word, confidence) from the generated token ids and the log-probability each was chosen with. A word's tokens
    are decoded together: one Tamil letter can span two byte-level tokens."""
    groups: list[tuple[list[int], float]] = []
    for t, lp in zip(ids, logprobs):
        if not groups or starts_word(t):
            groups.append(([], 0.0))
        groups[-1] = (groups[-1][0] + [t], groups[-1][1] + lp)
    out = [(decode(g).replace("▁", " ").strip(), math.exp(total)) for g, total in groups]
    return [(w, c) for w, c in out if w]


def block_stats(ids: list[int], logprobs: list[float], starts_word, decode) -> dict:
    ws = words(ids, logprobs, starts_word, decode)
    if not ws:
        return {"text_conf": None, "low_words": []}
    low = sorted((w for w in ws if w[1] < LOW_WORD), key=lambda w: w[1])[:_MAX_LOW_WORDS]
    return {"text_conf": round(sum(c for _, c in ws) / len(ws), 3),
            "low_words": [{"word": w, "conf": round(c, 3)} for w, c in low]}


def install() -> None:
    """Measure confidence in the recognizer that ships with the model, without editing its files: record the block
    order of every crop it builds, and decode with a logits processor that keeps the chosen token's probability."""
    import idp_recognizer
    import torch
    from transformers import LogitsProcessor, LogitsProcessorList

    if getattr(idp_recognizer, "_confidence_installed", False):
        return

    class ChosenTokenLogprob(LogitsProcessor):
        """Leaves the scores alone; under greedy decoding the chosen token is the arg-max, so its log-probability is
        max - logsumexp of the final scores (this runs after the model's own processors)."""

        def __init__(self) -> None:
            self.steps: list[torch.Tensor] = []

        def __call__(self, input_ids, scores):
            s = scores.float()
            self.steps.append(s.max(-1).values - torch.logsumexp(s, -1))
            return scores

    build_requests = idp_recognizer.build_requests

    def recording_build_requests(*args, **kwargs):
        requests, orders = build_requests(*args, **kwargs)
        if hasattr(_local, "orders"):
            _local.orders.extend(orders)
        return requests, orders

    def transcribe(self, requests):
        texts: list[str] = []
        tokenizer = self.processor.tokenizer
        stop = {self.eos_token_id, self.pad_token_id}

        def starts_word(t: int) -> bool:
            return tokenizer.convert_ids_to_tokens(t).startswith(_SPACE_MARKS)

        def decode(ids: list[int]) -> str:
            return tokenizer.decode(ids, skip_special_tokens=True)

        for i in range(0, len(requests), self.batch_size):
            chunk = requests[i: i + self.batch_size]
            inputs = self.processor(text=[self._prompt(r.prompt) for r in chunk], images=[r.image for r in chunk],
                                    padding=True, return_tensors="pt").to(self.model.device)
            prompt_len = inputs["input_ids"].shape[-1]
            chosen = ChosenTokenLogprob()
            with self._torch.inference_mode():
                out = self.model.generate(**inputs, max_new_tokens=self.config.max_tokens, do_sample=False,
                                          use_cache=True, eos_token_id=self.eos_token_id,
                                          pad_token_id=self.pad_token_id, logits_processor=LogitsProcessorList([chosen]))
            generated = out[:, prompt_len:]
            texts.extend(self.processor.batch_decode(generated, skip_special_tokens=True))
            if hasattr(_local, "stats"):
                logprobs = torch.stack(chosen.steps, 1).cpu().tolist() if chosen.steps else [[] for _ in chunk]
                for ids, lps in zip(generated.cpu().tolist(), logprobs):
                    n = next((k for k, t in enumerate(ids) if t in stop), len(ids))  # up to its end of text
                    _local.stats.append(block_stats(ids[:n], lps[:n], starts_word, decode))
        return [t.strip() for t in texts]

    idp_recognizer.build_requests = recording_build_requests
    idp_recognizer.HfRecognizer.transcribe = transcribe
    idp_recognizer._confidence_installed = True
