from typing import Literal, Optional
from pydantic import BaseModel, field_validator


class AgentFindingModel(BaseModel):
    agent_id: str
    status: Literal["success", "no_match", "timeout", "error"]
    root_cause: Optional[str]
    confidence: float
    justification: str
    resolution_steps: list[str]
    evidence: list[str]
    timestamp: str

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("justification")
    @classmethod
    def justification_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("justification must be a non-empty, non-whitespace string")
        return v
