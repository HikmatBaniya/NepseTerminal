from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str
    role: str
    goal: str
    model: str = "llama3-8b-8192"
    tools: list[str] = Field(default_factory=list)
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    goal: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    is_active: bool | None = None


class AgentOut(AgentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunBase(BaseModel):
    run_type: str
    agent_id: UUID | None = None
    crew_name: str | None = None
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    agent_id: UUID
    input_text: str
    context: dict[str, Any] | None = None
    mode: str | None = None


class CrewRunRequest(BaseModel):
    agent_ids: list[UUID]
    objective: str
    context: dict[str, Any] | None = None
    crew_name: str | None = None
    mode: str | None = None


class RunOut(RunBase):
    id: UUID