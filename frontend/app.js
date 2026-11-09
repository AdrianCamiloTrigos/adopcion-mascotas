// =====================================================================
// Frontend · Huellas de Esperanza
// Consume la API de Mascotas y la API de Adopciones por HTTP/JSON.
// =====================================================================
const { MASCOTAS_API, ADOPCIONES_API } = window.APP_CONFIG;

const ESTADOS = {
  disponible: "Disponible",
  en_proceso: "En proceso",
  adoptada: "Adoptada",
  pendiente: "Pendiente",
  aprobada: "Aprobada",
  rechazada: "Rechazada",
};
const EMOJI = { perro: "🐶", gato: "🐱", otro: "🐰" };

let mascotasCache = [];      // para mostrar el nombre de la mascota en cada solicitud
let filtroSolicitud = "";

// ---------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);

function esc(texto) {
  // Evita inyección de HTML con datos escritos por usuarios
  return String(texto ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function toast(mensaje, tipo = "") {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.textContent = mensaje;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 5000);
}

function edadTexto(meses) {
  if (meses == null) return "Edad desconocida";
  if (meses < 12) return `${meses} ${meses === 1 ? "mes" : "meses"}`;
  const a = Math.floor(meses / 12);
  return `${a} ${a === 1 ? "año" : "años"}`;
}

function fecha(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
}

// Llamada HTTP con manejo de errores y aviso de "servidor despertando"
async function api(base, ruta, opciones = {}) {
  const temporizador = setTimeout(() => ($("#aviso-despertar").hidden = false), 4000);
  try {
    const r = await fetch(`${base}${ruta}`, {
      headers: { "Content-Type": "application/json" },
      ...opciones,
    });
    if (r.status === 204) return null;
    const cuerpo = await r.json().catch(() => ({}));
    if (!r.ok) {
      let detalle = cuerpo.detail;
      if (Array.isArray(detalle)) {
        // Errores de validación de FastAPI
        detalle = detalle.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join(" · ");
      }
      throw new Error(detalle || `Error ${r.status}`);
    }
    return cuerpo;
  } catch (e) {
    if (e instanceof TypeError) throw new Error("No hay conexión con el servidor");
    throw e;
  } finally {
    clearTimeout(temporizador);
    $("#aviso-despertar").hidden = true;
  }
}

// ---------------------------------------------------------------------
// Navegación por pestañas
// ---------------------------------------------------------------------
function mostrarVista(nombre) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("activo", t.dataset.vista === nombre));
  document.querySelectorAll(".vista").forEach((v) => v.classList.toggle("activa", v.id === `vista-${nombre}`));
  if (nombre === "adoptar") cargarMascotas();
  if (nombre === "solicitudes") cargarSolicitudes();
  if (nombre === "sistema") revisarSistema();
}

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => mostrarVista(t.dataset.vista))
);

// ---------------------------------------------------------------------
// Mascotas
// ---------------------------------------------------------------------
async function cargarMascotas() {
  const grid = $("#grid-mascotas");
  grid.innerHTML = `<p class="cargando">Cargando mascotas…</p>`;
  const params = new URLSearchParams();
  if ($("#filtro-especie").value) params.set("especie", $("#filtro-especie").value);
  if ($("#filtro-estado").value) params.set("estado", $("#filtro-estado").value);

  try {
    const lista = await api(MASCOTAS_API, `/mascotas?${params}`);
    if (!params.toString()) mascotasCache = lista;
    if (!lista.length) {
      grid.innerHTML = `<p class="vacio">No hay mascotas con esos filtros.</p>`;
      return;
    }
    grid.innerHTML = lista.map(tarjetaMascota).join("");
  } catch (e) {
    grid.innerHTML = `<p class="vacio">No se pudieron cargar las mascotas.<br>${esc(e.message)}</p>`;
  }
}

function tarjetaMascota(m) {
  const foto = m.foto_url
    ? `<img src="${esc(m.foto_url)}" alt="Foto de ${esc(m.nombre)}" loading="lazy"
         onerror="this.replaceWith(document.createTextNode('${EMOJI[m.especie] || "🐾"}'))">`
    : EMOJI[m.especie] || "🐾";
  const datos = [m.raza, m.sexo, edadTexto(m.edad_meses)].filter(Boolean).map(esc).join(" · ");
  const boton = m.estado === "adoptada"
    ? `<button class="btn" disabled>Ya tiene hogar 💛</button>`
    : `<button class="btn primario" onclick="abrirSolicitud(${m.id})">Quiero adoptar${m.sexo === "hembra" ? "la" : "lo"}</button>`;
  return `
    <article class="tarjeta mascota">
      <div class="foto ${esc(m.especie)}">${foto}</div>
      <div class="cuerpo">
        <div class="titulo">
          <h3>${esc(m.nombre)}</h3>
          <span class="badge ${m.estado}">${ESTADOS[m.estado]}</span>
        </div>
        <p class="datos">${datos}</p>
        <p class="desc">${esc(m.descripcion || "")}</p>
        ${boton}
      </div>
    </article>`;
}

