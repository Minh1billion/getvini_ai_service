from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.api.schemas.spellcheck import ScenarioInfo


class ContentBlock(BaseModel):
    id: str
    sheet: str
    scenario: str
    row_range: List[int]
    content: str


class MismatchReport(BaseModel):
    mismatches: List[Dict[str, Any]]


class QCModels(BaseModel):
    verify: str


class QCRunResponse(BaseModel):
    content_blocks: List[ContentBlock]
    scanned_scenarios: List[ScenarioInfo]
    mismatch_report: MismatchReport
    models: QCModels


class QCSubmitResponse(BaseModel):
    job_id: str
    total: int


class QCJobResponse(BaseModel):
    status: str
    total: int
    content_blocks: Optional[List[ContentBlock]] = None
    scanned_scenarios: Optional[List[ScenarioInfo]] = None
    mismatch_report: Optional[MismatchReport] = None
    models: Optional[QCModels] = None
    error: Optional[str] = None
