"""Model manager — VRAM-aware loading/unloading of ML models."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kris.models.registry import ModelInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages loading/unloading of embedding and LLM models.

    Only one model is loaded at a time to fit within VRAM constraints.
    """

    def __init__(self) -> None:
        self._loaded_model_id: str | None = None
        self._loaded_model: Any = None
        self._loaded_info: ModelInfo | None = None

    @property
    def current_model_id(self) -> str | None:
        return self._loaded_model_id

    @property
    def current_model(self) -> Any:
        return self._loaded_model

    def load_embedding_model(self, info: ModelInfo) -> Any:
        """Load a sentence-transformers embedding model."""
        if self._loaded_model_id == info.model_id:
            return self._loaded_model

        self.unload()

        logger.info("Loading embedding model: %s", info.name)
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(info.name)
        logger.info("Embedding model loaded on device: %s", model.device)
        self._loaded_model = model
        self._loaded_model_id = info.model_id
        self._loaded_info = info
        return model

    def unload(self) -> None:
        """Unload the currently loaded model to free VRAM."""
        if self._loaded_model is not None:
            logger.info("Unloading model: %s", self._loaded_model_id)
            del self._loaded_model
            self._loaded_model = None
            self._loaded_model_id = None
            self._loaded_info = None

            # Try to free GPU memory
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def is_loaded(self, model_id: str) -> bool:
        return self._loaded_model_id == model_id

    def load_llm(self, info: ModelInfo) -> Any:
        """Load a llama-cpp-python LLM model.

        Hot-swaps with embedding model if one is loaded — only one model
        at a time to stay within VRAM budget.
        """
        if self._loaded_model_id == info.model_id:
            return self._loaded_model

        self.unload()

        logger.info("Loading LLM: %s", info.name)
        from llama_cpp import Llama

        model = Llama(
            model_path=info.path_or_repo,
            n_ctx=4096,
            n_gpu_layers=-1,  # offload all layers to GPU
            verbose=False,
        )

        # Log backend info for diagnostics
        gpu_layers = model.model_params.n_gpu_layers
        logger.info("LLM loaded: n_gpu_layers=%d, n_ctx=%d", gpu_layers, model.n_ctx())

        self._loaded_model = model
        self._loaded_model_id = info.model_id
        self._loaded_info = info
        return model


def measure_model_vram(model_info: ModelInfo) -> float:
    """Measure VRAM usage for a model by loading it and checking GPU memory delta.

    Uses driver-level memory reporting (torch.cuda.mem_get_info) so that
    allocations from non-PyTorch runtimes like llama.cpp are captured.

    Returns VRAM usage in GB. Raises RuntimeError if the model fails to load (e.g. OOM).
    """
    import torch

    manager = ModelManager()

    # Ensure clean state
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    free_before, _ = torch.cuda.mem_get_info()

    try:
        if model_info.model_type == "embedding":
            manager.load_embedding_model(model_info)
        elif model_info.model_type == "llm":
            manager.load_llm(model_info)
        else:
            raise ValueError(f"Unknown model type: {model_info.model_type}")

        free_after, _ = torch.cuda.mem_get_info()
        delta_bytes = free_before - free_after
        delta_gb = round(max(delta_bytes, 0) / (1024**3), 2)
        return delta_gb
    finally:
        manager.unload()
