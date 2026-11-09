"""Acceso a datos de la API de Mascotas.

Hay dos implementaciones con la misma interfaz:
- SupabaseRepo: la real, usa PostgreSQL en Supabase.
- MemoriaRepo: guarda todo en memoria. Sirve para correr las pruebas
  sin conexión a internet (DB_MODE=memory).
"""
import os
import threading
from datetime import datetime, timezone
from typing import Optional

TABLA = "mascotas"


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseRepo:
    def __init__(self, url: str, key: str):
        from supabase import create_client

        self.client = create_client(url, key)

    def listar(self, estado: Optional[str] = None, especie: Optional[str] = None) -> list[dict]:
        q = self.client.table(TABLA).select("*")
        if estado:
            q = q.eq("estado", estado)
        if especie:
            q = q.eq("especie", especie)
        return q.order("id").execute().data

    def obtener(self, mascota_id: int) -> Optional[dict]:
        res = self.client.table(TABLA).select("*").eq("id", mascota_id).limit(1).execute()
        return res.data[0] if res.data else None

    def crear(self, datos: dict) -> dict:
        return self.client.table(TABLA).insert(datos).execute().data[0]

    def actualizar(self, mascota_id: int, datos: dict) -> Optional[dict]:
        datos = {**datos, "actualizado_en": ahora()}
        res = self.client.table(TABLA).update(datos).eq("id", mascota_id).execute()
        return res.data[0] if res.data else None

    def eliminar(self, mascota_id: int) -> bool:
        res = self.client.table(TABLA).delete().eq("id", mascota_id).execute()
        return bool(res.data)


class MemoriaRepo:
    def __init__(self):
        self._datos: dict[int, dict] = {}
        self._siguiente = 1
        self._lock = threading.Lock()
        semilla = [
            ("Luna", "perro", "Criolla", "hembra", 18, "Juguetona y buena con niños."),
            ("Michi", "gato", "Siamés", "macho", 8, "Tranquilo, le gusta dormir al sol."),
            ("Rocky", "perro", "Labrador mestizo", "macho", 36, "Necesita patio."),
        ]
        for nombre, especie, raza, sexo, edad, desc in semilla:
            self.crear({"nombre": nombre, "especie": especie, "raza": raza, "sexo": sexo,
                        "edad_meses": edad, "descripcion": desc})

    def listar(self, estado=None, especie=None):
        with self._lock:
            filas = list(self._datos.values())
        if estado:
            filas = [f for f in filas if f["estado"] == estado]
        if especie:
            filas = [f for f in filas if f["especie"] == especie]
        return [dict(f) for f in sorted(filas, key=lambda f: f["id"])]

    def obtener(self, mascota_id):
        with self._lock:
            fila = self._datos.get(mascota_id)
            return dict(fila) if fila else None

    def crear(self, datos):
        with self._lock:
            fila = {"raza": None, "sexo": None, "edad_meses": None, "descripcion": None,
                    "foto_url": None, "estado": "disponible", **datos,
                    "id": self._siguiente, "creado_en": ahora(), "actualizado_en": ahora()}
            self._datos[self._siguiente] = fila
            self._siguiente += 1
            return dict(fila)

    def actualizar(self, mascota_id, datos):
        with self._lock:
            fila = self._datos.get(mascota_id)
            if not fila:
                return None
            fila.update(datos)
            fila["actualizado_en"] = ahora()
            return dict(fila)

    def eliminar(self, mascota_id):
        with self._lock:
            return self._datos.pop(mascota_id, None) is not None


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
