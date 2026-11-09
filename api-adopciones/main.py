"""API 2 - Adopciones

Registra, consulta y gestiona las solicitudes de adopción.
Es la única dueña de la tabla `solicitudes` y se comunica con la
API de Mascotas por HTTP para verificar disponibilidad y actualizar estados.
"""
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

import cliente_mascotas as mascotas  # noqa: E402
from db import ConflictoUnico, crear_repo  # noqa: E402

EstadoSolicitud = Literal["pendiente", "aprobada", "rechazada"]
ORIGENES = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(
    title="API de Adopciones",
    version="1.0.0",
    description=(
        "Servicio de la Fundación Huellas de Esperanza que gestiona las solicitudes de adopción.\n\n"
        "Antes de registrar, aprobar o rechazar una solicitud, este servicio consulta la "
        "**API de Mascotas** por HTTP y le pide que actualice el estado del animal:\n\n"
        "| Acción | Estado de la mascota |\n"
        "|---|---|\n"
        "| Se registra la primera solicitud | `disponible` → `en_proceso` |\n"
        "| Se aprueba una solicitud | → `adoptada` (las demás pendientes se rechazan solas) |\n"
        "| Se rechaza la última pendiente | `en_proceso` → `disponible` |\n\n"
        "Una mascota nunca puede tener dos solicitudes aprobadas: lo valida la API y además "
        "lo garantiza un índice único parcial en PostgreSQL."
    ),
    openapi_tags=[
        {"name": "Solicitudes", "description": "Registro y consulta de solicitudes."},
        {"name": "Gestión", "description": "Aprobar o rechazar (requiere comunicación con la API de Mascotas)."},
        {"name": "Salud", "description": "Estado del servicio y de sus dependencias."},
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
class SolicitudCrear(BaseModel):
    mascota_id: int = Field(..., ge=1, examples=[1])
    nombre_solicitante: str = Field(..., min_length=3, max_length=100, examples=["Camilo Quintero"])
    documento: str = Field(..., min_length=5, max_length=20, pattern=r"^[0-9A-Za-z\-]+$",
                           examples=["1091678234"])
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                       examples=["camilo.quintero@gmail.com"])
    telefono: str = Field(..., min_length=7, max_length=20, examples=["3157894512"])
    ciudad: Optional[str] = Field(None, max_length=60, examples=["Ocaña"])
    motivo: str = Field(..., min_length=10, max_length=600,
                        examples=["Vivo en casa con patio y tengo tiempo para sacarla a caminar."])


class Decision(BaseModel):
    observacion: Optional[str] = Field(None, max_length=300, examples=["Visita domiciliaria aprobada"])


class Solicitud(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    mascota_id: int
    nombre_solicitante: str
    documento: str
    email: str
    telefono: str
    ciudad: Optional[str] = None
    motivo: str
    estado: EstadoSolicitud
    observacion: Optional[str] = None
    creado_en: Optional[str] = None
    actualizado_en: Optional[str] = None


class SolicitudDetalle(Solicitud):
    mascota: Optional[dict] = Field(None, description="Datos traídos de la API de Mascotas")


class ResultadoAprobacion(BaseModel):
    solicitud: Solicitud
    mascota: dict
    rechazadas_automaticamente: list[int]


class ResultadoRechazo(BaseModel):
    solicitud: Solicitud
    mascota: Optional[dict] = None
    aviso: Optional[str] = None


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def obtener_o_404(solicitud_id: int) -> dict:
    sol = repo.obtener(solicitud_id)
    if not sol:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"La solicitud {solicitud_id} no existe")
    return sol


def exigir_pendiente(sol: dict) -> None:
    if sol["estado"] != "pendiente":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"La solicitud {sol['id']} ya fue {sol['estado']} y no se puede modificar.",
        )


def consultar_mascota(mascota_id: int) -> Optional[dict]:
    try:
        return mascotas.obtener_mascota(mascota_id)
    except mascotas.ErrorServicioMascotas as e:
        raise mascotas.servicio_no_disponible(e)


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/", tags=["Salud"], summary="Estado del servicio")
def raiz():
    return {"servicio": "api-adopciones", "estado": "ok", "docs": "/docs"}


@app.get("/salud", tags=["Salud"], summary="Estado del servicio y de la API de Mascotas")
def salud():
    return {"servicio": "api-adopciones", "estado": "ok", "api_mascotas": mascotas.salud()}


@app.get("/solicitudes", response_model=list[Solicitud], tags=["Solicitudes"],
         summary="Listar solicitudes")
def listar_solicitudes(
    estado: Optional[EstadoSolicitud] = Query(None, description="Filtrar por estado"),
    mascota_id: Optional[int] = Query(None, description="Filtrar por mascota"),
):
    return repo.listar(estado=estado, mascota_id=mascota_id)


@app.get("/solicitudes/{solicitud_id}", response_model=SolicitudDetalle, tags=["Solicitudes"],
         summary="Consultar una solicitud con los datos de su mascota")
def obtener_solicitud(solicitud_id: int):
    sol = obtener_o_404(solicitud_id)
    try:
        sol["mascota"] = mascotas.obtener_mascota(sol["mascota_id"])
    except mascotas.ErrorServicioMascotas:
        sol["mascota"] = None  # la solicitud se muestra aunque Mascotas esté caída
    return sol


