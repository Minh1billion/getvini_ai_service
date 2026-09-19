import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.schemas.qc import QCRunResponse
from app.api.schemas.spellcheck import SheetsResponse
from app.common.upload import save_upload
from app.core.config import get_settings
from app.domain.qc.verify_service import annotate_mismatches, verify_blocks, verify_blocks_stream
from app.domain.sheet_structure.scenario import describe_workbook, scan_content_blocks, scan_sheet
from app.infra.llm.client import LLMClient
from app.infra.sheet_reader import read_sheet

router = APIRouter(prefix="/qc", tags=["qc"])


async def _load_product_info(product_info: Optional[str], product_info_file: Optional[UploadFile]):
    if product_info_file is not None:
        raw, label = await product_info_file.read(), "product_info_file"
    elif product_info:
        raw, label = product_info, "product_info"
    else:
        raise HTTPException(status_code=400, detail="Cần cung cấp product_info hoặc product_info_file")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"{label} không hợp lệ: {e}")


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


async def _prepare_qc_run(
    sheet_name,
    file,
    url,
    product_info,
    product_info_file,
    provider,
    model,
    verify_model,
    api_key,
    scenario_ids,
):
    selected_scenario_ids = {s.strip() for s in scenario_ids.split(",") if s.strip()} if scenario_ids else None
    if not file and not url:
        raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")

    info = await _load_product_info(product_info, product_info_file)

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
        verify_llm = LLMClient(provider=provider, model=verify_model or model or get_settings().qc_verify_model, api_key=api_key)
    except Exception as e:
        if tmp_path:
            _safe_remove(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))

    content_blocks = await asyncio.to_thread(scan_content_blocks, sheet_name, rows, selected_scenario_ids)
    scanned_scenarios = await asyncio.to_thread(scan_sheet, sheet_name, rows)

    return content_blocks, scanned_scenarios, verify_llm, info, tmp_path


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@router.post("/run", response_model=QCRunResponse)
async def qc_run(
    sheet_name: str = Form(...),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    product_info: Optional[str] = Form(None),
    product_info_file: Optional[UploadFile] = File(None),
    provider: str = Form("groq"),
    model: Optional[str] = Form(None),
    verify_model: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
    batch_size: Optional[int] = Form(None),
    scenario_ids: Optional[str] = Form(None),
):
    content_blocks, scanned_scenarios, verify_llm, info, tmp_path = await _prepare_qc_run(
        sheet_name, file, url, product_info, product_info_file, provider, model, verify_model, api_key, scenario_ids,
    )
    if tmp_path:
        _safe_remove(tmp_path)

    models = {"verify": verify_llm.model}

    if not content_blocks:
        return {"content_blocks": content_blocks, "scanned_scenarios": scanned_scenarios, "mismatch_report": {"mismatches": []}, "models": models}

    try:
        report = await asyncio.to_thread(verify_blocks, verify_llm, content_blocks, info, batch_size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lỗi khi gọi LLM: {e}")

    return {
        "content_blocks": content_blocks,
        "scanned_scenarios": scanned_scenarios,
        "mismatch_report": annotate_mismatches(report, content_blocks, sheet_name),
        "models": models,
    }


@router.post("/run/stream")
async def qc_run_stream(
    sheet_name: str = Form(...),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    product_info: Optional[str] = Form(None),
    product_info_file: Optional[UploadFile] = File(None),
    provider: str = Form("groq"),
    model: Optional[str] = Form(None),
    verify_model: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
    scenario_ids: Optional[str] = Form(None),
    context_window: Optional[int] = Form(None),
):
    content_blocks, scanned_scenarios, verify_llm, info, tmp_path = await _prepare_qc_run(
        sheet_name, file, url, product_info, product_info_file, provider, model, verify_model, api_key, scenario_ids,
    )
    models = {"verify": verify_llm.model}

    async def event_source():
        try:
            yield f"data: {json.dumps({'content_blocks': content_blocks, 'scanned_scenarios': scanned_scenarios, 'models': models}, ensure_ascii=False)}\n\n"

            if not content_blocks:
                yield f"data: {json.dumps({'done': True, 'mismatch_report': {'mismatches': []}}, ensure_ascii=False)}\n\n"
                return

            gen = verify_blocks_stream(verify_llm, content_blocks, info, context_window=context_window)

            def next_item():
                try:
                    return next(gen)
                except StopIteration:
                    return None

            all_mismatches = []
            while True:
                item = await asyncio.to_thread(next_item)
                if item is None:
                    break
                if "batch_mismatches" in item:
                    annotated = annotate_mismatches({"mismatches": item["batch_mismatches"]}, content_blocks, sheet_name)
                    item["batch_mismatches"] = annotated["mismatches"]
                    all_mismatches.extend(annotated["mismatches"])
                    item["mismatches_so_far"] = list(all_mismatches)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True, 'mismatch_report': {'mismatches': all_mismatches}}, ensure_ascii=False)}\n\n"
        finally:
            if tmp_path:
                _safe_remove(tmp_path)

    return StreamingResponse(event_source(), media_type="text/event-stream")
