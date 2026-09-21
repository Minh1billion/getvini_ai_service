import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas.qc import QCJobResponse, QCSubmitResponse
from app.api.schemas.spellcheck import SheetsResponse
from app.common.upload import save_upload
from app.domain.qc.verify_service import annotate_mismatches, verify_blocks
from app.domain.sheet_structure.scenario import describe_workbook, scan_content_blocks, scan_sheet
from app.infra.jobs.qc_queue import QcQueueFullError, submit as submit_qc_job
from app.infra.jobs.qc_store import get_qc_store
from app.infra.llm.client import LLMClient
from app.infra.sheet_reader import read_sheet

router = APIRouter(prefix="/qc", tags=["qc"])


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@router.post("/sheets", response_model=SheetsResponse)
async def qc_sheets(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    if file is not None:
        path, _ = await save_upload(file)
        try:
            return await asyncio.to_thread(describe_workbook, path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            os.remove(path)
    if url:
        raise HTTPException(status_code=400, detail="Liệt kê sheet chỉ hỗ trợ upload file, không hỗ trợ qua url")
    raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")


@router.post("/run", response_model=QCSubmitResponse)
async def qc_run(
    sheet_name: str = Form(...),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    product_info: str = Form(...),
    provider: Optional[str] = Form(None),
    verify_model: Optional[str] = Form(None),
    scenario_ids: Optional[str] = Form(None),
    context_window: Optional[int] = Form(None),
    max_scenarios_per_batch: Optional[int] = Form(None),
):
    selected_scenario_ids = {s.strip() for s in scenario_ids.split(",") if s.strip()} if scenario_ids else None
    if not file and not url:
        raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")

    try:
        info = json.loads(product_info)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"product_info không hợp lệ: {e}")

    tmp_path = None
    source = url
    if file is not None:
        tmp_path, _ = await save_upload(file)
        source = tmp_path

    try:
        rows = await asyncio.to_thread(read_sheet, source, sheet_name)
    except Exception as e:
        if tmp_path:
            _safe_remove(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))

    try:
        verify_llm = LLMClient(provider=provider, model=verify_model)
    except Exception as e:
        if tmp_path:
            _safe_remove(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))

    content_blocks = await asyncio.to_thread(scan_content_blocks, sheet_name, rows, selected_scenario_ids)
    scanned_scenarios = await asyncio.to_thread(scan_sheet, sheet_name, rows)

    if tmp_path:
        _safe_remove(tmp_path)

    store = get_qc_store()
    job_id = store.create(len(content_blocks))

    models = {"verify": verify_llm.model}

    if not content_blocks:
        store.update(
            job_id,
            status="done",
            content_blocks=content_blocks,
            scanned_scenarios=scanned_scenarios,
            mismatch_report={"mismatches": []},
            models=models,
        )
        return {"job_id": job_id, "total": 0}

    def run_job():
        store.update(job_id, status="running")
        try:
            report = verify_blocks(
                verify_llm,
                content_blocks,
                info,
                context_window=context_window,
                max_scenarios_per_batch=max_scenarios_per_batch,
            )
            annotated = annotate_mismatches(report, content_blocks, sheet_name)
            store.update(
                job_id,
                status="done",
                content_blocks=content_blocks,
                scanned_scenarios=scanned_scenarios,
                mismatch_report=annotated,
                models=models,
            )
        except Exception as e:
            store.update(job_id, status="error", error=str(e))

    try:
        submit_qc_job(run_job)
    except QcQueueFullError:
        store.update(job_id, status="error", error="Hệ thống đang quá tải, vui lòng thử lại sau")
        raise HTTPException(status_code=503, detail="Hệ thống đang quá tải, vui lòng thử lại sau")

    return {"job_id": job_id, "total": len(content_blocks)}


@router.get("/run/{job_id}", response_model=QCJobResponse)
async def qc_run_status(job_id: str):
    job = get_qc_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
