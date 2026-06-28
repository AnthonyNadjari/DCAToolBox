"""Reports layer: Markdown, HTML and PDF report generation."""

from __future__ import annotations

from dcatoolbox.reports.generator import ReportGenerator
from dcatoolbox.reports.text import (
    auto_conclusion,
    key_findings,
    metrics_table,
)

__all__ = ["ReportGenerator", "metrics_table", "key_findings", "auto_conclusion"]
