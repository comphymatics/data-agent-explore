"""Raw E2E benchmark; legacy Evidence comparison exports retained for regression."""

from .models import RetrievalResult
from .scoring import aggregate_scores, score_result

__all__ = ["RetrievalResult", "aggregate_scores", "score_result"]
