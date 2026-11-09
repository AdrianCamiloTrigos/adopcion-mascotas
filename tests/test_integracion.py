"""Pruebas de integración entre la API de Mascotas y la API de Adopciones.

Se ejecutan contra las APIs reales (locales o desplegadas), por HTTP:

    MASCOTAS_URL=https://...  ADOPCIONES_URL=https://...  SERVICE_API_KEY=...  pytest -v tests/

Cada prueba crea sus propias mascotas, así que se puede correr varias veces
sobre la misma base de datos sin chocar con datos anteriores.
"""
import os
import random
import threading

import httpx
import pytest

MASCOTAS = os.getenv("MASCOTAS_URL", "http://localhost:8001").rstrip("/")
ADOPCIONES = os.getenv("ADOPCIONES_URL", "http://localhost:8002").rstrip("/")
SERVICE_KEY = os.getenv("SERVICE_API_KEY", "")

http = httpx.Client(timeout=90)


# ----------------------------------------------------------------------
# Ayudantes
# ----------------------------------------------------------------------
def nueva_mascota(nombre="Prueba") -> dict:
    r = http.post(f"{MASCOTAS}/mascotas", json={
        "nombre": f"{nombre}-{random.randint(1000, 9999)}",
        "especie": "perro", "raza": "Criolla", "sexo": "hembra", "edad_meses": 12,
        "descripcion": "Creada por las pruebas de integración",
    })
    assert r.status_code == 201, r.text
    return r.json()


def estado_mascota(mascota_id: int) -> str:
    return http.get(f"{MASCOTAS}/mascotas/{mascota_id}").json()["estado"]


def documento() -> str:
    return str(random.randint(10**9, 10**10 - 1))


def nueva_solicitud(mascota_id: int, nombre="Laura Sanjuán", doc=None) -> httpx.Response:
    return http.post(f"{ADOPCIONES}/solicitudes", json={
        "mascota_id": mascota_id,
        "nombre_solicitante": nombre,
        "documento": doc or documento(),
        "email": "laura.sanjuan@gmail.com",
        "telefono": "3157894512",
        "ciudad": "Ocaña",
        "motivo": "Tengo casa con patio y tiempo para cuidarla.",
    })


# ----------------------------------------------------------------------
# Pruebas
# ----------------------------------------------------------------------
def test_01_ambos_servicios_responden():
    assert http.get(f"{MASCOTAS}/").json()["estado"] == "ok"
    salud = http.get(f"{ADOPCIONES}/salud").json()
    assert salud["estado"] == "ok"
    assert salud["api_mascotas"]["estado"] == "ok", "Adopciones no logra hablar con Mascotas"


def test_02_swagger_publicado_en_ambas_apis():
    for base in (MASCOTAS, ADOPCIONES):
        assert http.get(f"{base}/openapi.json").status_code == 200
        assert http.get(f"{base}/docs").status_code == 200


def test_03_solicitud_cambia_mascota_a_en_proceso():
    m = nueva_mascota("Luna")
    assert m["estado"] == "disponible"
    r = nueva_solicitud(m["id"])
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "pendiente"
    assert estado_mascota(m["id"]) == "en_proceso"


def test_04_solicitud_para_mascota_inexistente_da_404():
    r = nueva_solicitud(999_999_999)
    assert r.status_code == 404


def test_05_misma_persona_no_duplica_solicitud_pendiente():
    m = nueva_mascota("Canela")
    doc = documento()
    assert nueva_solicitud(m["id"], doc=doc).status_code == 201
    r = nueva_solicitud(m["id"], doc=doc)
    assert r.status_code == 409, r.text


