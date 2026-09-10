import asyncio
import io
import json
import os
import threading
import time
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import structural as sc

from app.common import SPREADSHEET_EXTS, list_sheet_names, resolve_sheet_names, save_upload
from app.common_pdf import VN_FONT, VN_FONT_BOLD, ensure_vn_fonts

router = APIRouter(prefix="/check", tags=["spellcheck"])

JOBS: dict = {}
JOBS_LOCK = threading.Lock()
CANCEL_EVENTS: dict = {}

ensure_vn_fonts()


def extract_units(path: str, ext: str, sheet_names: Optional[str]):
    units = []
    if ext in SPREADSHEET_EXTS:
        selected_sheets = resolve_sheet_names(path, sheet_names)
        multi = len(selected_sheets) > 1
        for sheet in selected_sheets:
            raw = sc.read_sheet(path, sheet)
            for entry in json.loads(raw):
                location = f"R{entry['row'] + 1}C{entry['col'] + 1}"
                if multi:
                    location = f"{sheet}!{location}"
                value = str(entry.get("value", ""))
                if value.strip():
                    units.append((location, value))
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                line = line.rstrip("\n")
                if line.strip():
                    units.append((f"L{i + 1}", line))
    return units


def check_unit(location: str, text: str, whitelist: list, lang: str):
    errors = []
    for token in sc.tokenize(text):
        for sub, tag in sc.tag(token):
            if tag != "WORD":
                continue
            if sc.check(sub, whitelist, lang):
                errors.append({"location": location, "token": sub})
    return errors


