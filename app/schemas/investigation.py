from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceFact(BaseModel):
    value: str
    source_urls: list[str] = Field(default_factory=list)
    supporting_quote: str


class InvestigationSource(BaseModel):
    url: str
    title: str
    source_type: str
    retrieved_at: datetime


class InvestigationDraft(BaseModel):
    title: EvidenceFact | None = None
    deadline: EvidenceFact | None = None
    eligibility: list[EvidenceFact] = Field(default_factory=list)
    required_skills: list[EvidenceFact] = Field(default_factory=list)
    salary: EvidenceFact | None = None
    location: EvidenceFact | None = None
    application_steps: list[EvidenceFact] = Field(default_factory=list)
    required_documents: list[EvidenceFact] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class InvestigationResult(InvestigationDraft):
    sources: list[InvestigationSource] = Field(default_factory=list)