$("#filtro-especie").addEventListener("change", cargarMascotas);
$("#filtro-estado").addEventListener("change", cargarMascotas);

$("#form-mascota").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const datos = Object.fromEntries(new FormData(form));
  for (const k of Object.keys(datos)) if (datos[k] === "") delete datos[k];
  if (datos.edad_meses) datos.edad_meses = Number(datos.edad_meses);

  const boton = form.querySelector("button[type=submit]");
  boton.disabled = true;
  try {
    const m = await api(MASCOTAS_API, "/mascotas", { method: "POST", body: JSON.stringify(datos) });
    toast(`${m.nombre} quedó registrada y disponible para adopción`, "exito");
    form.reset();
    mostrarVista("adoptar");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    boton.disabled = false;
  }
});

// ---------------------------------------------------------------------
// Registrar solicitud
// ---------------------------------------------------------------------
async function abrirSolicitud(id) {
  const m = mascotasCache.find((x) => x.id === id) || (await api(MASCOTAS_API, `/mascotas/${id}`));
  const form = $("#form-solicitud");
  form.reset();
  form.mascota_id.value = id;
  $("#modal-nombre").textContent = m.nombre;
  $("#modal-solicitud").showModal();
}
window.abrirSolicitud = abrirSolicitud;

$("#form-solicitud").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const datos = Object.fromEntries(new FormData(form));
  datos.mascota_id = Number(datos.mascota_id);
  if (!datos.ciudad) delete datos.ciudad;

  const boton = form.querySelector("button[type=submit]");
  boton.disabled = true;
  try {
    const s = await api(ADOPCIONES_API, "/solicitudes", { method: "POST", body: JSON.stringify(datos) });
    $("#modal-solicitud").close();
    toast(`Solicitud #${s.id} registrada. La fundación te contactará pronto.`, "exito");
    cargarMascotas();
    actualizarContador();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    boton.disabled = false;
  }
});

// ---------------------------------------------------------------------
// Gestión de solicitudes
// ---------------------------------------------------------------------
async function cargarSolicitudes() {
  const lista = $("#lista-solicitudes");
  lista.innerHTML = `<p class="cargando">Cargando solicitudes…</p>`;
  const params = filtroSolicitud ? `?estado=${filtroSolicitud}` : "";
  try {
    const [solicitudes, mascotas] = await Promise.all([
      api(ADOPCIONES_API, `/solicitudes${params}`),
      api(MASCOTAS_API, "/mascotas"),
    ]);
    mascotasCache = mascotas;
    actualizarContador();
    if (!solicitudes.length) {
      lista.innerHTML = `<p class="vacio">No hay solicitudes ${filtroSolicitud ? ESTADOS[filtroSolicitud].toLowerCase() + "s" : "todavía"}.</p>`;
      return;
    }
    lista.innerHTML = solicitudes.map(tarjetaSolicitud).join("");
  } catch (e) {
    lista.innerHTML = `<p class="vacio">No se pudieron cargar las solicitudes.<br>${esc(e.message)}</p>`;
  }
}

function tarjetaSolicitud(s) {
  const m = mascotasCache.find((x) => x.id === s.mascota_id);
  const mascota = m ? `${EMOJI[m.especie] || "🐾"} ${esc(m.nombre)}` : `Mascota #${s.mascota_id}`;
  const acciones = s.estado === "pendiente"
    ? `<div class="acciones-sol">
         <button class="btn exito" onclick="decidir(${s.id}, 'aprobar')">Aprobar</button>
         <button class="btn peligro" onclick="decidir(${s.id}, 'rechazar')">Rechazar</button>
       </div>`
    : "<div></div>";
  return `
    <article class="tarjeta solicitud">
      <div>
        <div class="cabecera">
          <span class="num">#${s.id}</span>
          <h3>${esc(s.nombre_solicitante)} → ${mascota}</h3>
          <span class="badge ${s.estado}">${ESTADOS[s.estado]}</span>
        </div>
        <p class="meta">CC ${esc(s.documento)} · ${esc(s.email)} · ${esc(s.telefono)}${s.ciudad ? " · " + esc(s.ciudad) : ""} · ${fecha(s.creado_en)}</p>
        <p class="motivo">${esc(s.motivo)}</p>
        ${s.observacion ? `<p class="obs">📝 ${esc(s.observacion)}</p>` : ""}
      </div>
      ${acciones}
    </article>`;
}

