# -*- coding: utf-8 -*-
"""Curated V2 Data API request contracts.

The public API deliberately accepts a small, allow-listed query language.  An
Agent may choose filters and paths, but it may not submit SQL or SPARQL through
these models.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProductType = Literal[
    "BOND",
    "ETF_KR",
    "ETF_GL",
    "ETN_KR",
    "ETN_GL",
    "FUND_PUB",
    "FUND_PRIVATE",
]
MetricCode = Literal["AUM", "RETURN_1Y", "EXPENSE_RATIO"]
FilterField = Literal[
    "AUM",
    "RETURN_1Y",
    "EXPENSE_RATIO",
    "MATURITY_DATE",
    "CREDIT_RATING_RANK",
    "ASSUMED_PURCHASABLE",
    "BUY_YIELD",
]
FilterOperator = Literal["eq", "gt", "gte", "lt", "lte"]
RelationStep = Literal[
    "holds_security",
    "held_by_product",
    "parent_of",
    "issued_bond",
    "has_document",
    "same_vehicle_as",
]


class ProductSearchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    match: Literal["exact", "normalized_exact", "contains"] = "exact"
    product_types: list[ProductType] = Field(default_factory=list, max_length=7)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name은 공백일 수 없습니다")
        return value


class ProductFilter(BaseModel):
    field: FilterField
    op: FilterOperator
    value: str | float | bool


class ProductQueryRequest(BaseModel):
    product_types: list[ProductType] = Field(default_factory=list, max_length=7)
    market_scope: Literal["KR", "GL"] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=16)
    filters: list[ProductFilter] = Field(default_factory=list, max_length=8)
    sort_by: FilterField | Literal["NAME"] = "NAME"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def require_aum_unit(self) -> ProductQueryRequest:
        uses_aum = self.sort_by == "AUM" or any(item.field == "AUM" for item in self.filters)
        if uses_aum and not self.currency:
            raise ValueError("AUM 비교·필터에는 currency가 필요합니다")
        return self


class ProductCompareRequest(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=20)
    metric_codes: list[MetricCode] = Field(min_length=1, max_length=3)

    @field_validator("product_ids")
    @classmethod
    def unique_product_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("빈 product_id는 허용하지 않습니다")
        if len(normalized) != len(set(normalized)):
            raise ValueError("product_ids는 중복될 수 없습니다")
        return normalized

    @field_validator("metric_codes")
    @classmethod
    def unique_metric_codes(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("metric_codes는 중복될 수 없습니다")
        return values


class RelationTraverseRequest(BaseModel):
    start_entity_id: str = Field(min_length=1, max_length=300)
    path: list[RelationStep] = Field(min_length=1, max_length=3)
    as_of: date | Literal["latest"] = "latest"
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("start_entity_id")
    @classmethod
    def strip_start_id(cls, value: str) -> str:
        return value.strip()


class OntologyValidateRequest(BaseModel):
    validation_type: Literal["credit_rating", "relation_domain", "cutoff"]
    value: str | None = Field(default=None, max_length=100)
    relation: RelationStep | None = None
    subject_product_id: str | None = Field(default=None, max_length=300)
    requested_as_of: date | None = None


class EvidenceSearchRequest(BaseModel):
    query_embedding: list[float] = Field(min_length=1024, max_length=1024)
    candidate_product_ids: list[str] | None = Field(default=None, max_length=20)
    top_k: int = Field(default=2, ge=1, le=2)

    @field_validator("query_embedding")
    @classmethod
    def validate_embedding(cls, values: list[float]) -> list[float]:
        converted = [float(value) for value in values]
        if not all(isfinite(value) for value in converted):
            raise ValueError("query_embedding에는 유한한 숫자만 허용합니다")
        if not any(value != 0.0 for value in converted):
            raise ValueError("query_embedding은 영벡터일 수 없습니다")
        return converted

    @field_validator("candidate_product_ids")
    @classmethod
    def normalize_candidate_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("빈 candidate product_id는 허용하지 않습니다")
        return list(dict.fromkeys(normalized))


class ApiProblem(BaseModel):
    code: str
    message: str
    release_id: str
    details: dict[str, Any] = Field(default_factory=dict)
