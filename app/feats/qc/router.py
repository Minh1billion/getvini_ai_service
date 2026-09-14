import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.common import list_sheet_names, save_upload
from app.feats.qc.llm_client import LLMClient
from app.feats.qc.extract import extract_blocks
from app.feats.qc.verify import verify_blocks
from app.feats.qc.sheet_reader import read_sheet

router = APIRouter(prefix="/qc", tags=["qc"])


@router.post("/sheets")
async def qc_sheets(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    if file is not None:
        path, ext = await save_upload(file)
        try:
            names = await asyncio.to_thread(list_sheet_names, path)
            return JSONResponse({"sheets": names})
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            os.remove(path)
    if url:
        raise HTTPException(status_code=400, detail="Liệt kê sheet chỉ hỗ trợ upload file, không hỗ trợ qua url")
    raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")


@router.post("/run")
async def qc_run(
    sheet_name: str = Form(...),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    product_info: Optional[str] = Form(None),
    product_info_file: Optional[UploadFile] = File(None),
    provider: str = Form("groq"),
    model: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
    batch_size: int = Form(20),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")

    if product_info_file is not None:
        content = await product_info_file.read()
        try:
            info = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"product_info_file không hợp lệ: {e}")
    elif product_info:
        try:
            info = json.loads(product_info)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"product_info không hợp lệ: {e}")
    else:
        raise HTTPException(status_code=400, detail="Cần cung cấp product_info hoặc product_info_file")

    tmp_path = None
    source = url
    if file is not None:
        tmp_path, _ = await save_upload(file)
        source = tmp_path

    try:
        rows = await asyncio.to_thread(read_sheet, source, sheet_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    try:
        llm = LLMClient(provider=provider, model=model, api_key=api_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        content_blocks = await asyncio.to_thread(extract_blocks, llm, rows)
        mismatch_report = await asyncio.to_thread(verify_blocks, llm, content_blocks["blocks"], info, batch_size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lỗi khi gọi LLM: {e}")

    return JSONResponse({"content_blocks": content_blocks, "mismatch_report": mismatch_report})