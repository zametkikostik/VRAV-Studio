"""Phase C: grounded transcript intelligence over timestamped segment search.

Pipeline:
  query → validate → embed → search_project_segments (exact vector space)
       → rank / threshold → bounded context → optional LLM explanation
       → grounded response with full segment provenance.

Never invents timestamps, asset IDs, or dialogue. Transcript text is untrusted evidence.
Production never silently uses MockAIProvider for LLM answers.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.services.embeddings import (
    EmbeddingAuthError,
    EmbeddingConfigError,
    EmbeddingProviderError,
    get_embedding_provider,
)
from app.services.rag_search import RagError
from app.services.segment_index import SegmentHit, search_project_segments

logger = logging.getLogger(__name__)

# CONTENT CONTINUES - THIS IS A TEST OF TOOL ACCEPTANCE
