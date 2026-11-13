"""Validaciones por registro. Cada hallazgo indica DONDE esta el error (archivo/fila/campo),
QUE esta mal y COMO corregirlo."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .rules import Reglas, Tarifas

# Formatos de cedula panamena: 8-123-4567, 4-AV-12-345, PE-12-345, E-8-12345, N-12-345
CEDULA_RE = re.compile(r"^(?:(?:[1-9]|1[0-3])(?:-(?:AV|PI))?|PE|E|N)-\d{1,4}(?:-\d{1,6})?$")
NSS_RE = re.compile(r"^\d{4,10}$")
CENT = Decimal("0.01")

CATALOGO = {
    "E101": "Cedula vacia o con formato invalido",
    "E102": "Cedula duplicada en la planilla",
    "E103": "Numero de seguro social invalido",
    "E104": "Nombre o apellido vacio",
    "E105": "Fecha de ingreso invalida",
    "E106": "Salario invalido",
    "E107": "Descuento CSS no coincide con el calculo",
    "E108": "Descuento de seguro educativo no coincide",
    "E001": "Archivo ilegible o sin columnas requeridas",
    "W201": "Salario inferior al minimo de referencia",
    "W202": "Salario atipicamente alto",
}


@dataclass
class Hallazgo:
    codigo: str
    severidad: str  # "error" bloquea el envio; "advertencia" no
    archivo: str
    fila: int
    campo: str
    valor: str
    mensaje: str
    sugerencia: str

    def dict(self) -> dict:
        return asdict(self)


def _dinero(v: object) -> Decimal:
    if isinstance(v, str):
        v = v.replace("$", "").replace("B/.", "").replace(" ", "")
        if v.count(",") == 1 and v.count(".") == 0:
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")
    d = Decimal(str(v))
    if not d.is_finite():
        raise InvalidOperation
    return d


def _fecha(v: object) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(s)


def normalizar_cedula(v: object) -> str:
    return re.sub(r"\s+", "", str(v or "")).upper()


def calcular_descuentos(salario: Decimal, t: Tarifas) -> dict[str, Decimal]:
    q = lambda x: x.quantize(CENT, ROUND_HALF_UP)
    return {
        "css_empleado": q(salario * t.cuota_empleado),
        "css_patrono": q(salario * t.cuota_patrono),
        "se_empleado": q(salario * t.se_empleado),
        "se_patrono": q(salario * t.se_patrono),
    }


class ValidadorPlanilla:
    """Mantiene estado entre filas (duplicados) y totales de control."""

    def __init__(self, reglas: Reglas, periodo: date):
        self.reglas = reglas
        self.periodo = periodo
        self.tarifas = reglas.tarifas_para(periodo)
        self.cedulas: dict[str, tuple[str, int]] = {}
        self.totales = {k: Decimal("0") for k in
                        ("salarios", "css_empleado", "css_patrono", "se_empleado", "se_patrono")}

    def validar(self, archivo: str, fila: int, reg: dict) -> list[Hallazgo]:
        out: list[Hallazgo] = []

        def err(cod, campo, valor, msg, sug, sev="error"):
            out.append(Hallazgo(cod, sev, archivo, fila, campo, str(valor)[:60], msg, sug))

        ced = normalizar_cedula(reg.get("cedula"))
        if not ced or not CEDULA_RE.match(ced):
            err("E101", "cedula", ced, CATALOGO["E101"], "Use el formato 8-123-4567 (provincia-tomo-asiento).")
        elif ced in self.cedulas:
            a, f = self.cedulas[ced]
            err("E102", "cedula", ced, f"{CATALOGO['E102']} (ya aparece en {a} fila {f})",
                "Elimine el registro repetido o corrija la cedula.")
        else:
            self.cedulas[ced] = (archivo, fila)

        nss = str(reg.get("nss") or "").strip()
        if nss and not NSS_RE.match(nss):
            err("E103", "nss", nss, CATALOGO["E103"], "Debe contener solo digitos (4 a 10).")

        for campo in ("nombres", "apellidos"):
            if not str(reg.get(campo) or "").strip():
                err("E104", campo, "", f"{CATALOGO['E104']} ({campo})", "Complete el campo.")

        try:
            fi = _fecha(reg.get("fecha_ingreso"))
            if fi > self.periodo:
                err("E105", "fecha_ingreso", fi, "La fecha de ingreso es posterior al periodo declarado",
                    f"Debe ser anterior o igual a {self.periodo}.")
            elif fi.year < 1950:
                err("E105", "fecha_ingreso", fi, "Fecha de ingreso demasiado antigua", "Verifique el ano.")
        except (ValueError, TypeError):
            err("E105", "fecha_ingreso", reg.get("fecha_ingreso") or "", CATALOGO["E105"],
                "Use AAAA-MM-DD o DD/MM/AAAA.")

        try:
            sal = _dinero(reg.get("salario"))
        except (InvalidOperation, ValueError, TypeError):
            err("E106", "salario", reg.get("salario") or "", "El salario no es un numero", "Use un valor como 1250.00.")
            return out
        if sal <= 0:
            err("E106", "salario", sal, "El salario debe ser mayor que cero", "Corrija el monto.")
            return out
        if sal < self.reglas.salario_minimo:
            err("W201", "salario", sal, f"{CATALOGO['W201']} ({self.reglas.salario_minimo})",
                "Verifique si es jornada parcial o un error de digitacion.", "advertencia")
        if sal > self.reglas.salario_maximo_alerta:
            err("W202", "salario", sal, CATALOGO["W202"], "Confirme el monto.", "advertencia")

        calc = calcular_descuentos(sal, self.tarifas)
        for campo, clave, cod, nom in (("descuento_css", "css_empleado", "E107", "CSS"),
                                       ("descuento_se", "se_empleado", "E108", "seguro educativo")):
            dado = reg.get(campo)
            if dado in (None, ""):
                continue
            try:
                d = _dinero(dado)
            except (InvalidOperation, ValueError, TypeError):
                err(cod, campo, dado, f"El descuento de {nom} no es numerico", f"Esperado: {calc[clave]}")
                continue
            if abs(d - calc[clave]) > self.reglas.tolerancia:
                err(cod, campo, d, f"{CATALOGO[cod]}: declarado {d}, calculado {calc[clave]}",
                    f"Corrija a {calc[clave]} (salario {sal} x tarifa vigente).")

        self.totales["salarios"] += sal
        for k, v in calc.items():
            self.totales[k] += v
        return out