def process_job(job_id: str, units: list, whitelist: list, lang: str, cancel_event: threading.Event):
    total = len(units)
    if total == 0:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["finished_at"] = time.time()
        yield 0, 0
        return

    step = max(1, total // 100)
    processed = 0
    errors = []
    for location, text in units:
        if cancel_event.is_set():
            return
        errors.extend(check_unit(location, text, whitelist, lang))
        processed += 1
        if processed % step == 0 or processed == total:
            with JOBS_LOCK:
                if job_id not in JOBS:
                    return
                JOBS[job_id]["processed"] = processed
                JOBS[job_id]["progress"] = processed / total
            yield processed, total

    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["errors"] = errors
            JOBS[job_id]["finished_at"] = time.time()


def run_job_in_background(job_id: str, path: str, units: list, whitelist: list, lang: str, cancel_event: threading.Event):
    try:
        for _ in process_job(job_id, units, whitelist, lang, cancel_event):
            pass
    except Exception as e:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
                JOBS[job_id]["finished_at"] = time.time()
    finally:
        with JOBS_LOCK:
            CANCEL_EVENTS.pop(job_id, None)
        try:
            os.remove(path)
        except OSError:
            pass


def group_errors(errors: list):
    grouped = {}
    order = []
    for err in errors:
        token = err["token"]
        if token not in grouped:
            grouped[token] = []
            order.append(token)
        grouped[token].append(err["location"])

    groups = [(token, grouped[token]) for token in order]
    groups.sort(key=lambda item: len(item[1]), reverse=True)
    return groups


def build_pdf(job: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("VNTitle", parent=styles["Title"], fontName=VN_FONT_BOLD)
    header_style = ParagraphStyle("VNHeader", fontName=VN_FONT_BOLD, fontSize=9, textColor=colors.white, alignment=TA_LEFT)
    cell_style = ParagraphStyle("VNCell", fontName=VN_FONT, fontSize=9, leading=12, alignment=TA_LEFT)

    elements = [Paragraph("Báo cáo lỗi chính tả", title_style), Spacer(1, 12)]
    groups = group_errors(job["errors"])

    data = [[Paragraph("Từ lỗi", header_style), Paragraph("Tần suất", header_style), Paragraph("Vị trí", header_style)]]
    for token, locations in groups:
        data.append([Paragraph(token, cell_style), Paragraph(str(len(locations)), cell_style), Paragraph(", ".join(locations), cell_style)])

    table = Table(data, colWidths=[110, 60, 330], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer


@router.post("/sheets")
async def check_sheets(file: UploadFile = File(...)):
    path, ext = await save_upload(file)
    try:
        if ext not in SPREADSHEET_EXTS:
            return JSONResponse({"sheets": []})
        names = await asyncio.to_thread(list_sheet_names, path)
        return JSONResponse({"sheets": names})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.remove(path)


@router.post("/start")
async def check_start(
    file: UploadFile = File(...),
    lang: str = Form("both"),
    sheet_names: Optional[str] = Form(None),
    whitelist: Optional[str] = Form(None),
):
    path, ext = await save_upload(file)
    wl = [w.strip() for w in whitelist.split(",")] if whitelist else []

    try:
        units = await asyncio.to_thread(extract_units, path, ext, sheet_names)
    except Exception as e:
        os.remove(path)
        raise HTTPException(status_code=400, detail=str(e))

    job_id = uuid.uuid4().hex
    cancel_event = threading.Event()
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "processed": 0, "total": len(units), "progress": 0.0, "errors": [], "created_at": time.time()}
        CANCEL_EVENTS[job_id] = cancel_event

    thread = threading.Thread(target=run_job_in_background, args=(job_id, path, units, wl, lang, cancel_event), daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id, "total": len(units)})


@router.post("/stream")
async def check_stream(
    file: UploadFile = File(...),
    lang: str = Form("both"),
    sheet_names: Optional[str] = Form(None),
    whitelist: Optional[str] = Form(None),
):
    path, ext = await save_upload(file)
    wl = [w.strip() for w in whitelist.split(",")] if whitelist else []

    try:
        units = await asyncio.to_thread(extract_units, path, ext, sheet_names)
    except Exception as e:
        os.remove(path)
        raise HTTPException(status_code=400, detail=str(e))

    job_id = uuid.uuid4().hex
    cancel_event = threading.Event()
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "processed": 0, "total": len(units), "progress": 0.0, "errors": [], "created_at": time.time()}
        CANCEL_EVENTS[job_id] = cancel_event

    async def event_source():
        try:
            gen = process_job(job_id, units, wl, lang, cancel_event)

            def next_item():
                try:
                    return next(gen)
                except StopIteration:
                    return None

            while True:
                try:
                    result = await asyncio.to_thread(next_item)
                except Exception as e:
                    with JOBS_LOCK:
                        if job_id in JOBS:
                            JOBS[job_id]["status"] = "error"
                            JOBS[job_id]["error"] = str(e)
                            JOBS[job_id]["finished_at"] = time.time()
                    yield f"data: {json.dumps({'job_id': job_id, 'error': str(e)})}\n\n"
                    break

                if result is None:
                    break
                processed, total = result
                payload = {"job_id": job_id, "processed": processed, "total": total, "progress": (processed / total) if total else 1.0}
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            with JOBS_LOCK:
                CANCEL_EVENTS.pop(job_id, None)
            try:
                os.remove(path)
            except OSError:
                pass

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/text")
async def check_text(text: str = Form(...), lang: str = Form("vi"), whitelist: Optional[str] = Form(None)):
    wl = [w.strip() for w in whitelist.split(",")] if whitelist else []
    errors = await asyncio.to_thread(check_unit, "text", text, wl, lang)
    return JSONResponse({"errors": errors})


@router.get("/{job_id}")
async def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse({
        "status": job["status"],
        "processed": job["processed"],
        "total": job["total"],
        "progress": job["progress"],
        "errors": job["errors"],
        "error": job.get("error"),
    })


@router.get("/{job_id}/pdf")
async def get_job_pdf(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="job not finished")

    buffer = await asyncio.to_thread(build_pdf, job)
    headers = {"Content-Disposition": f'attachment; filename="report_{job_id}.pdf"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    with JOBS_LOCK:
        cancel_event = CANCEL_EVENTS.pop(job_id, None)
        if cancel_event is not None:
            cancel_event.set()
        existed = JOBS.pop(job_id, None) is not None
    if not existed:
        raise HTTPException(status_code=404, detail="job not found")
    return {"deleted": job_id}
