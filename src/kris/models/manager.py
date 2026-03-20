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
        self._loaded_model = model
        self._loaded_model_id = info.model_id
        self._loaded_info = info
        return model
