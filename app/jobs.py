"""Ciclo de vida de una planilla: validar (streaming) -> corregir -> enviar por lotes."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from .gateway import ErrorEnvio, enviar_planilla
from .parser import ErrorArchivo, leer_planilla
from .rules import Reglas
from .validators import ValidadorPlanilla, Hallazgo, CATALOGO

MAX_HALLAZGOS_GUARDADOS = 200_000
AUDIT = Path("data/audit.jsonl")


def auditar(evento: str, **datos) -> None:
    """Bitacora de auditoria append-only (sin datos personales)."""
    AUDIT.parent.mkdir(exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "evento": evento, **datos}) + "\n")


@dataclass
class Job:
    id: str
    empresa: dict
    periodo: date
    archivos: list[Path]
    estado: str = "en_cola"  # en_cola|validando|con_errores|lista|enviando|enviada|fallida
    total_filas: int = 0
    procesadas: int = 0
    errores: int = 0
    advertencias: int = 0
    por_codigo: Counter = field(default_factory=Counter)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    truncado: bool = False
    totales: dict = field(default_factory=dict)
    envio: dict = field(default_factory=dict)
    mensaje: str = ""
    inicio: float = field(default_factory=time.time)
    duracion_validacion: float = 0.0

    def resumen(self) -> dict:
        return {
            "id": self.id, "estado": self.estado, "empresa": self.empresa, "periodo": str(self.periodo),
            "archivos": [p.name for p in self.archivos], "total_filas": self.total_filas,
            "procesadas": self.procesadas, "errores": self.errores, "advertencias": self.advertencias,
            "por_codigo": [{"codigo": k, "descripcion": CATALOGO.get(k, k), "cantidad": v}
                           for k, v in sorted(self.por_codigo.items())],
            "hallazgos_truncados": self.truncado,
            "totales": {k: str(v) for k, v in self.totales.items()},
            "envio": self.envio, "mensaje": self.mensaje,
            "segundos_validacion": round(self.duracion_validacion, 2),
        }


JOBS: dict[str, Job] = {}


def crear_job(empresa: dict, periodo: date, archivos: list[Path]) -> Job:
    j = Job(id=uuid.uuid4().hex[:12], empresa=empresa, periodo=periodo, archivos=archivos)
    JOBS[j.id] = j
    auditar("planilla_recibida", job=j.id, ruc=empresa.get("ruc"), archivos=len(archivos))
    return j


def validar_job(j: Job, reglas: Reglas) -> None:
    t0 = time.time()
    j.estado = "validando"
    try:
        v = ValidadorPlanilla(reglas, j.periodo)
        for archivo, fila, reg in leer_planilla(j.archivos):
            j.total_filas += 1
            for h in v.validar(archivo, fila, reg):
                j.por_codigo[h.codigo] += 1
                if h.severidad == "error":
                    j.errores += 1
                else:
                    j.advertencias += 1
                if len(j.hallazgos) < MAX_HALLAZGOS_GUARDADOS:
                    j.hallazgos.append(h)
                else:
                    j.truncado = True
            j.procesadas = j.total_filas
        j.totales = {**v.totales, "empleados": j.total_filas}
        j.estado = "con_errores" if j.errores else "lista"
    except ErrorArchivo as e:
        j.estado, j.mensaje = "con_errores", str(e)
        j.errores += 1
        j.por_codigo["E001"] += 1
        j.hallazgos.append(Hallazgo("E001", "error", "-", 0, "-", "", str(e),
                                    "Use las columnas de la plantilla oficial."))
    except Exception as e:  # defensivo: nunca dejar el job colgado
        j.estado, j.mensaje = "fallida", f"Error interno: {type(e).__name__}"
    j.duracion_validacion = time.time() - t0
    auditar("planilla_validada", job=j.id, estado=j.estado, filas=j.total_filas, errores=j.errores)


async def _lotes(j: Job, tam: int) -> AsyncIterator[list[dict]]:
    lote: list[dict] = []
    for archivo, fila, reg in leer_planilla(j.archivos):
        lote.append({k: (str(v) if v is not None else "") for k, v in reg.items()})
        if len(lote) >= tam:
            yield lote
            lote = []
            await asyncio.sleep(0)
    if lote:
        yield lote


def enviar_job(j: Job, reglas: Reglas) -> None:
    j.estado, j.envio = "enviando", {"lotes": 0, "registros": 0}
    j.envio_id = f"{j.empresa.get('ruc', 'X')}-{j.periodo:%Y%m}-{j.id}"

    def prog(l, r):
        j.envio = {"lotes": l, "registros": r}

    try:
        res = asyncio.run(enviar_planilla(j.envio_id, j.empresa | {"periodo": str(j.periodo)},
                                          _lotes(j, reglas.tamano_lote), prog))
        j.envio |= res
        j.estado = "enviada"
    except ErrorEnvio as e:
        j.estado, j.mensaje = "fallida", str(e)
    auditar("planilla_enviada", job=j.id, estado=j.estado, lotes=j.envio.get("lotes"),
            registros=j.envio.get("registros"), comprobante=j.envio.get("comprobante"))


def en_segundo_plano(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()
