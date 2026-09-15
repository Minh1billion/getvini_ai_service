from fastapi import FastAPI

from app.feats.qc.router import router as qc_router
from app.feats.spell_check.router import router as spell_check_router

app = FastAPI(title="AI Service")

app.include_router(spell_check_router)
app.include_router(qc_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.head()
async def health():
    return {"status": "ok"}