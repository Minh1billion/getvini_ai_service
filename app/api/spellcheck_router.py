import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.schemas.spellcheck import DeleteResponse, JobResponse, SheetsResponse, StartResponse, TextCheckResponse
from app.common.upload import SPREADSHEET_EXTS, save_upload
from app.domain.sheet_structure.scenario import describe_workbook
from app.domain.spellcheck import service
from app.infra.jobs import runner
from app.infra.jobs.store import get_store
from app.infra.pdf.report import build_spellcheck_pdf

router = APIRouter(prefix="/check", tags=["spellcheck"])


async def _prepare(file: UploadFile, sheet_names: Optional[str], scenario_ids: Optional[str] = None):
    path, ext = await save_upload(file)
    try:
        ids = {s.strip() for s in scenario_ids.split(",") if s.strip()} if scenario_ids else None
        units, scanned_scenarios = await asyncio.to_thread(service.extract_units, path, ext, sheet_names, ids)
    except Exception as e:
        os.remove(path)
        raise HTTPException(status_code=400, detail=str(e))
    return path, units, scanned_scenarios


@router.post("/sheets", response_model=SheetsResponse, response_model_exclude_unset=True)
async def check_sheets(file: UploadFile = File(...)):
    path, ext = await save_upload(file)
    try:
        if ext not in SPREADSHEET_EXTS:
            return {"sheets": []}
        return await asyncio.to_thread(describe_workbook, path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.remove(path)


@router.post("/start", response_model=StartResponse)
async def check_start(
    file: UploadFile = File(...),
    lang: str = Form("both"),
    sheet_names: Optional[str] = Form(None),
    whitelist: Optional[str] = Form(None),
    scenario_ids: Optional[str] = Form(None),
):
    path, units, scanned_scenarios = await _prepare(file, sheet_names, scenario_ids)
    job_id, total = runner.start_job(get_store(), path, units, scanned_scenarios, service.parse_whitelist(whitelist), lang)
    return {"job_id": job_id, "total": total}


@router.post("/stream")
async def check_stream(
    file: UploadFile = File(...),
    lang: str = Form("both"),
    sheet_names: Optional[str] = Form(None),
    whitelist: Optional[str] = Form(None),
    scenario_ids: Optional[str] = Form(None),
):
    path, units, scanned_scenarios = await _prepare(file, sheet_names, scenario_ids)

    async def event_source():
        async for payload in runner.stream_job(get_store(), path, units, scanned_scenarios, service.parse_whitelist(whitelist), lang):
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/text", response_model=TextCheckResponse)
async def check_text(text: str = Form(...), lang: str = Form("vi"), whitelist: Optional[str] = Form(None)):
    unit = {"location": "text", "text": text, "sheet": None, "scenario": None, "scenarioId": None}
    errors = await asyncio.to_thread(service.check_unit, unit, service.parse_whitelist(whitelist), lang)
    return {"errors": errors}


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = get_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/{job_id}/pdf")
async def get_job_pdf(job_id: str):
    job = get_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="job not finished")

    buffer = await asyncio.to_thread(build_spellcheck_pdf, job)
    headers = {"Content-Disposition": f'attachment; filename="report_{job_id}.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@router.delete("/{job_id}", response_model=DeleteResponse)
async def delete_job(job_id: str):
    if not get_store().delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"deleted": job_id}
