"""
End-of-run health check for the refresh pipeline. A run can "succeed" while
parts of it quietly fail (Groq retired its models and AI write-ups failed for
weeks without anyone noticing), so the run counts warnings as it goes and
emails the owner when something looks wrong.
"""

import logging
from collections import Counter

AI_LOGGER = "app.services.ai_service"
DB_ALERT_FRACTION = 0.8


class WarningCounter(logging.Handler):
    """Counts WARNING-or-worse records per logger while the pipeline runs."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.counts: Counter[str] = Counter()
        self.samples: dict[str, str] = {}

    def emit(self, record: logging.LogRecord) -> None:
        self.counts[record.name] += 1
        self.samples.setdefault(record.name, record.getMessage()[:300])


def health_issues(
    failed_steps: list[tuple[str, str]],
    warnings: Counter,
    samples: dict[str, str],
    insights_attempted: int,
    db_bytes: int,
    db_limit: int,
) -> list[str]:
    """Plain-English problems worth an email, or [] when the run looks healthy."""
    issues = [f"Step failed: {label} ({err[:200]})" for label, err in failed_steps]
    ai_failed = warnings.get(AI_LOGGER, 0)
    if insights_attempted and ai_failed >= max(3, insights_attempted // 2):
        issues.append(
            f"AI write-ups: {ai_failed} of {insights_attempted} failed. First error: {samples.get(AI_LOGGER, '?')}"
        )
    if db_limit and db_bytes >= DB_ALERT_FRACTION * db_limit:
        issues.append(
            f"Database at {db_bytes / 1024 / 1024:.0f} MB of {db_limit / 1024 / 1024:.0f} MB "
            f"({100 * db_bytes / db_limit:.0f}%). Shorten retention before it fills."
        )
    return issues
