from __future__ import annotations

from pathlib import Path

from .knowledge_runtime import KnowledgeRuntime
from .knowledge_system_evolution import EvolutionFacadeMixin
from .knowledge_system_policy import PolicyFacadeMixin, ReconciliationFacadeMixin
from .knowledge_system_projection import (
    EmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    ProjectionFacadeMixin,
)
from .knowledge_system_publication import PublicationFacadeMixin
from .store import Store


class KnowledgeSystem(
    PolicyFacadeMixin,
    ReconciliationFacadeMixin,
    PublicationFacadeMixin,
    ProjectionFacadeMixin,
    EvolutionFacadeMixin,
    KnowledgeRuntime,
):
    """Complete governed Phase 3 production facade.

    The existing epistemic ledger remains the sole proposition truth-state
    authority. Phase 3 adds governed semantic state, deterministic publication,
    rebuildable projections, freshness/impact controls, bounded intake, and
    read-only routing evidence without broadening tool or routing authority.
    """

    def __init__(
        self,
        store: Store,
        artifact_root: str | Path = "state/knowledge",
    ) -> None:
        super().__init__(store, artifact_root)
        self.okf_root = self.root / "okf-snapshots"
        self.okf_root.mkdir(parents=True, exist_ok=True)


__all__ = ["EmbeddingAdapter", "KnowledgeSystem", "OpenAIEmbeddingAdapter"]
