"""SIMULADOR de la API de la CSS (no es la API real). Sirve para desarrollar y probar el flujo:
autenticacion, firma, idempotencia por lote, fallas transitorias y comprobante de cierre."""
from __future__ import annotations

import json
import os
import random
import uuid

from fastapi import FastAPI, Header, HTTPException, Request

from .security import verificar

SECRETO = os.getenv("CSS_SHARED_SECRET", "secreto-demo-cambiar")
TOKEN = os.getenv("CSS_API_TOKEN", "token-demo")

app = FastAPI(title="Simulador API CSS")
RECIBOS: dict[str, dict] = {}  # idempotency-key -> recibo
ENVIOS: dict[str, dict] = {}   # envio_id -> {lotes:{n:registros}}
FAIL_RATE = float(os.getenv("MOCK_CSS_FAIL_RATE", "0"))


async def _auth(request: Request, authorization: str, x_timestamp: str, x_signature: str) -> bytes:
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Token invalido")
    cuerpo = await request.body()
    if not verificar(SECRETO, x_timestamp or "", cuerpo, x_signature or ""):
        raise HTTPException(401, "Firma invalida o mensaje expirado")
    return cuerpo


@app.post("/v1/planillas/{envio_id}/lotes/{n}")
async def recibir_lote(envio_id: str, n: int, request: Request,
                       authorization: str = Header(""), x_timestamp: str = Header(""),
                       x_signature: str = Header(""), idempotency_key: str = Header("")):
    cuerpo = await _auth(request, authorization, x_timestamp, x_signature)
    if not idempotency_key:
        raise HTTPException(400, "Falta Idempotency-Key")
    if idempotency_key in RECIBOS:  # reintento: devolver el mismo recibo, sin duplicar
        return RECIBOS[idempotency_key]
    if FAIL_RATE and random.random() < FAIL_RATE:
        raise HTTPException(503, "Servicio temporalmente no disponible")
    datos = json.loads(cuerpo)
    recibo = {"recibo": f"R-{uuid.uuid4().hex[:10].upper()}", "lote": n,
              "registros_aceptados": len(datos["registros"])}
    RECIBOS[idempotency_key] = recibo
    ENVIOS.setdefault(envio_id, {"lotes": {}})["lotes"][n] = len(datos["registros"])
    return recibo


@app.post("/v1/planillas/{envio_id}/cierre")
async def cerrar(envio_id: str, request: Request, authorization: str = Header(""),
                 x_timestamp: str = Header(""), x_signature: str = Header("")):
    cuerpo = await _auth(request, authorization, x_timestamp, x_signature)
    datos = json.loads(cuerpo)
    envio = ENVIOS.get(envio_id, {"lotes": {}})
    recibidos = sum(envio["lotes"].values())
    if len(envio["lotes"]) != datos["total_lotes"] or recibidos != datos["total_registros"]:
        raise HTTPException(409, f"Conciliacion fallida: esperados {datos['total_registros']} "
                                 f"registros/{datos['total_lotes']} lotes, recibidos {recibidos}/{len(envio['lotes'])}")
    return {"comprobante": f"C-{uuid.uuid4().hex[:12].upper()}", "registros": recibidos, "estado": "ACEPTADA"}
