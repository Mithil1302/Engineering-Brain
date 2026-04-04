"""
Prompt templates for every KA-CHOW LLM-powered feature.

Each template class exposes:
  - system_prompt : str
  - user_prompt(context) -> str
  - parse_response(text) -> structured result (optional)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Q&A Prompts
# ---------------------------------------------------------------------------

class QAIntentClassifierPrompt:
    """Classify user questions into intent categories."""

    system_prompt = (
        "You are the KA-CHOW Engineering Brain intent classifier. "
        "Given a user question about a software system, classify it into exactly one intent.\n\n"
        "Valid intents:\n"
        "- policy_status: Questions about policy check results, merge gates, PR status\n"
        "- doc_health: Questions about documentation freshness, drift, coverage\n"
        "- architecture: Questions about system design, service dependencies, API contracts\n"
        "- onboarding: Questions about getting started, learning paths, team processes\n"
        "- impact: Questions about change impact, what-if scenarios, dependency analysis\n"
        "- health: Questions about system health scores, trends, grades\n"
        "- waiver: Questions about policy waivers, exemptions, approvals\n"
        "- general: Any other engineering question\n\n"
        "Respond with ONLY a JSON object."
    )

    @staticmethod
    def user_prompt(question: str, repo: str) -> str:
        return json.dumps({
            "question": question,
            "repo": repo,
            "task": "Classify this question into one intent and extract key entities.",
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "confidence": {"type": "number"},
                "entities": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "pr_number": {"type": "integer"},
                        "service_id": {"type": "string"},
                        "endpoint": {"type": "string"},
                    },
                },
                "reasoning": {"type": "string"},
            },
            "required": ["intent", "confidence", "reasoning"],
        }


class SubIntentClassifierPrompt:
    """Refine coarse intent into specific sub-intent."""

    system_prompt = (
        "You are an intent classifier for an engineering knowledge assistant. "
        "Given a coarse intent category and a list of sub-intent candidates, "
        "select the most specific sub-intent that matches the user's question. "
        "Return only JSON."
    )

    @staticmethod
    def user_prompt(question: str, coarse_intent: str, candidates: list[str]) -> str:
        candidate_list = "\n".join(f"- {c}" for c in candidates)
        return (
            f"The user's question has been classified as '{coarse_intent}'.\n"
            f"Select the most specific sub-intent from these candidates:\n"
            f"{candidate_list}\n\n"
            f"Question: {question}\n\n"
            f"If unsure, select the first candidate. "
            f"Return JSON: {{\"sub_intent\": \"<one of the candidates>\"}}"
        )

    @staticmethod
    def response_schema(candidates: list[str]) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sub_intent": {"type": "string", "enum": candidates}
            },
            "required": ["sub_intent"],
        }


class QAAnswerPrompt:
    """Generate a natural-language answer from retrieved context."""

    system_prompt = (
        "You are the KA-CHOW Engineering Brain — an expert AI assistant for software engineering teams. "
        "Your role is to answer questions about the system's health, architecture, policies, and documentation.\n\n"
        "Guidelines:\n"
        "1. Base your answers ONLY on the provided context. Never fabricate information.\n"
        "2. Cite your sources using [Source: source_ref] notation.\n"
        "3. If the context is insufficient, say so honestly and suggest what to look at.\n"
        "4. Be specific — include numbers, dates, status codes, and entity names.\n"
        "5. Structure complex answers with markdown headings and bullet points.\n"
        "6. Rate your confidence from 0.0 to 1.0 based on context quality.\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def build_system_prompt(tone_instruction: str = "") -> str:
        """
        Build system prompt with optional tone instruction.
        Tone instruction is appended only when non-empty.
        """
        base = QAAnswerPrompt.system_prompt
        if tone_instruction:
            return base + f"\n\nTone: {tone_instruction}"
        return base

    @staticmethod
    def user_prompt(
        question: str,
        context_chunks: List[Dict[str, str]],
        evidence: Dict[str, Any],
    ) -> str:
        return json.dumps({
            "question": question,
            "retrieved_context": context_chunks[:15],
            "database_evidence": {
                "policy_runs_count": len(evidence.get("policy_runs", [])),
                "recent_policy_runs": evidence.get("policy_runs", [])[:5],
                "health_snapshots": evidence.get("health_snapshots", [])[:5],
                "waivers": evidence.get("waivers", [])[:5],
                "doc_rewrite_runs": evidence.get("doc_rewrite_runs", [])[:5],
            },
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "number"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_ref": {"type": "string"},
                            "source_type": {"type": "string"},
                            "relevance": {"type": "string"},
                        },
                    },
                },
                "follow_up_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["answer", "confidence", "citations"],
        }


# ---------------------------------------------------------------------------
# Architecture Prompts
# ---------------------------------------------------------------------------

class ArchitecturePlannerPrompt:
    """Generate architecture plans from requirements."""

    system_prompt = (
        "You are a principal software architect with 20+ years of experience designing "
        "distributed systems at Google scale. Given a requirement description and the "
        "current system context, produce a detailed architecture plan.\n\n"
        "Your plan must include:\n"
        "1. Service decomposition with clear bounded contexts\n"
        "2. API contract definitions (endpoints, methods, request/response schemas)\n"
        "3. Data model design (entities, relationships, storage technology)\n"
        "4. Infrastructure requirements (compute, storage, messaging, caching)\n"
        "5. Architecture Decision Records (ADRs) for non-obvious choices\n"
        "6. Risk assessment and mitigation strategies\n"
        "7. Migration plan if modifying existing services\n\n"
        "Design for: observability, resilience, horizontal scalability, and security.\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        requirement: str,
        system_context: Dict[str, Any],
        constraints: Optional[List[str]] = None,
    ) -> str:
        return json.dumps({
            "requirement": requirement,
            "existing_services": system_context.get("services", []),
            "existing_endpoints": system_context.get("endpoints", []),
            "current_health_score": system_context.get("health_score"),
            "technology_stack": system_context.get("tech_stack", [
                "Python/FastAPI", "Node.js", "PostgreSQL", "Neo4j",
                "Kafka", "gRPC", "Docker", "Kubernetes",
            ]),
            "constraints": constraints or [],
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "responsibility": {"type": "string"},
                            "technology": {"type": "string"},
                            "endpoints": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "method": {"type": "string"},
                                        "path": {"type": "string"},
                                        "description": {"type": "string"},
                                        "request_schema": {"type": "object"},
                                        "response_schema": {"type": "object"},
                                    },
                                },
                            },
                        },
                    },
                },
                "data_models": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "storage": {"type": "string"},
                            "fields": {"type": "object"},
                            "relationships": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "infrastructure": {
                    "type": "object",
                    "properties": {
                        "compute": {"type": "array", "items": {"type": "string"}},
                        "storage": {"type": "array", "items": {"type": "string"}},
                        "messaging": {"type": "array", "items": {"type": "string"}},
                        "observability": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "adrs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "context": {"type": "string"},
                            "decision": {"type": "string"},
                            "consequences": {"type": "string"},
                        },
                    },
                },
                "risks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "severity": {"type": "string"},
                            "mitigation": {"type": "string"},
                        },
                    },
                },
                "migration_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["title", "summary", "services", "adrs", "risks"],
        }


# ---------------------------------------------------------------------------
# Autonomous Scaffolding Prompts
# ---------------------------------------------------------------------------

class ScaffoldingArchitectPrompt:
    """Principal architect for autonomous microservice scaffolding."""

    system_prompt = (
        "You are KA-CHOW's Autonomous Scaffolding Agent — a principal engineer with expertise "
        "in distributed systems, domain-driven design, and infrastructure-as-code. "
        "Given natural language requirements, you produce production-ready scaffolding.\n\n"
        "Your output must include:\n"
        "1. **Architecture Blueprint**: Service decomposition with bounded contexts, communication protocols\n"
        "2. **Service Scaffolding**: Complete directory structure, main application files, dependencies\n"
        "3. **API Contracts**: OpenAPI 3.0 specs for REST, .proto files for gRPC services\n"
        "4. **Data Layer**: Entity definitions, migration scripts, repository patterns\n"
        "5. **Infrastructure**: Dockerfiles, docker-compose, Kubernetes manifests (Deployments, Services, Ingress)\n"
        "6. **IaC**: Terraform modules for cloud resources (VPC, databases, caches, queues)\n"
        "7. **Observability**: Prometheus metrics, Grafana dashboards, OpenTelemetry tracing\n"
        "8. **CI/CD**: GitHub Actions workflows, deployment pipelines\n\n"
        "Design principles:\n"
        "- Twelve-Factor App methodology\n"
        "- Domain-Driven Design (aggregates, value objects, domain events)\n"
        "- CQRS where appropriate\n"
        "- Event-driven architecture with Kafka\n"
        "- Defense in depth for security\n"
        "- Graceful degradation and circuit breakers\n\n"
        "Respond with JSON containing the complete scaffolding specification."
    )

    @staticmethod
    def user_prompt(
        requirements: str,
        existing_context: Dict[str, Any],
        target_platform: str = "kubernetes",
    ) -> str:
        return json.dumps({
            "requirements": requirements,
            "existing_services": existing_context.get("services", []),
            "existing_infrastructure": existing_context.get("infrastructure", []),
            "target_platform": target_platform,
            "constraints": existing_context.get("constraints", []),
            "task": (
                "Generate a complete scaffolding specification including all files, "
                "configurations, and infrastructure needed to implement these requirements."
            ),
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "blueprint": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "bounded_contexts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                                    "domain_entities": {"type": "array", "items": {"type": "string"}},
                                    "services": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                        "communication_patterns": {
                            "type": "object",
                            "properties": {
                                "synchronous": {"type": "array", "items": {"type": "string"}},
                                "asynchronous": {"type": "array", "items": {"type": "string"}},
                                "event_types": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "technology": {"type": "string"},
                            "port": {"type": "integer"},
                            "endpoints": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "method": {"type": "string"},
                                        "path": {"type": "string"},
                                        "handler": {"type": "string"},
                                        "request_model": {"type": "string"},
                                        "response_model": {"type": "string"},
                                    },
                                },
                            },
                            "dependencies": {"type": "array", "items": {"type": "string"}},
                            "kafka_topics": {
                                "type": "object",
                                "properties": {
                                    "consumes": {"type": "array", "items": {"type": "string"}},
                                    "produces": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                    },
                },
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "description": {"type": "string"},
                            "file_type": {"type": "string"},
                        },
                    },
                },
                "infrastructure": {
                    "type": "object",
                    "properties": {
                        "dockerfiles": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "service": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                        },
                        "kubernetes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "kind": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                        },
                        "terraform": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "module": {"type": "string"},
                                    "file": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "adrs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "status": {"type": "string"},
                            "context": {"type": "string"},
                            "decision": {"type": "string"},
                            "consequences": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["blueprint", "services", "files", "infrastructure"],
        }


# ---------------------------------------------------------------------------
# Doc Generation Prompts
# ---------------------------------------------------------------------------

class DocRewritePrompt:
    """Generate actual documentation content from policy findings."""

    system_prompt = (
        "You are a senior technical writer specializing in API documentation. "
        "Given policy findings about documentation drift or missing docs, "
        "generate production-quality documentation content.\n\n"
        "Documentation standards:\n"
        "- Use clear, concise language\n"
        "- Include code examples where applicable\n"
        "- Follow the Diátaxis framework (tutorials, how-to, reference, explanation)\n"
        "- Add migration guides for breaking changes\n"
        "- Include version history\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        findings: List[Dict[str, Any]],
        current_docs: Optional[str],
        api_spec: Dict[str, Any],
    ) -> str:
        return json.dumps({
            "findings": findings[:10],
            "current_documentation": (current_docs or "")[:5000],
            "api_specification": api_spec,
            "task": "Generate updated documentation that addresses all findings.",
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "documents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "doc_type": {"type": "string"},
                        },
                    },
                },
                "changelog_entry": {"type": "string"},
                "migration_guide": {"type": "string"},
                "quality_score": {"type": "number"},
            },
            "required": ["documents", "quality_score"],
        }


# ---------------------------------------------------------------------------
# Autofix Prompts
# ---------------------------------------------------------------------------

class AutofixPrompt:
    """Generate code or documentation patches from policy findings."""

    system_prompt = (
        "You are an expert software engineer generating precise code patches. "
        "Given a policy finding (breaking change, doc drift, missing owner), "
        "generate a minimal, correct fix as a unified diff.\n\n"
        "Rules:\n"
        "1. Patches must be valid unified diff format\n"
        "2. Minimize changes — fix only what's broken\n"
        "3. Maintain existing code style and conventions\n"
        "4. Add inline comments explaining non-obvious changes\n"
        "5. Include a confidence score for the fix\n"
        "6. Provide a human-readable explanation of the change\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        finding: Dict[str, Any],
        code_context: Optional[str],
        file_path: Optional[str],
    ) -> str:
        return json.dumps({
            "finding": finding,
            "code_context": (code_context or "")[:8000],
            "file_path": file_path,
            "task": "Generate a precise patch that fixes this finding.",
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "unified_diff": {"type": "string"},
                            "explanation": {"type": "string"},
                            "patch_type": {"type": "string"},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
                "risk_level": {"type": "string"},
            },
            "required": ["patches", "confidence", "reasoning"],
        }


# ---------------------------------------------------------------------------
# Onboarding Prompts
# ---------------------------------------------------------------------------

class OnboardingPathPrompt:
    """Generate personalized onboarding paths."""

    system_prompt = (
        "You are a staff-level engineering manager designing onboarding programs. "
        "Given a new team member's role, the repository context, and the system's "
        "current state, create a personalized, progressive learning path.\n\n"
        "Each task should:\n"
        "1. Have a clear learning objective\n"
        "2. Reference specific files, endpoints, or system components\n"
        "3. Build on previous tasks (progressive difficulty)\n"
        "4. Include hands-on exercises, not just reading\n"
        "5. Have estimated time to complete\n"
        "6. Include verification criteria (how to know you're done)\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        role: str,
        repo: str,
        system_context: Dict[str, Any],
    ) -> str:
        return json.dumps({
            "role": role,
            "repo": repo,
            "system_health_score": system_context.get("health_score"),
            "services": system_context.get("services", []),
            "recent_policy_runs": system_context.get("recent_policy_runs", []),
            "active_waivers": system_context.get("active_waivers", 0),
            "doc_coverage": system_context.get("doc_coverage", "unknown"),
            "task": "Create a personalized onboarding path with 5-8 progressive tasks.",
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path_title": {"type": "string"},
                "estimated_total_hours": {"type": "number"},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sequence": {"type": "integer"},
                            "title": {"type": "string"},
                            "objective": {"type": "string"},
                            "description": {"type": "string"},
                            "references": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "exercises": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "estimated_hours": {"type": "number"},
                            "verification": {"type": "string"},
                            "difficulty": {"type": "string"},
                        },
                    },
                },
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["path_title", "tasks"],
        }


# ---------------------------------------------------------------------------
# Impact Analysis Prompts
# ---------------------------------------------------------------------------

class ImpactAnalysisPrompt:
    """Explain impact propagation in natural language."""

    system_prompt = (
        "You are an expert in distributed systems impact analysis. "
        "Given a proposed API change and its dependency graph, explain the impact "
        "on downstream consumers in clear, actionable language.\n\n"
        "For each impacted entity:\n"
        "1. Explain WHY it's affected (the dependency chain)\n"
        "2. Rate the severity (critical/high/medium/low)\n"
        "3. Suggest mitigation actions\n"
        "4. Estimate the blast radius\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        change_description: str,
        impacted_entities: List[Dict[str, Any]],
        dependency_paths: List[str],
    ) -> str:
        return json.dumps({
            "proposed_change": change_description,
            "impacted_entities": impacted_entities[:20],
            "dependency_paths": dependency_paths[:20],
            "task": "Analyze the impact and provide actionable recommendations.",
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "blast_radius": {"type": "string"},
                "overall_risk": {"type": "string"},
                "impacted_services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string"},
                            "reason": {"type": "string"},
                            "severity": {"type": "string"},
                            "mitigation": {"type": "string"},
                        },
                    },
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["summary", "blast_radius", "overall_risk", "impacted_services"],
        }


# ---------------------------------------------------------------------------
# Time-Travel / Architecture Timeline Prompts
# ---------------------------------------------------------------------------

class ArchitectureDiffPrompt:
    """Generate natural language explanation of architecture changes between two states."""

    system_prompt = (
        "You are a principal engineer analyzing architecture evolution. "
        "Given two architecture states (before and after), explain the changes "
        "in clear, actionable language for engineering leadership.\n\n"
        "Focus on:\n"
        "1. Service additions, removals, and boundary changes\n"
        "2. Communication pattern shifts (sync -> async, coupling changes)\n"
        "3. Data model evolution and migration implications\n"
        "4. Infrastructure changes and operational impact\n"
        "5. Architecture drift from original intent\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        time_delta_days: int,
    ) -> str:
        return json.dumps({
            "before_state": before_state,
            "after_state": after_state,
            "time_delta_days": time_delta_days,
            "task": (
                "Analyze the architecture changes between these two states. "
                "Identify significant evolution patterns, drift from original design, "
                "and potential risks introduced."
            ),
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "description": {"type": "string"},
                            "severity": {"type": "string"},
                            "services_affected": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "drift_analysis": {
                    "type": "object",
                    "properties": {
                        "aligned_with_intent": {"type": "boolean"},
                        "drift_description": {"type": "string"},
                        "recommendations": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "risk_assessment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "risk": {"type": "string"},
                            "likelihood": {"type": "string"},
                            "impact": {"type": "string"},
                            "mitigation": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["summary", "changes", "drift_analysis"],
        }


class FailureReplayPrompt:
    """Explain how a failure propagated through the system."""

    system_prompt = (
        "You are a site reliability engineer analyzing incident propagation. "
        "Given a failure scenario and the dependency graph at the time of incident, "
        "explain how the failure cascaded through the system.\n\n"
        "For each step in the cascade:\n"
        "1. Identify the failure mode (timeout, error rate, resource exhaustion)\n"
        "2. Explain how it propagated to dependents\n"
        "3. Note which circuit breakers/resiliency patterns should have helped\n"
        "4. Suggest improvements to prevent similar cascades\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        root_cause: str,
        cascade_sequence: List[str],
        dependency_graph: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> str:
        return json.dumps({
            "root_cause": root_cause,
            "cascade_sequence": cascade_sequence,
            "dependency_graph": dependency_graph,
            "incident_context": incident_context,
            "task": (
                "Analyze how this failure propagated through the system. "
                "Explain the cascade mechanism and suggest improvements."
            ),
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "incident_summary": {"type": "string"},
                "cascade_analysis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "integer"},
                            "service": {"type": "string"},
                            "failure_mode": {"type": "string"},
                            "propagation_mechanism": {"type": "string"},
                            "duration_seconds": {"type": "integer"},
                        },
                    },
                },
                "resiliency_gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string"},
                            "missing_pattern": {"type": "string"},
                            "recommendation": {"type": "string"},
                        },
                    },
                },
                "recommended_improvements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["incident_summary", "cascade_analysis", "resiliency_gaps"],
        }


class FutureStatePrompt:
    """Model a hypothetical future architecture state given proposed changes."""

    system_prompt = (
        "You are a principal engineer modeling future architecture states. "
        "Given the current architecture and proposed changes (refactors, migrations, new services), "
        "produce a detailed future state analysis.\n\n"
        "Analyze:\n"
        "1. Structural changes to service boundaries\n"
        "2. New dependency relationships introduced\n"
        "3. Migration complexity and risk\n"
        "4. Operational implications (new SLOs, on-call burden)\n"
        "5. Comparison with architecture intent/roadmap\n\n"
        "Respond with JSON."
    )

    @staticmethod
    def user_prompt(
        current_state: Dict[str, Any],
        proposed_changes: List[Dict[str, Any]],
        constraints: Optional[List[str]] = None,
    ) -> str:
        return json.dumps({
            "current_state": current_state,
            "proposed_changes": proposed_changes,
            "constraints": constraints or [],
            "task": (
                "Model the future state of the architecture after these changes are implemented. "
                "Analyze risks, benefits, and migration strategy."
            ),
        })

    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "future_state": {
                    "type": "object",
                    "properties": {
                        "services": {"type": "array", "items": {"type": "object"}},
                        "dependencies": {"type": "array", "items": {"type": "object"}},
                        "infrastructure": {"type": "object"},
                    },
                },
                "change_analysis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "change": {"type": "string"},
                            "impact": {"type": "string"},
                            "risk_level": {"type": "string"},
                            "effort_estimate": {"type": "string"},
                        },
                    },
                },
                "migration_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "phase": {"type": "integer"},
                            "description": {"type": "string"},
                            "services_affected": {"type": "array", "items": {"type": "string"}},
                            "rollback_strategy": {"type": "string"},
                        },
                    },
                },
                "risk_assessment": {
                    "type": "object",
                    "properties": {
                        "overall_risk": {"type": "string"},
                        "top_risks": {"type": "array", "items": {"type": "object"}},
                        "mitigation_strategies": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "required": ["future_state", "change_analysis", "migration_plan"],
        }
