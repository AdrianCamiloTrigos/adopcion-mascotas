# Pruebas de integración

Las pruebas viven en `tests/test_integracion.py` y usan `pytest` con `httpx`. Cada una llama a las APIs por HTTP, sin importar su código, así que prueban la integración real entre servicios. Se ejecutaron primero en local y después contra el despliegue en Render.

## Casos

| # | Prueba | Qué verifica | Servicios involucrados |
|---|---|---|---|
| 01 | Ambos servicios responden | Adopciones logra hablar con Mascotas (`/salud`) | 1 y 2 |
| 02 | Swagger publicado | `/docs` y `/openapi.json` responden en las dos APIs | 1 y 2 |
| 03 | Solicitud cambia mascota a `en_proceso` | Al registrar la primera solicitud, la API 2 actualiza el estado en la API 1 | 1 y 2 |
| 04 | Mascota inexistente | La API 2 consulta a la API 1, recibe 404 y no guarda nada | 1 y 2 |
| 05 | Sin duplicados por persona | El mismo documento no puede tener dos pendientes para la misma mascota (409) | 2 y BD |
| 06 | Proceso completo | Dos solicitudes, se aprueba una, la mascota queda `adoptada`, la otra se rechaza sola y el detalle trae la mascota desde la API 1 | 1 y 2 |
| 07 | Mascota adoptada no recibe solicitudes | Responde 409 | 1 y 2 |
| 08 | No se aprueba dos veces | La segunda aprobación de la misma solicitud da 409 | 2 |
| 09 | Aprobaciones simultáneas | Dos aprobaciones en paralelo para la misma mascota: una 200 y otra 409, y solo queda una aprobada | 1, 2 y BD |
| 10 | Rechazo libera la mascota | Con dos pendientes, rechazar una la deja `en_proceso`; rechazar la última la deja `disponible` | 1 y 2 |
| 11 | `adoptada` es final | La API 1 no deja devolver una mascota adoptada a `disponible` | 1 |
| 12 | Clave de servicio | Sin `X-Service-Key` no se puede cambiar el estado de una mascota (401) | 1 |
| 13 | No se borra con proceso en curso | Una mascota `en_proceso` no se puede eliminar (409) | 1 y 2 |

## Prueba manual de falla de un servicio

Con las dos APIs corriendo se registró una solicitud y luego se apagó la API de Mascotas. Al intentar aprobar:

```
PATCH /solicitudes/18/aprobar  →  503
{"detail": "No se pudo contactar la API de Mascotas: [Errno 111] Connection refused"}

GET /solicitudes/18  →  estado: pendiente, mascota: null
GET /salud           →  api_mascotas.estado: "caida"
```

La solicitud quedó pendiente y no hubo ningún cambio a medias.

## Resultados

- `evidencias/pytest_local.txt`: 13 de 13 pruebas pasaron contra las APIs locales.
- `evidencias/demo_flujo_local.txt`: recorrido completo con cada petición y respuesta.
- `evidencias/pytest_nube.txt`: *(agregar después de correr contra Render)*.
- Capturas del frontend: `01_catalogo_mascotas.png` a `05_estado_del_sistema.png`.

Para generar la evidencia contra la nube:

```bash
MASCOTAS_URL=https://huellas-api-mascotas.onrender.com \
ADOPCIONES_URL=https://huellas-api-adopciones.onrender.com \
SERVICE_API_KEY=la-clave-de-render \
pytest -v tests/ > docs/evidencias/pytest_nube.txt
```
