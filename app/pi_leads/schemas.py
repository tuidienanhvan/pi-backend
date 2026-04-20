"""Pi Leads backend DTOs."""

from pydantic import BaseModel


class LeadData(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    message: str = ""


class LeadScoreRequest(BaseModel):
    lead: LeadData


class LeadScoreResponse(BaseModel):
    success: bool
    score: int
    reasoning: str


class LeadEnrichRequest(BaseModel):
    domain: str


class LeadEnrichResponse(BaseModel):
    success: bool
    company: dict
