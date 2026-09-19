"""Model registry — loads and queries model definitions from config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kris.config.schema import KrisConfig


@dataclass
class ModelInfo:
    model_id: str
    model_type: str  # "embedding" or "llm"
    name: str
    path_or_repo: str
    dimensions: int | None = None
    vram_gb: float = 0.0
    n_ctx: int = 4096


class ModelRegistry:
    """Registry of available models loaded from configuration."""

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}

    def load_from_config(self, config: KrisConfig) -> None:
        """Populate registry from a KrisConfig."""
        emb = config.models.embedding
        self._models["embedding"] = ModelInfo(
            model_id="embedding",
            model_type="embedding",
            name=emb.name,
            path_or_repo=emb.name,
            dimensions=emb.dimensions,
            vram_gb=emb.vram_gb,
        )

        llm = config.models.llm
        if llm.name:
            self._models["llm"] = ModelInfo(
                model_id="llm",
                model_type="llm",
                name=llm.name,
                path_or_repo=llm.model_path or llm.name,
                vram_gb=llm.vram_gb,
                n_ctx=llm.n_ctx,
            )

    def get(self, model_id: str) -> ModelInfo | None:
        return self._models.get(model_id)

    def get_by_type(self, model_type: str) -> list[ModelInfo]:
        return [m for m in self._models.values() if m.model_type == model_type]

    def list_all(self) -> list[ModelInfo]:
        return list(self._models.values())
