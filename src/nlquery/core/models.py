"""Serializable public schema, intent, IR, plan, policy and result contracts."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$", max_length=160)]
Scalar = str | int | float | bool | None


class Model(BaseModel):
    """Immutable attributes; revalidate all untrusted copies at trust boundaries."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False
    )


class FieldSchema(Model):
    """A typed column, document path, graph property, tag or issue field."""

    name: Name
    data_type: Literal[
        "string", "integer", "number", "boolean", "datetime", "array", "object", "unknown"
    ] = "unknown"
    nullable: bool = True
    primary_key: bool = False
    indexed: bool = False
    description: str = ""
    native_type: str = ""
    role: Literal["field", "tag", "time", "key"] = "field"


class Relationship(Model):
    """A declared relational edge or graph relationship."""

    name: Name
    source: Name
    target: Name
    source_field: Name | None = None
    target_field: Name | None = None
    properties: list[FieldSchema] = Field(default_factory=list)


class SourceSchema(Model):
    """One entity with explicit storage semantics."""

    name: Name
    kind: Literal["table", "view", "node", "collection", "measurement", "key", "issues"] = "table"
    fields: list[FieldSchema]
    description: str = ""
    namespace: Name | None = None
    key: str | None = None
    key_type: Literal["hash", "set", "zset", "stream", "json", "search"] | None = None
    bucket: str | None = None
    time_field: Name | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_fields(self) -> SourceSchema:
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ValueError("Duplicate field names")
        return self