@app.post(
    "/solicitudes",
    response_model=Solicitud,
    status_code=status.HTTP_201_CREATED,
    tags=["Solicitudes"],
    summary="Registrar una solicitud de adopción",
    responses={
        404: {"description": "La mascota no existe"},
        409: {"description": "La mascota ya fue adoptada o la persona ya tiene una solicitud pendiente"},
        503: {"description": "La API de Mascotas no responde"},
    },
)
def crear_solicitud(datos: SolicitudCrear):
    # 1. Verificar la mascota en la API de Mascotas
    mascota = consultar_mascota(datos.mascota_id)
    if not mascota:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"La mascota {datos.mascota_id} no existe")
    if mascota["estado"] == "adoptada":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{mascota['nombre']} ya fue adoptada")

    # 2. Guardar la solicitud
    try:
        nueva = repo.crear({**datos.model_dump(), "estado": "pendiente"})
    except ConflictoUnico:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya existe una solicitud pendiente de este documento para {mascota['nombre']}",
        )

    # 3. Marcar la mascota "en_proceso" (solo con la primera solicitud)
    if mascota["estado"] == "disponible":
        try:
            mascotas.cambiar_estado(datos.mascota_id, "en_proceso", f"Solicitud #{nueva['id']} registrada")
        except (mascotas.ErrorServicioMascotas, HTTPException) as e:
            # Compensación: sin el cambio de estado la solicitud queda inconsistente
            repo.eliminar(nueva["id"])
            detalle = e.detail if isinstance(e, HTTPException) else str(e)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"No se registró la solicitud porque falló la actualización de la mascota: {detalle}",
            )
    return nueva


@app.patch(
    "/solicitudes/{solicitud_id}/aprobar",
    response_model=ResultadoAprobacion,
    tags=["Gestión"],
    summary="Aprobar una solicitud",
    responses={
        404: {"description": "La solicitud o la mascota no existen"},
        409: {"description": "La solicitud no está pendiente o la mascota ya tiene una adopción aprobada"},
        503: {"description": "La API de Mascotas no responde (se revierte la aprobación)"},
    },
)
def aprobar_solicitud(solicitud_id: int, decision: Optional[Decision] = None):
    observacion = decision.observacion if decision else None
    sol = obtener_o_404(solicitud_id)
    exigir_pendiente(sol)

    # 1. Verificar disponibilidad en la API de Mascotas
    mascota = consultar_mascota(sol["mascota_id"])
    if not mascota:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"La mascota {sol['mascota_id']} ya no existe")
    if mascota["estado"] == "adoptada":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{mascota['nombre']} ya fue adoptada")

    # 2. Aprobar en la base de datos (el índice único frena aprobaciones simultáneas)
    try:
        aprobada = repo.actualizar(solicitud_id, {"estado": "aprobada", "observacion": observacion})
    except ConflictoUnico:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{mascota['nombre']} ya tiene otra solicitud aprobada",
        )

    # 3. Marcar la mascota como adoptada. Si falla, se revierte el paso 2.
    try:
        mascota = mascotas.cambiar_estado(sol["mascota_id"], "adoptada", f"Solicitud #{solicitud_id} aprobada")
    except (mascotas.ErrorServicioMascotas, HTTPException) as e:
        repo.actualizar(solicitud_id, {"estado": "pendiente", "observacion": sol.get("observacion")})
        detalle = e.detail if isinstance(e, HTTPException) else str(e)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Se revirtió la aprobación porque no se pudo actualizar la mascota: {detalle}",
        )

    # 4. Rechazar automáticamente las otras solicitudes pendientes de esa mascota
    rechazadas = []
    for otra in repo.listar(estado="pendiente", mascota_id=sol["mascota_id"]):
        repo.actualizar(otra["id"], {
            "estado": "rechazada",
            "observacion": f"Rechazada automáticamente: {mascota['nombre']} fue adoptada "
                           f"con la solicitud #{solicitud_id}",
        })
        rechazadas.append(otra["id"])

    return {"solicitud": aprobada, "mascota": mascota, "rechazadas_automaticamente": rechazadas}


@app.patch(
    "/solicitudes/{solicitud_id}/rechazar",
    response_model=ResultadoRechazo,
    tags=["Gestión"],
    summary="Rechazar una solicitud",
    responses={
        404: {"description": "La solicitud no existe"},
        409: {"description": "La solicitud no está pendiente"},
    },
)
def rechazar_solicitud(solicitud_id: int, decision: Optional[Decision] = None):
    observacion = decision.observacion if decision else None
    sol = obtener_o_404(solicitud_id)
    exigir_pendiente(sol)

    rechazada = repo.actualizar(solicitud_id, {"estado": "rechazada", "observacion": observacion})

    # Si no quedan solicitudes pendientes, la mascota vuelve a estar disponible
    mascota, aviso = None, None
    if not repo.listar(estado="pendiente", mascota_id=sol["mascota_id"]):
        try:
            mascota = mascotas.obtener_mascota(sol["mascota_id"])
            if mascota and mascota["estado"] == "en_proceso":
                mascota = mascotas.cambiar_estado(
                    sol["mascota_id"], "disponible", f"Solicitud #{solicitud_id} rechazada"
                )
        except (mascotas.ErrorServicioMascotas, HTTPException) as e:
            # El rechazo es válido igual; solo se avisa que la mascota no se liberó
            detalle = e.detail if isinstance(e, HTTPException) else str(e)
            aviso = f"La solicitud se rechazó, pero no se pudo liberar la mascota: {detalle}"

    return {"solicitud": rechazada, "mascota": mascota, "aviso": aviso}
