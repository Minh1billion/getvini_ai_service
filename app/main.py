from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.document_router import router as document_router
from app.api.qc_router import router as qc_router
from app.api.spellcheck_router import router as spellcheck_router
from app.core.logging import setup_logging
from app.domain.spellcheck.service import register_dictionaries
from app.infra.jobs.qc_queue import start_workers

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    register_dictionaries()
    start_workers()
    yield


app = FastAPI(title="AI Service", lifespan=lifespan)

app.include_router(spellcheck_router)
app.include_router(qc_router)
app.include_router(document_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
@app.head("/")
async def root():
    return {"status": "ok"}
