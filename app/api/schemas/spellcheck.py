from typing import Dict, List, Optional

from pydantic import BaseModel


class ScenarioInfo(BaseModel):
    id: str
    sheet: str
    scenarioLabel: str
    headerRow: int
    startRow: Optional[int]
    endRow: Optional[int]
    colWidth: int


class SheetsResponse(BaseModel):
    sheets: List[str]
    scenarios: Optional[Dict[str, List[ScenarioInfo]]] = None


class SpellError(BaseModel):
    location: str
    token: str
    sheet: Optional[str] = None
    scenario: Optional[str] = None
    scenarioId: Optional[str] = None


class TextCheckResponse(BaseModel):
    errors: List[SpellError]


class StartResponse(BaseModel):
    job_id: str
    total: int


class JobResponse(BaseModel):
    status: str
    processed: int
    total: int
    progress: float
    errors: List[SpellError]
    scanned_scenarios: List[ScenarioInfo]
    error: Optional[str] = None


class DeleteResponse(BaseModel):
    deleted: str