def test_06_proceso_completo_de_adopcion():
    """Consultar → solicitar (x2) → aprobar una → mascota adoptada → la otra se rechaza sola."""
    m = nueva_mascota("Rocky")
    s1 = nueva_solicitud(m["id"], "Camilo Quintero").json()
    s2 = nueva_solicitud(m["id"], "Yeimy Carrascal").json()
    assert estado_mascota(m["id"]) == "en_proceso"

    r = http.patch(f"{ADOPCIONES}/solicitudes/{s1['id']}/aprobar",
                   json={"observacion": "Visita domiciliaria aprobada"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["solicitud"]["estado"] == "aprobada"
    assert cuerpo["mascota"]["estado"] == "adoptada"
    assert s2["id"] in cuerpo["rechazadas_automaticamente"]

    assert estado_mascota(m["id"]) == "adoptada"
    assert http.get(f"{ADOPCIONES}/solicitudes/{s2['id']}").json()["estado"] == "rechazada"

    detalle = http.get(f"{ADOPCIONES}/solicitudes/{s1['id']}").json()
    assert detalle["mascota"]["id"] == m["id"], "El detalle debe traer la mascota desde la API 1"


def test_07_no_se_solicita_una_mascota_adoptada():
    m = nueva_mascota("Michi")
    s = nueva_solicitud(m["id"]).json()
    http.patch(f"{ADOPCIONES}/solicitudes/{s['id']}/aprobar")
    r = nueva_solicitud(m["id"])
    assert r.status_code == 409


def test_08_no_se_aprueba_dos_veces_la_misma_solicitud():
    m = nueva_mascota("Pelusa")
    s = nueva_solicitud(m["id"]).json()
    assert http.patch(f"{ADOPCIONES}/solicitudes/{s['id']}/aprobar").status_code == 200
    assert http.patch(f"{ADOPCIONES}/solicitudes/{s['id']}/aprobar").status_code == 409


def test_09_aprobaciones_simultaneas_solo_una_gana():
    """Dos administradores aprueban al mismo tiempo dos solicitudes de la misma mascota."""
    m = nueva_mascota("Tambor")
    ids = [nueva_solicitud(m["id"]).json()["id"] for _ in range(2)]
    codigos = []

    def aprobar(sid):
        c = httpx.Client(timeout=90)
        codigos.append(c.patch(f"{ADOPCIONES}/solicitudes/{sid}/aprobar").status_code)

    hilos = [threading.Thread(target=aprobar, args=(i,)) for i in ids]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(codigos) == [200, 409], codigos
    aprobadas = http.get(f"{ADOPCIONES}/solicitudes",
                         params={"mascota_id": m["id"], "estado": "aprobada"}).json()
    assert len(aprobadas) == 1


def test_10_rechazar_la_ultima_pendiente_libera_la_mascota():
    m = nueva_mascota("Nube")
    s1 = nueva_solicitud(m["id"]).json()
    s2 = nueva_solicitud(m["id"]).json()

    http.patch(f"{ADOPCIONES}/solicitudes/{s1['id']}/rechazar", json={"observacion": "Sin patio"})
    assert estado_mascota(m["id"]) == "en_proceso", "Aún queda una pendiente"

    r = http.patch(f"{ADOPCIONES}/solicitudes/{s2['id']}/rechazar")
    assert r.status_code == 200
    assert r.json()["mascota"]["estado"] == "disponible"
    assert estado_mascota(m["id"]) == "disponible"


def test_11_mascota_adoptada_no_vuelve_a_disponible():
    m = nueva_mascota("Toby")
    s = nueva_solicitud(m["id"]).json()
    http.patch(f"{ADOPCIONES}/solicitudes/{s['id']}/aprobar")
    cab = {"X-Service-Key": SERVICE_KEY} if SERVICE_KEY else {}
    r = http.patch(f"{MASCOTAS}/mascotas/{m['id']}/estado", json={"estado": "disponible"}, headers=cab)
    assert r.status_code == 409


@pytest.mark.skipif(not SERVICE_KEY, reason="SERVICE_API_KEY no configurada")
def test_12_cambio_de_estado_exige_clave_de_servicio():
    m = nueva_mascota("Lola")
    r = http.patch(f"{MASCOTAS}/mascotas/{m['id']}/estado", json={"estado": "adoptada"})
    assert r.status_code == 401
    assert estado_mascota(m["id"]) == "disponible"


def test_13_no_se_elimina_mascota_con_proceso_en_curso():
    m = nueva_mascota("Kira")
    nueva_solicitud(m["id"])
    assert http.delete(f"{MASCOTAS}/mascotas/{m['id']}").status_code == 409
