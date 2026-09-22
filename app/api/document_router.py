import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas.document import (
    DocumentExtractResponse,
    ProductInfoFormatRequest,
    ProductInfoFormatResponse,
)
from app.common.upload import save_upload, save_upload_from_url
from app.domain.document_extract.service import extract_text
from app.domain.product_info_format.service import format_product_info

router = APIRouter(prefix="/documents", tags=["documents"])


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@router.post("/extract", response_model=DocumentExtractResponse)
async def documents_extract(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Cần cung cấp file hoặc url")

    if file is not None:
        path, _ = await save_upload(file)
        filename = file.filename or ""
    else:
        path, _ = await save_upload_from_url(url)
        filename = url

    try:
        text, has_complex_layout = extract_text(path, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể trích xuất nội dung file: {e}")
    finally:
        _safe_remove(path)

    return {"text": text, "has_complex_layout": has_complex_layout}


@router.post("/format-product-info", response_model=ProductInfoFormatResponse)
async def documents_format_product_info(payload: ProductInfoFormatRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Cần cung cấp nội dung để format")

    try:
        html = format_product_info(
            payload.text,
            product_name=payload.product_name,
            provider=payload.provider,
            model=payload.model,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể format nội dung: {e}")

    return {"html": html}
