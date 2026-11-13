"""Motor de reglas versionado por fecha de vigencia (las tarifas cambian por ley)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "reglas_css.json"


@dataclass(frozen=True)
class Tarifas:
    desde: date
    cuota_empleado: Decimal
    cuota_patrono: Decimal
    se_empleado: Decimal
    se_patrono: Decimal


@dataclass(frozen=True)
class Reglas:
    vigencias: tuple[Tarifas, ...]
    salario_minimo: Decimal
    salario_maximo_alerta: Decimal
    tolerancia: Decimal
    tamano_lote: int

    def tarifas_para(self, periodo: date) -> Tarifas:
        vigentes = [t for t in self.vigencias if t.desde <= periodo]
        if not vigentes:
            raise ValueError(f"No hay tarifas CSS vigentes para {periodo}")
        return max(vigentes, key=lambda t: t.desde)


def cargar_reglas(path: Path = CONFIG_PATH) -> Reglas:
    raw = json.loads(path.read_text(encoding="utf-8"))
    vig = tuple(
        Tarifas(
            desde=date.fromisoformat(v["desde"]),
            cuota_empleado=Decimal(v["cuota_empleado"]),
            cuota_patrono=Decimal(v["cuota_patrono"]),
            se_empleado=Decimal(v["seguro_educativo_empleado"]),
            se_patrono=Decimal(v["seguro_educativo_patrono"]),
        )
        for v in raw["vigencias"]
    )
    return Reglas(
        vigencias=vig,
        salario_minimo=Decimal(raw["salario_minimo_referencia"]),
        salario_maximo_alerta=Decimal(raw["salario_maximo_alerta"]),
        tolerancia=Decimal(raw["tolerancia_centavos"]),
        tamano_lote=int(raw["tamano_lote"]),
    )
