# Planillas CSS — prototipo

Plataforma para que empresas privadas suban su planilla (CSV/Excel, uno o varios archivos), reciban alertas precisas de errores y la envíen por API segura a la CSS (simulada). Ver `docs/ARQUITECTURA.md`.

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000      # abrir http://localhost:8000
python tools/generar_muestra.py 300000 planilla.csv --errores 0.01   # datos de prueba
pytest
```
Variables: `PLATAFORMA_API_KEY`, `CSS_API_URL` (si se omite usa el simulador), `CSS_API_TOKEN`, `CSS_SHARED_SECRET`, `MOCK_CSS_FAIL_RATE`, `MAX_MB_ARCHIVO`.

> Tarifas y reglas son de demostración; verificar contra la normativa vigente antes de producción.
