"""Knowledge slice. Ports, records, and memory adapters. No PostgreSQL."""

from backend.knowledge.memory import MemoryKnowledgePoints, MemoryMethods, MemoryTagger
from backend.knowledge.models import (
    COMPOSITE,
    FAULT_CODES,
    PRIMARY,
    ROLES,
    SUPPORT,
    ApprovedQuestion,
    KnowledgeFault,
    KnowledgePoint,
    Method,
    QuestionKnowledge,
    QuestionMethod,
)
from backend.knowledge.ports import CatalogReader, KnowledgePoints, Methods, QuestionTagger

__all__ = [
    "COMPOSITE",
    "FAULT_CODES",
    "PRIMARY",
    "ROLES",
    "SUPPORT",
    "ApprovedQuestion",
    "CatalogReader",
    "KnowledgeFault",
    "KnowledgePoint",
    "KnowledgePoints",
    "MemoryKnowledgePoints",
    "MemoryMethods",
    "MemoryTagger",
    "Method",
    "Methods",
    "QuestionKnowledge",
    "QuestionMethod",
    "QuestionTagger",
]
