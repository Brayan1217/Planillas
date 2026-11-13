from __future__ import annotations

import csv
import io
import os
import secrets
import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .rules import cargar_reglas

API_KEY = os.getenv("PLATAFORMA_API_KEY", "demo-key")
EXT_OK = {".csv", ".txt", ".xlsx", ".xlsm"}
MAX_MB_POR_ARCHIVO = int(os.getenv("MAX_MB_ARCHIVO", "200"))
REGLAS = cargar_reglas()
STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Plataforma de Planillas CSS (prototipo)")


def auth(x_api_key: str = Header("")):
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, "API key invalida")


def _job(job_id: str) -> jobs.Job:
    j = jobs.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Planilla no encontrada")
    return j


@app.post("/api/planillas", dependencies=[Depends(auth)], status_code=202)
async def subir(ruc: str = Form(...), razon_social: str = Form(...), periodo: date = Form(...),
                archivos: list[UploadFile] = File(...)):
    """Recibe uno o varios archivos que se tratan como UNA sola planilla."""
    destino = Path(tempfile.mkdtemp(prefix="planilla_"))
    rutas: list[Path] = []
    for i, up in enumerate(archivos):
        ext = Path(up.filename or "").suffix.lower()
        if ext not in EXT_OK:
            shutil.rmtree(destino, ignore_errors=True)
            raise HTTPException(415, f"Formato no permitido: {up.filename}")
        p = destino / f"{i:03d}_{Path(up.filename).name}"  # nunca confiar en la ruta del cliente
        tam = 0
        with p.open("wb") as f:
            while chunk := await up.read(1 << 20):
                tam += len(chunk)
                if tam > MAX_MB_POR_ARCHIVO << 20:
                    shutil.rmtree(destino, ignore_errors=True)
                    raise HTTPException(413, f"{up.filename} supera {MAX_MB_POR_ARCHIVO} MB")
                f.write(chunk)
        rutas.append(p)
    j = jobs.crear_job({"ruc": ruc, "razon_social": razon_social}, periodo, rutas)
    jobs.en_segundo_plano(jobs.validar_job, j, REGLAS)
    return {"id": j.id}


@app.get("/api/planillas/{job_id}", dependencies=[Depends(auth)])
def estado(job_id: str):
    return _job(job_id).resumen()


@app.get("/api/planillas/{job_id}/hallazgos", dependencies=[Depends(auth)])
def hallazgos(job_id: str, offset: int = 0, limit: int = 100, codigo: str | None = None):
    j = _job(job_id)
    items = [h for h in j.hallazgos if not codigo or h.codigo == codigo]
    return {"total": len(items), "items": [h.dict() for h in items[offset:offset + min(limit, 500)]]}


@app.get("/api/planillas/{job_id}/hallazgos.csv", dependencies=[Depends(auth)])
def hallazgos_csv(job_id: str):
    j = _job(job_id)

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["codigo", "severidad", "archivo", "fila", "campo", "valor", "mensaje", "sugerencia"])
        yield buf.getvalue()
        for h in j.hallazgos:
            buf.seek(0); buf.truncate()
            w.writerow(h.dict().values())
            yield buf.getvalue()

    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="errores_{j.id}.csv"'})


@app.post("/api/planillas/{job_id}/enviar", dependencies=[Depends(auth)], status_code=202)
def enviar(job_id: str):
    j = _job(job_id)
    if j.estado != "lista":
        raise HTTPException(409, f"No se puede enviar: estado '{j.estado}'. Corrija los errores y vuelva a cargar.")
    jobs.en_segundo_plano(jobs.enviar_job, j, REGLAS)
    return {"id": j.id, "estado": "enviando"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
