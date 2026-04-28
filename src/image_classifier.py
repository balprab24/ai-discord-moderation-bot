"""Pluggable PyTorch image classifier with a deterministic demo fallback."""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class ImageClassification:
    label: str
    score: float
    reason: str
    latency_ms: float
    model_loaded: bool


class ImageClassifier:
    """Classify image bytes as safe or NSFW.

    If NSFW_MODEL_PATH points to a TorchScript model, this wrapper loads it and
    passes a 256-bin byte histogram tensor to the model. Without a model, it uses
    a deterministic fallback so demos and tests work without large downloads.
    """

    def __init__(
        self, model_path: Optional[str] = None, threshold: float = 0.75
    ) -> None:
        self.model_path = model_path or None
        self.threshold = threshold
        self._torch = None
        self._model = None
        self._load_error: Optional[str] = None
        if self.model_path:
            self._try_load_model()

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    async def classify(
        self, image_bytes: bytes, filename: str = "attachment"
    ) -> ImageClassification:
        start = time.perf_counter()
        if self._model is not None:
            score, reason = await asyncio.to_thread(self._classify_with_model, image_bytes)
        else:
            score, reason = self._fallback_score(image_bytes, filename)
        latency_ms = (time.perf_counter() - start) * 1000
        label = "nsfw" if score >= self.threshold else "safe"
        return ImageClassification(
            label=label,
            score=round(score, 3),
            reason=reason,
            latency_ms=latency_ms,
            model_loaded=self.model_loaded,
        )

    def _try_load_model(self) -> None:
        model_file = Path(str(self.model_path)).expanduser()
        if not model_file.exists():
            self._load_error = f"model path does not exist: {model_file}"
            return
        try:
            import torch
        except ImportError:
            self._load_error = "torch is not installed; using deterministic fallback"
            return
        try:
            model = torch.jit.load(str(model_file), map_location="cpu")
            model.eval()
        except Exception as exc:  # pragma: no cover - depends on local model file
            self._load_error = f"failed to load torch model: {exc}"
            return
        self._torch = torch
        self._model = model
        self._load_error = None

    def _classify_with_model(self, image_bytes: bytes) -> Tuple[float, str]:
        assert self._torch is not None
        assert self._model is not None
        histogram = _byte_histogram(image_bytes)
        tensor = self._torch.tensor([histogram], dtype=self._torch.float32)
        with self._torch.no_grad():
            output = self._model(tensor)
        score = _coerce_model_score(output)
        return score, "pytorch model inference"

    def _fallback_score(self, image_bytes: bytes, filename: str) -> Tuple[float, str]:
        lower_name = filename.lower()
        upper_bytes = image_bytes[:4096].upper()
        if b"DEMO_SAFE" in upper_bytes:
            return 0.04, "demo safe marker"
        if b"DEMO_NSFW" in upper_bytes or "nsfw" in lower_name:
            return 0.93, "demo nsfw marker"
        if not image_bytes:
            return 0.0, "empty attachment"

        entropy = _shannon_entropy(image_bytes[:8192])
        digest = hashlib.sha256(image_bytes + lower_name.encode("utf-8")).digest()
        hash_component = digest[0] / 255.0
        size_component = min(len(image_bytes) / 2_000_000, 0.12)
        entropy_component = min(entropy / 8.0, 1.0) * 0.18
        score = 0.08 + (hash_component * 0.18) + entropy_component + size_component
        return min(score, 0.68), "deterministic fallback score"


def _byte_histogram(image_bytes: bytes) -> Tuple[float, ...]:
    if not image_bytes:
        return tuple(0.0 for _ in range(256))
    counts = [0] * 256
    for value in image_bytes:
        counts[value] += 1
    total = float(len(image_bytes))
    return tuple(count / total for count in counts)


def _coerce_model_score(output: object) -> float:
    try:
        if hasattr(output, "detach"):
            output = output.detach().cpu().flatten()
            value = float(output[0].item())
        elif isinstance(output, (list, tuple)):
            value = float(output[0])
        else:
            value = float(output)
    except Exception as exc:  # pragma: no cover - defensive around arbitrary models
        raise ValueError(f"model output could not be converted to a score: {exc}")
    if value < 0.0 or value > 1.0:
        value = 1.0 / (1.0 + math.exp(-value))
    return max(0.0, min(1.0, value))


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = {}
    for value in data:
        counts[value] = counts.get(value, 0) + 1
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())

