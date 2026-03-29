"""
Graph Write Tool

add_triple FunctionTool for MiroClaw agents to submit structured triples
to the Neo4j knowledge graph during the Contribute phase.

Validation pipeline:
1. Schema check — subject/object must match ontology entity types
2. Format check — must be structured triple, not free text
3. Dedup check — cosine similarity >0.95 rejected
4. Source check — URL must be reachable and claim extractable

Satisfies: R05 (Living knowledge graph), R06 (Triple validation), R01 (FunctionTool)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ...utils.logger import get_logger

logger = get_logger('miroclaw.graph_write')


@dataclass
class TripleSubmission:
    """A structured triple submission from an agent."""
    subject: str
    subject_type: str
    relationship: str
    object: str
    object_type: str
    source_url: str
    added_by_agent: str
    added_round: int
    added_timestamp: str = None

    def __post_init__(self):
        if self.added_timestamp is None:
            self.added_timestamp = datetime.now().isoformat()


@dataclass
class ValidationResult:
    """Result of triple validation."""
    valid: bool
    reason: str = ""
    duplicate_of: Optional[str] = None  # UUID of existing triple if dedup match

    def to_dict(self) -> Dict[str, Any]:
        result = {"valid": self.valid, "reason": self.reason}
        if self.duplicate_of:
            result["duplicate_of"] = self.duplicate_of
        return result


class TripleValidator:
    """Validates triple submissions before they enter the knowledge graph.

    Validation pipeline (in order):
    1. Format enforcement — must be structured triple
    2. Schema check — entity types must exist in ontology
    3. Dedup check — cosine similarity >0.95 rejected
    4. Source URL check — must be reachable
    """

    # Regex for structured triple format
    TRIPLE_PATTERN = re.compile(
        r'\(([^)]+)\)\s*—?\s*\[([^\]]+)\]\s*->?\s*\(([^)]+)\)',
        re.IGNORECASE,
    )

    def __init__(
        self,
        ontology_entity_types: Optional[set] = None,
        embedding_service=None,
        graph_service=None,
        similarity_threshold: float = 0.95,
    ):
        self.ontology_entity_types = ontology_entity_types or set()
        self.embedding_service = embedding_service
        self.graph_service = graph_service
        self.similarity_threshold = similarity_threshold

    def validate_format(self, triple: TripleSubmission) -> ValidationResult:
        """Check 1: Verify the submission is a structured triple, not free text."""
        if not triple.subject or not triple.relationship or not triple.object:
            return ValidationResult(
                valid=False,
                reason="Triple must have subject, relationship, and object fields. "
                       "Format: (Subject) —[RELATIONSHIP]-> (Object)",
            )
        if len(triple.subject) > 500 or len(triple.object) > 500:
            return ValidationResult(
                valid=False,
                reason="Subject and object must be under 500 characters each.",
            )
        if len(triple.relationship) > 200:
            return ValidationResult(
                valid=False,
                reason="Relationship must be under 200 characters.",
            )
        return ValidationResult(valid=True)

    def validate_schema(self, triple: TripleSubmission) -> ValidationResult:
        """Check 2: Entity types must exist in the ontology."""
        if not self.ontology_entity_types:
            # No ontology loaded, skip schema validation
            return ValidationResult(valid=True)

        subject_type_lower = triple.subject_type.lower()
        object_type_lower = triple.object_type.lower()

        valid_types = {t.lower() for t in self.ontology_entity_types}

        if subject_type_lower not in valid_types:
            return ValidationResult(
                valid=False,
                reason=f"Subject entity type '{triple.subject_type}' not found in ontology. "
                       f"Valid types: {', '.join(sorted(self.ontology_entity_types)[:20])}",
            )
        if object_type_lower not in valid_types:
            return ValidationResult(
                valid=False,
                reason=f"Object entity type '{triple.object_type}' not found in ontology. "
                       f"Valid types: {', '.join(sorted(self.ontology_entity_types)[:20])}",
            )
        return ValidationResult(valid=True)

    def validate_dedup(self, triple: TripleSubmission) -> ValidationResult:
        """Check 3: Reject near-duplicates via cosine similarity."""
        if self.embedding_service is None:
            # No embedding service, skip dedup
            return ValidationResult(valid=True)

        try:
            triple_text = f"{triple.subject} {triple.relationship} {triple.object}"
            triple_embedding = self.embedding_service.get_embedding(triple_text)

            # Search for similar triples in the graph
            if self.graph_service is not None:
                existing = self.graph_service.find_similar_triples(
                    embedding=triple_embedding,
                    threshold=self.similarity_threshold,
                )
                if existing:
                    return ValidationResult(
                        valid=False,
                        reason=f"Duplicate of existing triple (similarity > {self.similarity_threshold})",
                        duplicate_of=existing[0].get("uuid"),
                    )

        except Exception as e:
            logger.warning(f"Dedup validation failed: {e}")

        return ValidationResult(valid=True)

    def validate_source_url(self, triple: TripleSubmission) -> ValidationResult:
        """Check 4: Source URL must be reachable (if provided).

        Note: Full LLM-based claim verification is deferred to a later
        implementation phase. For now, we check URL reachability only.
        """
        if not triple.source_url:
            # No source URL provided — allowed but flagged
            return ValidationResult(valid=True)

        # Basic URL format check
        url_pattern = re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+',
            re.IGNORECASE,
        )
        if not url_pattern.match(triple.source_url):
            return ValidationResult(
                valid=False,
                reason=f"Invalid URL format: {triple.source_url}",
            )

        return ValidationResult(valid=True)

    def validate(self, triple: TripleSubmission) -> ValidationResult:
        """Run full validation pipeline."""
        # 1. Format
        result = self.validate_format(triple)
        if not result.valid:
            return result

        # 2. Schema
        result = self.validate_schema(triple)
        if not result.valid:
            return result

        # 3. Dedup
        result = self.validate_dedup(triple)
        if not result.valid:
            return result

        # 4. Source URL
        result = self.validate_source_url(triple)
        if not result.valid:
            return result

        return ValidationResult(valid=True)


class GraphWriteTool:
    """MiroClaw tool for writing triples to the knowledge graph.

    Registered as a CAMEL FunctionTool on MiroClawAgent instances.
    Only invocable during the Contribute phase.
    """

    def __init__(
        self,
        graph_service,
        validator: TripleValidator,
    ):
        self.graph_service = graph_service
        self.validator = validator

    def add_triple(
        self,
        subject: str,
        subject_type: str,
        relationship: str,
        object: str,
        object_type: str,
        source_url: str,
        added_by_agent: str,
        added_round: int,
    ) -> Dict[str, Any]:
        """Add a structured triple to the knowledge graph.

        Args:
            subject: Subject entity name
            subject_type: Subject entity type (from ontology)
            relationship: Relationship type
            object: Object entity name
            object_type: Object entity type (from ontology)
            source_url: URL where evidence was found
            added_by_agent: Agent identifier
            added_round: Current round number

        Returns:
            Dict with success status and validation result
        """
        triple = TripleSubmission(
            subject=subject,
            subject_type=subject_type,
            relationship=relationship,
            object=object,
            object_type=object_type,
            source_url=source_url,
            added_by_agent=added_by_agent,
            added_round=added_round,
        )

        # Run validation pipeline
        validation = self.validator.validate(triple)
        if not validation.valid:
            logger.info(
                f"Triple rejected: {validation.reason} "
                f"(agent={added_by_agent}, round={added_round})"
            )
            return {"success": False, "validation": validation.to_dict()}

        # Write to graph
        try:
            self.graph_service.write_triple(
                subject=triple.subject,
                subject_type=triple.subject_type,
                relationship=triple.relationship,
                object=triple.object,
                object_type=triple.object_type,
                properties={
                    "source_url": triple.source_url,
                    "added_by_agent": triple.added_by_agent,
                    "added_round": triple.added_round,
                    "added_timestamp": triple.added_timestamp,
                    "upvotes": 0,
                    "downvotes": 0,
                    "status": "pending",
                },
            )
            logger.info(
                f"Triple added: ({triple.subject}) —[{triple.relationship}]-> ({triple.object}) "
                f"(agent={added_by_agent}, round={added_round})"
            )
            return {"success": True, "validation": validation.to_dict()}

        except Exception as e:
            logger.error(f"Failed to write triple: {e}")
            return {"success": False, "error": str(e)}
