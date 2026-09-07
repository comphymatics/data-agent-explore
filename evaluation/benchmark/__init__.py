"""Official Evaluation = Four-System Raw E2E Benchmark.

Historical scoring symbols remain importable only for regression compatibility.
Use evaluation.benchmark.e2e_runner.run or python -m evaluation for official runs.
"""

from .models import RetrievalResult
from .scoring import aggregate_scores, score_result

__all__ = ["RetrievalResult", "aggregate_scores", "score_result"]
