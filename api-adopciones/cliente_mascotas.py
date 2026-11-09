"""Cliente HTTP hacia la API de Mascotas.

Toda la comunicación entre servicios pasa por aquí: HTTP/REST con JSON.
La API de Adopciones nunca lee la tabla `mascotas` directamente.
"""
import os
from typing import Optional

import httpx
from fastapi import HTTPException, status

MASCOTAS_API_URL = os.getenv("MASCOTAS_API_URL", "http://localhost:8001").rstrip("/")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
# Render (plan gratis) apaga el servicio tras 15 min sin uso y tarda ~50 s en despertar.
TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "60"))


class ErrorServicioMascotas(Exception):
    """La API de Mascotas no respondió o respondió con un error inesperado."""


def _cabeceras() -> dict:
    cab = {"Accept": "application/json"}
    if SERVICE_API_KEY:
        cab["X-Service-Key"] = SERVICE_API_KEY
    return cab


def _peticion(metodo: str, ruta: str, **kwargs) -> httpx.Response:
    try:
        with httpx.Client(timeout=TIMEOUT, headers=_cabeceras()) as cliente:
            return cliente.request(metodo, f"{MASCOTAS_API_URL}{ruta}", **kwargs)
    except httpx.HTTPError as e:
        raise ErrorServicioMascotas(f"No se pudo contactar la API de Mascotas: {e}") from e


def obtener_mascota(mascota_id: int) -> Optional[dict]:
    """GET /mascotas/{id}. Devuelve None si la mascota no existe."""
    r = _peticion("GET", f"/mascotas/{mascota_id}")
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise ErrorServicioMascotas(f"La API de Mascotas respondió {r.status_code}: {r.text}")
    return r.json()


def cambiar_estado(mascota_id: int, estado: str, motivo: str = "") -> dict:
    """PATCH /mascotas/{id}/estado."""
    r = _peticion("PATCH", f"/mascotas/{mascota_id}/estado",
                  json={"estado": estado, "motivo": motivo or None})
    if r.status_code == 200:
        return r.json()
    if r.status_code in (404, 409):
        # Errores de negocio: se devuelven tal cual al cliente
        detalle = r.json().get("detail", r.text)
        raise HTTPException(r.status_code, f"API de Mascotas: {detalle}")
    raise ErrorServicioMascotas(f"La API de Mascotas respondió {r.status_code}: {r.text}")


def salud() -> dict:
    try:
        r = _peticion("GET", "/")
        return {"url": MASCOTAS_API_URL, "estado": "ok" if r.status_code == 200 else f"http {r.status_code}"}
    except ErrorServicioMascotas as e:
        return {"url": MASCOTAS_API_URL, "estado": "caida", "error": str(e)}


def servicio_no_disponible(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
