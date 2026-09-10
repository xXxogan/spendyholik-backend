"""Input/output DTOs for the goals application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.domain.money import Money


class CreateGoalInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    target_amount_minor: int = Field(gt=0)
    currency: str
    account_id: UUID
    initial_amount_minor: int = Field(default=0, ge=0)
    deadline: date | None = None
    icon: str = "flag"
    color: str = "goal"


class UpdateGoalInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount_minor: int | None = Field(default=None, gt=0)
    deadline: date | None = None
    icon: str | None = None
    color: str | None = None


class ContributeToGoalInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    amount_minor: int = Field(gt=0)
    date: date


@dataclass(frozen=True, slots=True)
class GoalDTO:
    id: UUID
    name: str
    target_amount: Money
    current_amount: Money
    account_id: UUID
    deadline: date | None
    icon: str
    color: str
    progress: float  # 0.0 .. 1.0


@dataclass(frozen=True, slots=True)
class GoalContributionDTO:
    id: UUID
    goal_id: UUID
    account_id: UUID
    amount: Money
    date: date


@dataclass(frozen=True, slots=True)
class GoalForecastDTO:
    goal_id: UUID
    remaining: Money
    projected_completion: date | None  # None when no contributions yet