class SchemaModel(Model):
    """Bounded normalized metadata; never store connection configuration here."""

    sources: list[SourceSchema]
    relationships: list[Relationship] = Field(default_factory=list)
    backend: str = "sqlite"

    @model_validator(mode="after")
    def unique_sources(self) -> SchemaModel:
        if len({s.name for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate sources")
        if len({r.name for r in self.relationships}) != len(self.relationships):
            raise ValueError(
                "Relationship names must be unique; composite edges need explicit modeling"
            )
        return self


class Filter(Model):
    """Predicate values are data, not expressions or query fragments."""

    field: Name
    operator: Literal[
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "in",
        "not_in",
        "contains",
        "exists",
        "is_null",
        "relative_time",
    ] = "="
    value: Scalar | list[Scalar] = None


class Predicate(Model):
    """Recursive AND/OR/NOT expression; NOT requires exactly one child."""

    operator: Literal["and", "or", "not"] = "and"
    terms: list[Filter | Predicate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unary_not(self) -> Predicate:
        if self.operator == "not" and len(self.terms) != 1:
            raise ValueError("NOT requires one predicate")
        return self


class Metric(Model):
    """Explicit aggregate and safe output name."""

    field: Name | Literal["*"]
    aggregation: Literal["sum", "avg", "min", "max", "count"]
    alias: Name


class Sort(Model):
    field: Name
    direction: Literal["asc", "desc"] = "asc"


class Projection(Model):
    field: Name
    alias: Name | None = None


class Join(Model):
    """A declared relationship, never arbitrary SQL."""

    relationship: Name
    kind: Literal["inner", "left"] = "inner"


class Traversal(Model):
    relationship: Name
    direction: Literal["out", "in", "both"] = "out"
    min_depth: int = Field(default=1, ge=1)
    max_depth: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def depth_order(self) -> Traversal:
        if self.min_depth > self.max_depth:
            raise ValueError("Invalid traversal depth range")
        return self


class TimeWindow(Model):
    field: Name
    every: str = Field(pattern=r"^[1-9][0-9]{0,5}(s|m|h|d|w)$")
    alias: Name = "time_bucket"


class Calculation(Model):
    """Restricted arithmetic between schema fields, with no raw code."""

    left: Name
    operator: Literal["+", "-", "*", "/"]
    right: Name
    alias: Name


class Ambiguity(Model):
    term: str
    candidates: list[str]
    reason: str = "Multiple plausible interpretations"


class ConfidenceComponent(Model):
    category: str
    subject: str
    selected: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]


class ConfidenceAssessment(Model):
    overall: float = Field(default=0, ge=0, le=1)
    components: list[ConfidenceComponent] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class Provenance(Model):
    subject: str
    selected: str
    evidence: str
    stage: str = "grounding"


class QueryIntent(Model):
    """Provider-neutral semantics. Unsupported constructs must fail explicitly."""

    operation: Literal["select", "aggregate", "search", "traverse"] = "select"
    sources: list[Name] = Field(min_length=1, max_length=8)
    projections: list[Projection] = Field(default_factory=list)
    dimensions: list[Name] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    predicate: Predicate | None = None
    sort: list[Sort] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000000)
    offset: int = Field(default=0, ge=0, le=1000000)
    distinct: bool = False
    joins: list[Join] = Field(default_factory=list)
    traversal: Traversal | None = None
    window: TimeWindow | None = None
    unwind: list[Name] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    backend_hints: list[str] = Field(default_factory=list)


class QueryIR(QueryIntent):
    """Grounded intent with resolved identifiers and absolute time boundaries."""


class PlanNode(Model):
    operation: Literal[
        "Scan",
        "Filter",
        "Traverse",
        "Join",
        "Project",
        "Aggregate",
        "Window",
        "Sort",
        "Limit",
        "Search",
        "TimeRange",
        "DocumentMatch",
        "Unwind",
    ]
    provenance: list[Provenance] = Field(default_factory=list)


class QueryPlan(Model):
    """Inspectable logical operators plus canonical executable semantics."""

    ir: QueryIR
    nodes: list[PlanNode]
    confidence: ConfidenceAssessment
    provenance: list[Provenance]
    reference_time: str


class ConnectorCapabilities(Model):
    """Semantic capability negotiation is independent of backend identity."""

    joins: bool = False
    aggregation: bool = False
    graph_traversal: bool = False
    time_series: bool = False
    arrays: bool = False
    calculations: bool = False
    distinct: bool = False
    projection: bool = True
    sorting: bool = True
    offsets: bool = True
    explain: bool = False
    writes: bool = False
    extensions: list[str] = Field(default_factory=list)


class ConfidencePolicy(Model):
    auto_compile_threshold: float = Field(default=0.8, ge=0, le=1)
    clarification_threshold: float = Field(default=0.6, ge=0, le=1)
    reject_threshold: float = Field(default=0.35, ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> ConfidencePolicy:
        if not self.reject_threshold <= self.clarification_threshold <= self.auto_compile_threshold:
            raise ValueError("Confidence thresholds must be ordered")
        return self


class QueryPolicy(Model):
    """Limits are rechecked at execution, never taken from model output."""

    read_only: Literal[True] = True
    max_rows: int = Field(default=1000, ge=1, le=100000)
    max_execution_seconds: float = Field(default=30, gt=0, le=300)
    max_graph_depth: int = Field(default=5, ge=1, le=10)
    max_joins: int = Field(default=4, ge=0, le=7)
    max_offset: int = Field(default=10000, ge=0)
    allow_cross_source: Literal[False] = False
    allowed_sources: list[str] | None = None
    confidence: ConfidencePolicy = Field(default_factory=ConfidencePolicy)


class DiscoveryConfig(Model):
    max_sources: int = Field(default=100, ge=1, le=1000)
    max_fields: int = Field(default=200, ge=1, le=1000)
    sample_size: int = Field(default=50, ge=1, le=1000)
    max_context_sources: int = Field(default=8, ge=1, le=30)
    max_context_chars: int = Field(default=30000, ge=1000, le=100000)
    ttl_seconds: float = Field(default=300, ge=0)


class QueryRisk(Model):
    level: Literal["low", "medium", "high", "blocked"] = "low"
    reasons: list[str] = Field(default_factory=list)


class CompiledQuery(Model):
    """A proposal, not an authorization token. Execution rederives the operation."""

    backend: str
    language: str
    query: Any
    parameters: dict[str, Any] = Field(default_factory=dict)
    plan: QueryPlan
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    referenced_objects: list[str]
    risk: QueryRisk
    confidence: ConfidenceAssessment
    provenance: list[Provenance]

    @property
    def generated_query(self) -> Any:
        return self.query


class ValidationResult(Model):
    allowed: bool
    errors: list[str] = Field(default_factory=list)


class QueryResult(Model):
    """Rows preserve nested backend values rather than flattening them away."""

    kind: Literal["tabular", "document", "graph", "timeseries", "keyvalue", "issues"] = "tabular"
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    backend: str
    execution_time_ms: float
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def data(self) -> list[dict[str, Any]]:
        return self.rows


class SemanticConcept(Model):
    description: str = ""
    candidates: list[Name]
    aliases: list[str] = Field(default_factory=list)
    preferred: Name | None = None
    deprecated: list[Name] = Field(default_factory=list)
    units: str | None = None
    time_semantics: str | None = None
    aggregation: Literal["sum", "avg", "min", "max", "count"] | None = None
    condition: Filter | None = None
    source_metadata: dict[str, str] = Field(default_factory=dict)


class SemanticCatalog(Model):
    concepts: dict[str, SemanticConcept] = Field(default_factory=dict)


def checked_name(name: str) -> str:
    """Validate compiler identifiers even when called outside the public API."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,159}", name):
        from nlquery.exceptions import ValidationError

        raise ValidationError("Unsupported identifier syntax")
    return name
