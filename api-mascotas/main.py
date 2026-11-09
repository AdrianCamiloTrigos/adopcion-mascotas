"""API 1 - Mascotas

Administra el registro, la consulta y la disponibilidad de los animales.
Es la única dueña de la tabla `mascotas`.
"""
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

from db import crear_repo  # noqa: E402

Especie = Literal["perro", "gato", "otro"]
Sexo = Literal["macho", "hembra"]
Estado = Literal["disponible", "en_proceso", "adoptada"]

# Transiciones de estado permitidas.
# "adoptada" es final: una mascota adoptada no vuelve a quedar disponible.
TRANSICIONES: dict[str, set[str]] = {
    "disponible": {"en_proceso", "adoptada"},
    "en_proceso": {"disponible", "adoptada"},
    "adoptada": set(),
}

SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
ORIGENES = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(
    title="API de Mascotas",
    version="1.0.0",
    description=(
        "Servicio de la Fundación Huellas de Esperanza que administra las mascotas "
        "disponibles para adopción.\n\n"
        "**Estados de una mascota:** `disponible` → `en_proceso` (tiene solicitudes "
        "pendientes) → `adoptada` (estado final).\n\n"
        "El cambio de estado (`PATCH /mascotas/{id}/estado`) lo hace la API de Adopciones "
        "y está protegido con la cabecera `X-Service-Key`."
    ),
    openapi_tags=[
        {"name": "Mascotas", "description": "Registro y consulta de animales."},
        {"name": "Integración", "description": "Operaciones que consume la API de Adopciones."},
        {"name": "Salud", "description": "Estado del servicio."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = crear_repo()


# ----------------------------------------------------------------------
# Esquemas
# ----------------------------------------------------------------------
class MascotaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60, examples=["Luna"])
    especie: Especie = Field(..., examples=["perro"])
    raza: Optional[str] = Field(None, max_length=60, examples=["Criolla"])
    sexo: Optional[Sexo] = Field(None, examples=["hembra"])
    edad_meses: Optional[int] = Field(None, ge=0, le=400, examples=[18])
    descripcion: Optional[str] = Field(None, max_length=500, examples=["Juguetona y buena con niños."])
    foto_url: Optional[str] = Field(None, max_length=500, examples=[None])


class MascotaCrear(MascotaBase):
    pass


class MascotaActualizar(BaseModel):
    """Todos los campos son opcionales. El estado NO se cambia aquí."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=60)
    especie: Optional[Especie] = None
    raza: Optional[str] = Field(None, max_length=60)
    sexo: Optional[Sexo] = None
    edad_meses: Optional[int] = Field(None, ge=0, le=400)
    descripcion: Optional[str] = Field(None, max_length=500)
    foto_url: Optional[str] = Field(None, max_length=500)


class Mascota(MascotaBase):
    model_config = ConfigDict(extra="ignore")
    id: int
    estado: Estado
    creado_en: Optional[str] = None
    actualizado_en: Optional[str] = None


class CambioEstado(BaseModel):
    estado: Estado = Field(..., examples=["adoptada"])
    motivo: Optional[str] = Field(None, max_length=200, examples=["Solicitud #4 aprobada"])


class Disponibilidad(BaseModel):
    mascota_id: int
    estado: Estado
    disponible_para_solicitud: bool


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def obtener_o_404(mascota_id: int) -> dict:
    mascota = repo.obtener(mascota_id)
    if not mascota:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"La mascota {mascota_id} no existe")
    return mascota


def verificar_clave_servicio(clave: Optional[str]) -> None:
    if SERVICE_API_KEY and clave != SERVICE_API_KEY:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Clave de servicio inválida. Solo la API de Adopciones puede cambiar el estado.",
        )


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/", tags=["Salud"], summary="Estado del servicio")
def salud():
    return {"servicio": "api-mascotas", "estado": "ok", "docs": "/docs"}


@app.get("/mascotas", response_model=list[Mascota], tags=["Mascotas"], summary="Listar mascotas")
def listar_mascotas(
    estado: Optional[Estado] = Query(None, description="Filtrar por estado"),
    especie: Optional[Especie] = Query(None, description="Filtrar por especie"),
):
    return repo.listar(estado=estado, especie=especie)


@app.get("/mascotas/{mascota_id}", response_model=Mascota, tags=["Mascotas"],
         summary="Consultar una mascota", responses={404: {"description": "No existe"}})
def obtener_mascota(mascota_id: int):
    return obtener_o_404(mascota_id)


@app.post("/mascotas", response_model=Mascota, status_code=status.HTTP_201_CREATED,
          tags=["Mascotas"], summary="Registrar una mascota")
def crear_mascota(datos: MascotaCrear):
    return repo.crear(datos.model_dump())


@app.put("/mascotas/{mascota_id}", response_model=Mascota, tags=["Mascotas"],
         summary="Actualizar datos de una mascota")
def actualizar_mascota(mascota_id: int, datos: MascotaActualizar):
    obtener_o_404(mascota_id)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se envió ningún campo para actualizar")
    return repo.actualizar(mascota_id, cambios)


@app.delete("/mascotas/{mascota_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Mascotas"],
            summary="Eliminar una mascota",
            responses={409: {"description": "Tiene un proceso de adopción en curso o ya fue adoptada"}})
def eliminar_mascota(mascota_id: int):
    mascota = obtener_o_404(mascota_id)
    if mascota["estado"] != "disponible":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede eliminar: la mascota está '{mascota['estado']}'. "
            "Solo se eliminan mascotas disponibles sin proceso de adopción.",
        )
    repo.eliminar(mascota_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/mascotas/{mascota_id}/disponibilidad", response_model=Disponibilidad,
         tags=["Integración"], summary="Verificar disponibilidad")
def disponibilidad(mascota_id: int):
    mascota = obtener_o_404(mascota_id)
    return {
        "mascota_id": mascota_id,
        "estado": mascota["estado"],
        "disponible_para_solicitud": mascota["estado"] != "adoptada",
    }


@app.patch(
    "/mascotas/{mascota_id}/estado",
    response_model=Mascota,
    tags=["Integración"],
    summary="Cambiar el estado (uso interno de la API de Adopciones)",
    responses={
        401: {"description": "Falta o es incorrecta la cabecera X-Service-Key"},
        404: {"description": "No existe"},
        409: {"description": "Transición de estado no permitida"},
    },
)
def cambiar_estado(
    mascota_id: int,
    cambio: CambioEstado,
    x_service_key: Optional[str] = Header(None, description="Clave compartida entre servicios"),
):
    verificar_clave_servicio(x_service_key)
    mascota = obtener_o_404(mascota_id)
    actual, nuevo = mascota["estado"], cambio.estado

    if actual == nuevo:
        return mascota  # idempotente: repetir la misma orden no es error

    if nuevo not in TRANSICIONES[actual]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede pasar de '{actual}' a '{nuevo}'.",
        )
    return repo.actualizar(mascota_id, {"estado": nuevo})
