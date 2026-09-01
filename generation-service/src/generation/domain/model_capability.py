"""Canonical model capability, pricing and bounded fallback decisions."""

from dataclasses import dataclass
from typing import Mapping


class ModelUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    provider: str
    input_types: frozenset[str]
    output_type: str
    max_duration_seconds: int
    resolutions: frozenset[str]
    supports_reference_images: bool
    price_version: str
    price_points: int
    fallback_group: str
    retry_budget: int

    def validate(self, params: Mapping[str, object]) -> None:
        duration = params.get("duration_seconds")
        resolution = params.get("resolution")
        if not isinstance(duration, int) or duration < 1 or duration > self.max_duration_seconds:
            raise ModelUnavailable("UNSUPPORTED_PARAMETER")
        if not isinstance(resolution, str) or resolution not in self.resolutions:
            raise ModelUnavailable("UNSUPPORTED_PARAMETER")


class ModelResolver:
    def __init__(self, capabilities: list[ModelCapability]) -> None:
        self._capabilities = {capability.model_id: capability for capability in capabilities}

    def resolve(self, model_id: str, params: Mapping[str, object]) -> ModelCapability:
        capability = self._capabilities.get(model_id)
        if capability is None:
            raise ModelUnavailable("MODEL_UNAVAILABLE")
        capability.validate(params)
        return capability

    def estimate(self, model_id: str, params: Mapping[str, object]) -> int:
        return self.resolve(model_id, params).price_points

    def resolve_with_fallback(self, model_id: str, params: Mapping[str, object], failed_models: set[str], cost_cap: int) -> ModelCapability:
        primary = self.resolve(model_id, params)
        candidates = [primary] + [candidate for candidate in self._capabilities.values() if candidate.fallback_group == primary.fallback_group and candidate.model_id != model_id]
        for candidate in candidates:
            if candidate.model_id in failed_models:
                continue
            candidate.validate(params)
            if candidate.price_points > cost_cap:
                continue
            return candidate
        raise ModelUnavailable("RETRY_BUDGET_EXHAUSTED")