document.querySelectorAll("#chips-solicitudes .chip").forEach((c) =>
  c.addEventListener("click", () => {
    document.querySelectorAll("#chips-solicitudes .chip").forEach((x) => x.classList.remove("activo"));
    c.classList.add("activo");
    filtroSolicitud = c.dataset.estado;
    cargarSolicitudes();
  })
);

let decisionActual = null;

function decidir(id, accion) {
  decisionActual = { id, accion };
  const aprobar = accion === "aprobar";
  $("#decision-titulo").textContent = `${aprobar ? "Aprobar" : "Rechazar"} la solicitud #${id}`;
  $("#decision-texto").textContent = aprobar
    ? "La mascota quedará adoptada y las demás solicitudes pendientes para ella se rechazarán automáticamente."
    : "Si no quedan más solicitudes pendientes, la mascota vuelve a estar disponible.";
  const confirmar = $("#decision-confirmar");
  confirmar.className = `btn ${aprobar ? "exito" : "primario"}`;
  confirmar.textContent = aprobar ? "Aprobar adopción" : "Rechazar solicitud";
  $("#form-decision").reset();
  $("#modal-decision").showModal();
}
window.decidir = decidir;

$("#form-decision").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const { id, accion } = decisionActual;
  const observacion = ev.target.observacion.value.trim();
  const boton = $("#decision-confirmar");
  boton.disabled = true;
  try {
    const r = await api(ADOPCIONES_API, `/solicitudes/${id}/${accion}`, {
      method: "PATCH",
      body: JSON.stringify({ observacion: observacion || null }),
    });
    $("#modal-decision").close();
    if (accion === "aprobar") {
      const extra = r.rechazadas_automaticamente.length
        ? ` Se rechazaron automáticamente ${r.rechazadas_automaticamente.length} solicitud(es) más.`
        : "";
      toast(`¡${r.mascota.nombre} fue adoptada!${extra}`, "exito");
    } else {
      toast(r.aviso || `Solicitud #${id} rechazada${r.mascota ? `. ${r.mascota.nombre} quedó ${ESTADOS[r.mascota.estado].toLowerCase()}` : ""}.`,
        r.aviso ? "error" : "");
    }
    cargarSolicitudes();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    boton.disabled = false;
  }
});

async function actualizarContador() {
  try {
    const pendientes = await api(ADOPCIONES_API, "/solicitudes?estado=pendiente");
    const c = $("#contador-pendientes");
    c.textContent = pendientes.length;
    c.hidden = pendientes.length === 0;
  } catch { /* el contador es opcional */ }
}

// ---------------------------------------------------------------------
// Estado del sistema
// ---------------------------------------------------------------------
async function revisarServicio(tarjeta, base, ruta) {
  tarjeta.querySelector(".url").textContent = base;
  tarjeta.querySelector("a").href = `${base}/docs`;
  const estado = tarjeta.querySelector(".estado-srv");
  estado.textContent = "Revisando…";
  estado.className = "estado-srv";
  const inicio = performance.now();
  try {
    const r = await api(base, ruta);
    const ms = Math.round(performance.now() - inicio);
    estado.textContent = `● En línea (${ms} ms)`;
    estado.classList.add("ok");
    return r;
  } catch (e) {
    estado.textContent = `● Sin respuesta: ${e.message}`;
    estado.classList.add("caido");
    return null;
  }
}

async function revisarSistema() {
  const tm = $("#srv-mascotas");
  const ta = $("#srv-adopciones");
  revisarServicio(tm, MASCOTAS_API, "/");
  const salud = await revisarServicio(ta, ADOPCIONES_API, "/salud");
  ta.querySelector(".dependencia").textContent = salud
    ? `Conexión con la API de Mascotas: ${salud.api_mascotas.estado === "ok" ? "✅ correcta" : "❌ " + salud.api_mascotas.estado}`
    : "";
}

$("#btn-revisar").addEventListener("click", revisarSistema);

// Cerrar modales con el botón Cancelar
document.querySelectorAll("[data-cerrar]").forEach((b) =>
  b.addEventListener("click", () => b.closest("dialog").close())
);

// Inicio
cargarMascotas();
actualizarContador();
