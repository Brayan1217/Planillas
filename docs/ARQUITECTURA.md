# Plataforma de Planillas CSS — arquitectura y respuesta al caso

**Pregunta:** ¿Cómo reducirías errores en planillas mediante calidad, seguridad y DevOps continuo?

## 1. Causa raíz de los errores (hipótesis a validar con la CSS y clientes)
| Problema actual | Respuesta del prototipo |
|---|---|
| El error se descubre *después* de enviar | Validación previa con fila/campo/causa/cómo corregir (E101…E108) |
| Planillas grandes se parten en varios Excel | N archivos = 1 planilla; lectura en streaming; 300 000 registros validados en ~12 s |
| Cálculos manuales de cuotas | Motor de reglas versionado por vigencia (tarifas en `config/reglas_css.json`) |
| Cambios de ley (p. ej. Ley 462 de 2025) rompen todo | Nueva vigencia = nueva entrada de configuración, sin redespliegue de código |
| Reenvíos y duplicados | Lotes idempotentes + conciliación de cierre (lotes y registros) |

## 2. Flujo
`Cargar (1..N archivos) → Validar (streaming) → Corregir → Enviar en lotes de 5 000 firmados → Cierre conciliado → Comprobante`
El envío está **bloqueado** mientras existan errores; las advertencias no bloquean.

## 3. Calidad
- Reglas como funciones puras + catálogo de códigos; pruebas unitarias parametrizadas (`tests/`).
- Pruebas de extremo a extremo: multi-archivo, lotes, fallas transitorias sin duplicados.
- Dinero con `Decimal` (nunca `float`) y redondeo explícito.
- Próximo: pruebas de contrato contra el sandbox real de la CSS, *property-based testing* (Hypothesis), carga con k6.

## 4. Seguridad
- API de la CSS: Bearer + firma HMAC-SHA256 con marca de tiempo (anti-replay) + `Idempotency-Key` (`app/security.py`, `app/gateway.py`).
- Subidas: lista blanca de extensiones, tope de tamaño, nombres saneados, lectura por bloques.
- Auditoría append-only sin datos personales; cédulas enmascaradas en logs (`enmascarar_cedula`).
- **Pendiente para producción:** OAuth2/OIDC + MFA y roles por empresa, mTLS a la CSS, cifrado en reposo, secretos en un gestor (Vault/KMS), antivirus de archivos, retención/borrado según la Ley 81 de 2019 (protección de datos), rate limiting, WAF.

## 5. DevOps continuo
- CI (`.github/workflows/ci.yml`): lint, SAST (bandit), auditoría de dependencias, pruebas con umbral de cobertura, build de imagen.
- CD sugerido: imagen inmutable → *staging* contra sandbox CSS → *canary* → producción; reglas de tarifas versionadas y con revisión de dos personas.
- Observabilidad: métricas (tasa de error por código, latencia por lote, reintentos), alertas, trazas por `envio_id`.
- Cola de trabajos (Celery/RQ/SQS) + almacenamiento de objetos para escalar horizontalmente; el prototipo usa hilos y memoria.

## 6. Límites del prototipo (honestidad)
- La API de la CSS es un **simulador**; el formato real, autenticación y reglas deben tomarse de la documentación oficial/convenio con la CSS.
- Tarifas y formatos de cédula/NSS son **valores de demostración**: verificar contra Ley 51 de 2005 y reformas (incl. Ley 462 de 2025).
- Estado en memoria (se pierde al reiniciar); sin login real (API key fija de demo).
- No cubre riesgos profesionales, décimo tercer mes, incapacidades, ni el resto de campos reales de la planilla CSS.

## 7. Cómo superar a e-Tax 2.0 / Payday (diferenciadores propuestos)
1. Planilla completa sin dividir; 2. errores accionables con sugerencia de corrección; 3. API pública para integrar ERP/nómina (SAP, Odoo, QuickBooks); 4. historial y comparación mes contra mes (altas/bajas/variaciones anómalas); 5. conciliación y comprobante verificable.
