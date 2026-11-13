from datetime import date
from decimal import Decimal

import pytest

from app.rules import cargar_reglas
from app.validators import ValidadorPlanilla, calcular_descuentos

R = cargar_reglas()
P = date(2026, 10, 31)


def reg(**kw):
    base = dict(cedula="8-123-4567", nss="123456", nombres="Ana", apellidos="Perez",
                fecha_ingreso="2020-01-15", salario="1000.00")
    return base | kw


def codigos(r, v=None):
    v = v or ValidadorPlanilla(R, P)
    return [h.codigo for h in v.validar("a.csv", 2, r)]


def test_registro_valido():
    assert codigos(reg()) == []


@pytest.mark.parametrize("ced", ["8-123-4567", "4-AV-12-345", "PE-12-345", "E-8-12345", "N-12-345", "13-1-1"])
def test_cedulas_validas(ced):
    assert "E101" not in codigos(reg(cedula=ced))


@pytest.mark.parametrize("ced", ["", "8-ABC", "99-1-1", "abc", "8--1"])
def test_cedulas_invalidas(ced):
    assert "E101" in codigos(reg(cedula=ced))


def test_duplicado_indica_donde():
    v = ValidadorPlanilla(R, P)
    v.validar("a.csv", 2, reg())
    h = v.validar("b.csv", 9, reg())[0]
    assert h.codigo == "E102" and "a.csv fila 2" in h.mensaje


def test_descuento_css_incorrecto_sugiere_valor():
    h = [x for x in ValidadorPlanilla(R, P).validar("a", 2, reg(descuento_css="100.00")) if x.codigo == "E107"][0]
    assert "97.50" in h.sugerencia


def test_descuento_correcto_no_error():
    assert codigos(reg(descuento_css="97.50", descuento_se="12.50")) == []


def test_salarios_con_formato_regional():
    assert codigos(reg(salario="1,250.00")) == []
    assert codigos(reg(salario="1250,50")) == []
    assert "E106" in codigos(reg(salario="mil"))
    assert "E106" in codigos(reg(salario="-5"))
    assert "E106" in codigos(reg(salario="NaN"))


def test_fecha_futura_y_formato():
    assert "E105" in codigos(reg(fecha_ingreso="2027-01-01"))
    assert "E105" in codigos(reg(fecha_ingreso="31/02/2020"))
    assert codigos(reg(fecha_ingreso="15/01/2020")) == []


def test_advertencias_no_son_errores():
    hs = ValidadorPlanilla(R, P).validar("a", 2, reg(salario="100"))
    assert [h.severidad for h in hs] == ["advertencia"]


def test_calculo_decimal_exacto():
    d = calcular_descuentos(Decimal("1000"), R.tarifas_para(P))
    assert d["css_empleado"] == Decimal("97.50") and d["css_patrono"] == Decimal("122.50")
