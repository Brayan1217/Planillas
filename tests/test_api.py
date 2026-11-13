import csv
import time

import pytest
from fastapi.testclient import TestClient

from app import mock_css
from app.main import app
from app.security import firmar, verificar

H = {"X-API-Key": "demo-key"}
c = TestClient(app)
CAB = ["cedula", "nombres", "apellidos", "fecha_ingreso", "salario"]


def escribir(path, filas):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(CAB); w.writerows(filas)
    return path


def subir(rutas):
    files = [("archivos", (p.name, p.read_bytes(), "text/csv")) for p in rutas]
    r = c.post("/api/planillas", headers=H, files=files,
               data={"ruc": "155-1-1", "razon_social": "T", "periodo": "2026-10-31"})
    assert r.status_code == 202, r.text
    return r.json()["id"]


def esperar(jid, fin=("lista", "con_errores", "enviada", "fallida")):
    for _ in range(200):
        s = c.get(f"/api/planillas/{jid}", headers=H).json()
        if s["estado"] in fin:
            return s
        time.sleep(0.05)
    raise AssertionError("timeout")


def filas(n, desde=1):
    return [[f"8-100-{desde + i}", "Ana", "Perez", "2020-01-01", "1000"] for i in range(n)]


def test_requiere_api_key():
    assert c.get("/api/planillas/x").status_code == 401


def test_flujo_completo_multiarchivo_y_lotes(tmp_path):
    a = escribir(tmp_path / "p1.csv", filas(7000))
    b = escribir(tmp_path / "p2.csv", filas(3000, desde=7001))
    jid = subir([a, b])
    s = esperar(jid)
    assert s["estado"] == "lista" and s["total_filas"] == 10000 and s["errores"] == 0
    assert c.post(f"/api/planillas/{jid}/enviar", headers=H).status_code == 202
    s = esperar(jid, ("enviada", "fallida"))
    assert s["estado"] == "enviada", s
    assert s["envio"]["registros"] == 10000 and s["envio"]["lotes"] == 2  # 10000 / 5000
    assert s["envio"]["comprobante"].startswith("C-")


def test_errores_bloquean_envio_e_indican_donde(tmp_path):
    f = filas(5)
    f[2][0] = "XX"          # cedula mala en fila 4 (encabezado=1)
    f[4][0] = f[0][0]       # duplicada
    jid = subir([escribir(tmp_path / "x.csv", f)])
    s = esperar(jid)
    assert s["estado"] == "con_errores" and s["errores"] == 2
    items = c.get(f"/api/planillas/{jid}/hallazgos", headers=H).json()["items"]
    assert {(h["codigo"], h["fila"]) for h in items} == {("E101", 4), ("E102", 6)}
    assert c.post(f"/api/planillas/{jid}/enviar", headers=H).status_code == 409
    assert "E101" in c.get(f"/api/planillas/{jid}/hallazgos.csv", headers=H).text


def test_columnas_faltantes(tmp_path):
    p = tmp_path / "m.csv"; p.write_text("cedula,nombres\n8-1-1,Ana\n")
    s = esperar(subir([p]))
    assert s["estado"] == "con_errores" and "faltan columnas" in s["mensaje"]


def test_formato_no_permitido():
    r = c.post("/api/planillas", headers=H, files=[("archivos", ("a.exe", b"x", "application/x"))],
               data={"ruc": "1", "razon_social": "T", "periodo": "2026-10-31"})
    assert r.status_code == 415


def test_reintentos_ante_fallas_transitorias(tmp_path, monkeypatch):
    mock_css.RECIBOS.clear(); mock_css.ENVIOS.clear()
    monkeypatch.setattr(mock_css, "FAIL_RATE", 0.5)
    import random; random.seed(1)
    jid = subir([escribir(tmp_path / "g.csv", filas(20000))])
    esperar(jid)
    c.post(f"/api/planillas/{jid}/enviar", headers=H)
    s = esperar(jid, ("enviada", "fallida"))
    assert s["estado"] == "enviada" and s["envio"]["registros"] == 20000  # sin duplicados pese a reintentos


def test_firma_hmac():
    ts = str(time.time())
    f = firmar("k", ts, b"cuerpo")
    assert verificar("k", ts, b"cuerpo", f)
    assert not verificar("k", ts, b"alterado", f)
    assert not verificar("k", str(time.time() - 1000), b"cuerpo", firmar("k", str(time.time() - 1000), b"cuerpo"))


def test_css_rechaza_sin_firma():
    r = TestClient(mock_css.app).post("/v1/planillas/e/lotes/1", json={"registros": []},
                                      headers={"Authorization": "Bearer token-demo", "Idempotency-Key": "k"})
    assert r.status_code == 401
