"""Coreference resolution for multi-turn conversations.

This module provides coreference resolution to handle pronouns and elliptical
references in multi-turn conversations by maintaining conversation state and
resolving references to previously mentioned entities.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ConversationState:
    """Maintains conversation context across turns for coreference resolution.
    
    Attributes:
        entity_registry: Maps entity types (e.g., "service", "api", "engineer") 
                        to lists of mentioned entities in chronological order
        subject_stack: Stack of recently discussed subjects for quick reference
        turn_count: Number of conversation turns processed
    """
    entity_registry: dict[str, list[str]] = field(default_factory=dict)
    subject_stack: list[str] = field(default_factory=list)
    turn_count: int = 0

    def extract_entities(self, text: str,
                         known_services: list[str]) -> dict[str, list[str]]:
        """Extract named entities from text using regex and known service names.
        
        Args:
            text: The text to extract entities from (question or answer)
            known_services: List of known service names from the graph
            
        Returns:
            Dictionary mapping entity types to lists of extracted entities
        """
        entities: dict[str, list[str]] = {
            "service": [], "endpoint": [], "schema": [], "engineer": []
        }
        
        # Services: case-insensitive match against known service names from graph
        # Use word boundaries to prevent partial matches (e.g., "payment" vs "payments service")
        for service in known_services:
            if re.search(rf'\b{re.escape(service)}\b', text, re.IGNORECASE):
                entities["service"].append(service)

        # Endpoints: /path/segments with at least 2 segments
        endpoints = re.findall(r'/[a-z][a-z0-9/_\-\{\}]+', text)
        entities["endpoint"] = [e for e in endpoints if e.count('/') >= 2]

        # Schemas and tables
        schemas = re.findall(
            r'\b[A-Z][a-zA-Z]+(?:Table|Schema|Model|Record|Entity)\b', text
        )
        entities["schema"] = schemas

        # Engineers: "First Last" pattern (matched against known engineers if available)
        engineers = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
        entities["engineer"] = engineers

        return entities

    def update(self, question: str, answer: str, known_services: list[str]) -> None:
        """Update entity registry and subject stack after a completed turn.
        
        Uses "move to end on re-mention" semantics: if an entity is already in the
        registry, it is removed and re-appended to ensure the most recently mentioned
        entity is always at position [-1].
        
        Args:
            question: The original user question
            answer: The generated answer
            known_services: List of known service names from the graph
        """
        q_entities = self.extract_entities(question, known_services)
        a_entities = self.extract_entities(answer, known_services)

        # Initialize entity types if not present
        for entity_type in ["service", "endpoint", "schema", "engineer"]:
            if entity_type not in self.entity_registry:
                self.entity_registry[entity_type] = []

        for entity_type in self.entity_registry:
            combined = q_entities.get(entity_type, []) + a_entities.get(entity_type, [])
            # Append unique new entities only (preserve order, most recent last)
            for e in combined:
                if e not in self.entity_registry[entity_type]:
                    self.entity_registry[entity_type].append(e)
                else:
                    # Move to end (most recently mentioned)
                    self.entity_registry[entity_type].remove(e)
                    self.entity_registry[entity_type].append(e)

        # Primary subject from question (first service or endpoint mentioned)
        primary = (q_entities["service"] or q_entities["endpoint"] or
                   q_entities["schema"] or [None])[0]
        if primary:
            self.subject_stack.append(primary)

        self.turn_count += 1

    def resolve_references(self, question: str) -> str:
        """Substitute pronouns with the most recent entity of the appropriate type.
        
        Returns question unchanged when:
        - turn_count is 0 (first turn)
        - reference is ambiguous (2+ equally recent entities of same type differ)
        - no matching entity type found
        
        Args:
            question: The user's question potentially containing pronouns
            
        Returns:
            Question with pronouns substituted, or unchanged if no substitution possible
        """
        # First turn: no context available, return unchanged
        if self.turn_count == 0:
            return question

        resolved = question

        # Map pronouns to entity types
        pronoun_map: dict[str, list[str]] = {
            "service":  [r'\bit\b', r'\bthis\b', r'\bthat\b',
                         r'\bthe service\b', r'\bthe microservice\b'],
            "endpoint": [r'\bthe endpoint\b', r'\bthe API\b',
                         r'\bthe route\b', r'\bthe path\b'],
            "schema":   [r'\bthe schema\b', r'\bthe table\b',
                         r'\bthe model\b'],
        }

        for entity_type, patterns in pronoun_map.items():
            registry = self.entity_registry.get(entity_type, [])
            if not registry:
                continue

            # Ambiguity check: are the last 2 entities different?
            if len(registry) >= 2 and registry[-1] != registry[-2]:
                continue  # ambiguous — skip substitution for this type

            recent_entity = registry[-1]
            for pattern in patterns:
                resolved = re.sub(
                    pattern, recent_entity, resolved, flags=re.IGNORECASE
                )

        return resolved

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for session store persistence."""
        return {
            "entity_registry": self.entity_registry,
            "subject_stack": self.subject_stack,
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationState":
        """Deserialize from session store.
        
        Provides default empty lists for all entity types to handle cases where
        stored state is missing a type added in a future version.
        """
        return cls(
            entity_registry=data.get("entity_registry",
                                     {"service": [], "endpoint": [], "schema": [], "engineer": []}),
            subject_stack=data.get("subject_stack", []),
            turn_count=data.get("turn_count", 0),
        )
