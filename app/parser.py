"""Lectura en streaming de planillas CSV/XLSX. Une N archivos en un solo flujo de filas,
de modo que una empresa grande ya no tiene que dividir su planilla manualmente."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path
from typing import Iterator

COLUMNAS_REQUERIDAS = ["cedula", "nombres", "apellidos", "fecha_ingreso", "salario"]
COLUMNAS_OPCIONALES = ["nss", "descuento_css", "descuento_se"]

ALIAS = {
    "cedula": {"cedula", "cedula_identidad", "id", "documento", "no_cedula"},
    "nss": {"nss", "seguro_social", "no_seguro_social", "num_seguro_social"},
    "nombres": {"nombres", "nombre", "primer_nombre"},
    "apellidos": {"apellidos", "apellido"},
    "fecha_ingreso": {"fecha_ingreso", "ingreso", "fecha_de_ingreso"},
    "salario": {"salario", "salario_mensual", "salario_bruto", "sueldo"},
    "descuento_css": {"descuento_css", "css_empleado", "cuota_css", "descuento_ss"},
    "descuento_se": {"descuento_se", "seguro_educativo", "se_empleado", "descuento_educativo"},
}
_REVERSO = {a: canon for canon, als in ALIAS.items() for a in als}


class ErrorArchivo(Exception):
    """Archivo ilegible o sin las columnas requeridas."""


def normalizar_encabezado(h: object) -> str:
    s = unicodedata.normalize("NFKD", str(h or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")
    return _REVERSO.get(s, s)


def _mapear(encabezados: list[object], archivo: str) -> list[str]:
    cols = [normalizar_encabezado(h) for h in encabezados]
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in cols]
    if faltan:
        raise ErrorArchivo(f"{archivo}: faltan columnas requeridas: {', '.join(faltan)}")
    return cols


def _leer_texto(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ErrorArchivo(f"{path.name}: codificacion no soportada")


def _filas_csv(path: Path) -> Iterator[tuple[int, dict]]:
    texto = _leer_texto(path)
    try:
        dialect = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rd = csv.reader(io.StringIO(texto), dialect)
    try:
        cols = _mapear(next(rd), path.name)
    except StopIteration:
        raise ErrorArchivo(f"{path.name}: archivo vacio")
    for n, fila in enumerate(rd, start=2):
        if not any((c or "").strip() for c in fila):
            continue
        yield n, dict(zip(cols, fila))


def _filas_xlsx(path: Path) -> Iterator[tuple[int, dict]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            try:
                cols = _mapear(list(next(it)), f"{path.name}[{ws.title}]")
            except StopIteration:
                continue
            for n, fila in enumerate(it, start=2):
                if fila is None or not any(c not in (None, "") for c in fila):
                    continue
                yield n, dict(zip(cols, fila))
    finally:
        wb.close()


def leer_archivo(path: Path) -> Iterator[tuple[int, dict]]:
    ext = path.suffix.lower()
    if ext in (".csv", ".txt"):
        return _filas_csv(path)
    if ext in (".xlsx", ".xlsm"):
        return _filas_xlsx(path)
    raise ErrorArchivo(f"{path.name}: formato no soportado (use .csv o .xlsx)")


def leer_planilla(paths: list[Path]) -> Iterator[tuple[str, int, dict]]:
    """Itera (archivo, fila, registro) sobre todos los archivos como una sola planilla."""
    for p in paths:
        nombre = re.sub(r"^\d{3}_", "", p.name)  # prefijo interno de orden de carga
        for n, reg in leer_archivo(p):
            yield nombre, n, reg
