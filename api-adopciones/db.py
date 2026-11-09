"""Acceso a datos de la API de Adopciones.

Igual que en la API de Mascotas, hay una implementación real (Supabase)
y una en memoria para pruebas (DB_MODE=memory). La versión en memoria
imita los índices únicos de la base de datos.
"""
import os
import threading
from datetime import datetime, timezone
from typing import Optional

TABLA = "solicitudes"


class ConflictoUnico(Exception):
    """Se violó un índice único (código 23505 en PostgreSQL)."""


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseRepo:
    def __init__(self, url: str, key: str):
        from supabase import create_client

        self.client = create_client(url, key)

    @staticmethod
    def _ejecutar(consulta):
        from postgrest.exceptions import APIError

        try:
            return consulta.execute()
        except APIError as e:
            if str(getattr(e, "code", "")) == "23505":
                raise ConflictoUnico(str(e)) from e
            raise

    def listar(self, estado: Optional[str] = None, mascota_id: Optional[int] = None) -> list[dict]:
        q = self.client.table(TABLA).select("*")
        if estado:
            q = q.eq("estado", estado)
        if mascota_id is not None:
            q = q.eq("mascota_id", mascota_id)
        return self._ejecutar(q.order("id", desc=True)).data

    def obtener(self, solicitud_id: int) -> Optional[dict]:
        res = self._ejecutar(self.client.table(TABLA).select("*").eq("id", solicitud_id).limit(1))
        return res.data[0] if res.data else None

    def crear(self, datos: dict) -> dict:
        return self._ejecutar(self.client.table(TABLA).insert(datos)).data[0]

    def actualizar(self, solicitud_id: int, datos: dict) -> Optional[dict]:
        datos = {**datos, "actualizado_en": ahora()}
        res = self._ejecutar(self.client.table(TABLA).update(datos).eq("id", solicitud_id))
        return res.data[0] if res.data else None

    def eliminar(self, solicitud_id: int) -> None:
        self._ejecutar(self.client.table(TABLA).delete().eq("id", solicitud_id))


class MemoriaRepo:
    def __init__(self):
        self._datos: dict[int, dict] = {}
        self._siguiente = 1
        self._lock = threading.Lock()

    def _validar_unicos(self, fila: dict, ignorar_id: Optional[int] = None) -> None:
        for otra in self._datos.values():
            if otra["id"] == ignorar_id or otra["mascota_id"] != fila["mascota_id"]:
                continue
            if fila["estado"] == "aprobada" and otra["estado"] == "aprobada":
                raise ConflictoUnico("una_aprobada_por_mascota")
            if (fila["estado"] == "pendiente" and otra["estado"] == "pendiente"
                    and otra["documento"] == fila["documento"]):
                raise ConflictoUnico("una_pendiente_por_persona")

    def listar(self, estado=None, mascota_id=None):
        with self._lock:
            filas = list(self._datos.values())
        if estado:
            filas = [f for f in filas if f["estado"] == estado]
        if mascota_id is not None:
            filas = [f for f in filas if f["mascota_id"] == mascota_id]
        return [dict(f) for f in sorted(filas, key=lambda f: f["id"], reverse=True)]

    def obtener(self, solicitud_id):
        with self._lock:
            fila = self._datos.get(solicitud_id)
            return dict(fila) if fila else None

    def crear(self, datos):
        with self._lock:
            fila = {"ciudad": None, "observacion": None, "estado": "pendiente", **datos,
                    "id": self._siguiente, "creado_en": ahora(), "actualizado_en": ahora()}
            self._validar_unicos(fila)
            self._datos[self._siguiente] = fila
            self._siguiente += 1
            return dict(fila)

    def actualizar(self, solicitud_id, datos):
        with self._lock:
            fila = self._datos.get(solicitud_id)
            if not fila:
                return None
            propuesta = {**fila, **datos}
            self._validar_unicos(propuesta, ignorar_id=solicitud_id)
            fila.update(datos)
            fila["actualizado_en"] = ahora()
            return dict(fila)

    def eliminar(self, solicitud_id):
        with self._lock:
            self._datos.pop(solicitud_id, None)


def crear_repo():
    if os.getenv("DB_MODE", "").lower() == "memory":
        return MemoriaRepo()
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL y SUPABASE_KEY. Configúralas en .env "
            "o usa DB_MODE=memory para pruebas locales."
        )
    return SupabaseRepo(url, key)
