"""Recorre el proceso completo de adopción y muestra cada petición HTTP.

Sirve como evidencia de integración y como demo en la socialización:

    python tests/demo_flujo.py
    MASCOTAS_URL=https://... ADOPCIONES_URL=https://... python tests/demo_flujo.py
"""
import json
import os
import random

import httpx

MASCOTAS = os.getenv("MASCOTAS_URL", "http://localhost:8001").rstrip("/")
ADOPCIONES = os.getenv("ADOPCIONES_URL", "http://localhost:8002").rstrip("/")
http = httpx.Client(timeout=90)
paso = 0


def llamar(metodo, url, cuerpo=None, titulo=""):
    global paso
    paso += 1
    print(f"\n── Paso {paso}: {titulo}")
    print(f"   {metodo} {url}")
    if cuerpo:
        print(f"   body: {json.dumps(cuerpo, ensure_ascii=False)}")
    r = http.request(metodo, url, json=cuerpo)
    datos = r.json() if r.content else None
    resumen = json.dumps(datos, ensure_ascii=False)
    print(f"   ← {r.status_code}  {resumen[:300]}{'…' if len(resumen) > 300 else ''}")
    return r.status_code, datos


def solicitud(mascota_id, nombre, doc):
    return {
        "mascota_id": mascota_id, "nombre_solicitante": nombre, "documento": doc,
        "email": f"{nombre.split()[0].lower()}@gmail.com", "telefono": "3157894512",
        "ciudad": "Ocaña", "motivo": "Tengo espacio y tiempo para cuidar a la mascota.",
    }


print("=" * 70)
print("DEMO · Proceso completo de adopción (API Mascotas ↔ API Adopciones)")
print(f"API Mascotas:   {MASCOTAS}\nAPI Adopciones: {ADOPCIONES}")
print("=" * 70)

llamar("GET", f"{ADOPCIONES}/salud", titulo="Adopciones verifica que Mascotas está en línea")

_, m = llamar("POST", f"{MASCOTAS}/mascotas", {
    "nombre": f"Firulais-{random.randint(100, 999)}", "especie": "perro", "raza": "Criollo",
    "sexo": "macho", "edad_meses": 20, "descripcion": "Mascota creada para la demostración",
}, "Registrar una mascota (API 1)")
mid = m["id"]

llamar("GET", f"{MASCOTAS}/mascotas/{mid}/disponibilidad", titulo="Consultar disponibilidad")

_, s1 = llamar("POST", f"{ADOPCIONES}/solicitudes",
               solicitud(mid, "Camilo Quintero", str(random.randint(10**9, 10**10))),
               "Primera solicitud (API 2 consulta a API 1 y la pasa a en_proceso)")
_, s2 = llamar("POST", f"{ADOPCIONES}/solicitudes",
               solicitud(mid, "Yeimy Carrascal", str(random.randint(10**9, 10**10))),
               "Segunda solicitud para la misma mascota")

llamar("GET", f"{MASCOTAS}/mascotas/{mid}", titulo="La mascota ahora está en_proceso")

llamar("PATCH", f"{ADOPCIONES}/solicitudes/{s1['id']}/aprobar", {"observacion": "Visita domiciliaria aprobada"},
       "Aprobar la primera solicitud")

llamar("GET", f"{MASCOTAS}/mascotas/{mid}", titulo="La mascota quedó adoptada")
llamar("GET", f"{ADOPCIONES}/solicitudes/{s2['id']}", titulo="La segunda solicitud se rechazó sola")

codigo, _ = llamar("PATCH", f"{ADOPCIONES}/solicitudes/{s2['id']}/aprobar",
                   titulo="Intentar aprobar la segunda (debe fallar con 409)")
codigo2, _ = llamar("POST", f"{ADOPCIONES}/solicitudes",
                    solicitud(mid, "Diego Pacheco", str(random.randint(10**9, 10**10))),
                    "Nueva solicitud para una mascota adoptada (debe fallar con 409)")

print("\n" + "=" * 70)
ok = codigo == 409 and codigo2 == 409
print("RESULTADO:", "✅ proceso completo correcto" if ok else "❌ revisar")
print("=" * 70)
