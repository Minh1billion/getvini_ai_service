import logging

from fastapi import FastAPI

from app.feats.qc.router import router as qc_router
from app.feats.spell_check.router import router as spell_check_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="AI Service")

app.include_router(spell_check_router)
app.include_router(qc_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
@app.head("/")
async def root():
    return {"status": "ok"}