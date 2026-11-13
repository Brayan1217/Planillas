"""Cliente de la API de la CSS: lotes firmados, idempotentes, con reintentos y conciliacion."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import AsyncIterator, Callable

import httpx

from .security import firmar


class ErrorEnvio(Exception):
    pass


def _cliente() -> httpx.AsyncClient:
    base = os.getenv("CSS_API_URL")
    if base:  # modo real: URL de la CSS
        return httpx.AsyncClient(base_url=base, timeout=30)
    from .mock_css import app as mock  # modo demo: simulador en proceso
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock), base_url="http://css-mock", timeout=30)


def _headers(cuerpo: bytes, idem: str | None = None) -> dict:
    secreto = os.getenv("CSS_SHARED_SECRET", "secreto-demo-cambiar")
    token = os.getenv("CSS_API_TOKEN", "token-demo")
    ts = str(time.time())
    h = {"Authorization": f"Bearer {token}", "X-Timestamp": ts,
         "X-Signature": firmar(secreto, ts, cuerpo), "Content-Type": "application/json"}
    if idem:
        h["Idempotency-Key"] = idem
    return h


async def _post(c: httpx.AsyncClient, url: str, payload: dict, idem: str | None, reintentos=5) -> dict:
    cuerpo = json.dumps(payload, separators=(",", ":"), default=str).encode()
    espera = 0.05
    for intento in range(1, reintentos + 1):
        try:
            r = await c.post(url, content=cuerpo, headers=_headers(cuerpo, idem))
            if r.status_code < 400:
                return r.json()
            if r.status_code < 500 and r.status_code != 429:
                raise ErrorEnvio(f"{r.status_code}: {r.json().get('detail', r.text)}")  # no reintentable
        except httpx.TransportError:
            pass
        if intento == reintentos:
            raise ErrorEnvio(f"Lote fallo tras {reintentos} intentos")
        await asyncio.sleep(espera)
        espera *= 2  # backoff exponencial
    raise ErrorEnvio("inalcanzable")


async def enviar_planilla(envio_id: str, empresa: dict, lotes: AsyncIterator[list[dict]],
                          progreso: Callable[[int, int], None]) -> dict:
    total_reg = total_lotes = 0
    async with _cliente() as c:
        n = 0
        async for lote in lotes:
            n += 1
            idem = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{envio_id}/{n}"))  # determinista => reintento seguro
            rec = await _post(c, f"/v1/planillas/{envio_id}/lotes/{n}",
                              {"empresa": empresa, "lote": n, "registros": lote}, idem)
            total_reg += rec["registros_aceptados"]
            total_lotes = n
            progreso(total_lotes, total_reg)
        return await _post(c, f"/v1/planillas/{envio_id}/cierre",
                           {"total_lotes": total_lotes, "total_registros": total_reg}, None)
