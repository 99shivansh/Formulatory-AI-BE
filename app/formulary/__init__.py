"""Formulary & Access Intelligence Module.

This module provides:
- PDF ingestion and text extraction
- Drug data parsing and structuring
- Access scoring and labeling
- Analytics and insights generation
- Plan comparison functionality
"""

from .models import Drug, FormularyPlan, AccessScore, FormularyInsights, PlanComparison
from .pdf_ingestion import PDFIngestionService
from .multimodal_parser import MultimodalParser
from .parser import FormularyParser
from .scoring import ScoringEngine
from .insights import InsightsEngine
from .comparison import ComparisonEngine
from .service import FormularyService

__all__ = [
    "Drug",
    "FormularyPlan",
    "AccessScore",
    "FormularyInsights",
    "PlanComparison",
    "PDFIngestionService",
    "MultimodalParser",
    "FormularyParser",
    "ScoringEngine",
    "InsightsEngine",
    "ComparisonEngine",
    "FormularyService",
]
