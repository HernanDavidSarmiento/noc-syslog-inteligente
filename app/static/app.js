"use strict";
/* NOC Syslog Inteligente - interfaz web v0.2.0

   REGLA DE ORO: todo texto que llega de la API (logs, nombres, notas) se muestra
   con textContent o nodos de texto, NUNCA con innerHTML. Un log es un dato no
   confiable: aunque contenga HTML o JavaScript, aquí solo se ve como texto. */

const SEV = ["Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Informational", "Debug"];
// Espejo de las transiciones del backend (el servidor las valida de todos modos).
const SIGUIENTES = {
  abierto: ["asignado", "en_progreso", "cerrado"],
  asignado: ["en_progreso", "resuelto", "cerrado"],
  en_progreso: ["resuelto", "cerrado"],
  resuelto: ["en_progreso", "cerrado"],
  cerrado: [],
};
const POR_PAGINA = 50;
const $ = (id) => document.getElementById(id);

let dispositivos = [];
let paginaEventos = 0;
let vistaActual = "dashboard";
let temporizador = null;
let temporizadorAviso = null;
let dispEditando = null;

/* ---------------- utilidades ---------------- */

/** Crea un elemento. Los textos se asignan como texto, nunca como HTML. */
function el(tag, props = {}, ...hijos) {
  const nodo = document.createElement(tag);
  for (const [clave, valor] of Object.entries(props)) {
    if (clave === "text") nodo.textContent = valor;
    else if (clave === "class") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else nodo.setAttribute(clave, valor);
  }
  for (const h of hijos) if (h !== null && h !== undefined) nodo.append(h);
  return nodo;
}

function textoError(cuerpo) {
  const d = cuerpo && cuerpo.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join(" | ");
  return "Error inesperado del servidor";
}

async function api(ruta, opciones = {}) {
  const resp = await fetch(ruta, { headers: { "Content-Type": "application/json" }, ...opciones });
  if (resp.status === 204) return null;
  let cuerpo = null;
  try { cuerpo = await resp.json(); } catch (_) { /* sin cuerpo JSON */ }
  if (!resp.ok) throw new Error(textoError(cuerpo));
  return cuerpo;
}

/** Muestra fechas ISO (con Z) o de SQLite (UTC sin Z) en hora de Bogotá. */
function fmtFecha(s) {
  if (!s) return "-";
  const iso = s.includes("T") ? s : s.replace(" ", "T") + "Z";
  const d = new Date(iso);
  if (isNaN(d)) return s;
  return d.toLocaleString("es-CO", { timeZone: "America/Bogota", dateStyle: "short", timeStyle: "medium" });
}

/** Aviso: dentro del diálogo abierto, si lo hay; si no, en la barra superior. */
function avisar(mensaje, tipo = "ok") {
  const enDialogo = document.querySelector("dialog[open] .msg-dlg");
  const caja = enDialogo || $("aviso");
  caja.textContent = mensaje;
  caja.className = (enDialogo ? "msg-dlg " : "aviso ") + tipo;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => caja.classList.add("oculto"), 6000);
}

function abrirDialogo(dlg) {
  const msg = dlg.querySelector(".msg-dlg");
  if (msg) msg.classList.add("oculto");
  if (!dlg.open) dlg.showModal();
}

function badge(texto, clase) { return el("span", { class: "badge " + clase, text: texto }); }
function badgeSev(n) { return badge(`${n} ${SEV[n]}`, "sev-" + n); }

/** Dibuja una tabla a partir de columnas {titulo, celda(fila)} y un arreglo de filas. */
function renderTabla(tabla, columnas, filas, opciones = {}) {
  const { vacio = "Sin datos", claseFila = null } = opciones;
  const cuerpo = el("tbody");
  if (!filas.length) {
    cuerpo.append(el("tr", {}, el("td", { colspan: columnas.length, class: "vacio", text: vacio })));
  }
  for (const fila of filas) {
    const clase = claseFila ? claseFila(fila) : "";
    const tr = el("tr", clase ? { class: clase } : {});
    for (const c of columnas) {
      const valor = c.celda(fila);
      tr.append(el("td", {}, valor === null || valor === undefined ? "" : valor));
    }
    cuerpo.append(tr);
  }
  const cab = el("thead", {}, el("tr", {}, ...columnas.map((c) => el("th", { text: c.titulo }))));
  tabla.replaceChildren(cab, cuerpo);
}

/* ---------------- columnas reutilizables ---------------- */

function celdaMensaje(f) {
  const caja = el("div", { class: "mensaje" });
  if (f.sospechoso) {
    caja.append(el("span", { class: "badge sosp", title: f.motivo_sospecha || "Evento sospechoso", text: "⚠ sospechoso" }), " ");
  }
  caja.append(el("span", { text: f.mensaje }));   // texto plano, nunca HTML
  return caja;
}

function columnasEventos(conAccion) {
  const cols = [
    { titulo: "Fecha", celda: (f) => fmtFecha(f.fecha_evento) },
    { titulo: "Equipo", celda: (f) => f.dispositivo || "(sin equipo)" },
    { titulo: "Marca", celda: (f) => f.marca || "-" },
    { titulo: "Facility", celda: (f) => `${f.facility} ${f.facility_nombre}` },
    { titulo: "Severidad", celda: (f) => badgeSev(f.severidad) },
    { titulo: "Mensaje", celda: celdaMensaje },
    { titulo: "Origen", celda: (f) => badge(f.origen, "origen-" + f.origen) },
    { titulo: "Rep.", celda: (f) => (f.repeticiones > 1 ? "×" + f.repeticiones : "") },
  ];
  if (conAccion) {
    cols.push({
      titulo: "Acción",
      celda: (f) => el("button", { type: "button", class: "mini", text: "Crear incidente", onclick: () => abrirNuevoIncidente(f) }),
    });
  }
  return cols;
}

function columnasIncidentes() {
  return [
    { titulo: "#", celda: (i) => String(i.id) },
    { titulo: "Título", celda: (i) => i.titulo },
    { titulo: "Severidad", celda: (i) => badgeSev(i.severidad) },
    { titulo: "Estado", celda: (i) => badge(i.estado.replace("_", " "), "est-" + i.estado) },
    { titulo: "Responsable", celda: (i) => i.asignado_a || "(sin asignar)" },
    { titulo: "Equipo", celda: (i) => i.dispositivo || "-" },
    { titulo: "Creado", celda: (i) => fmtFecha(i.fecha_creacion) },
    { titulo: "", celda: (i) => el("button", { type: "button", class: "mini", text: "Abrir", onclick: () => abrirDetalle(i.id) }) },
  ];
}

/* ---------------- navegación ---------------- */

const CARGADORES = {
  dashboard: () => cargarDashboard(),
  eventos: () => cargarEventos(),
  incidentes: () => cargarIncidentes(),
  inventario: () => cargarInventario(),
};

function mostrarVista(nombre) {
  vistaActual = nombre;
  document.querySelectorAll(".vista").forEach((v) => v.classList.toggle("oculto", v.id !== "vista-" + nombre));
  document.querySelectorAll("#menu button").forEach((b) => b.classList.toggle("activo", b.dataset.vista === nombre));
  clearInterval(temporizador);
  temporizador = null;
  CARGADORES[nombre]();
  if (nombre === "dashboard") temporizador = setInterval(cargarDashboard, 10000);   // refresco automático
}

function refrescarVistaActual() { CARGADORES[vistaActual](); }

/* ---------------- dispositivos (selects compartidos) ---------------- */

function llenarSelectEquipos(sel, textoVacio) {
  const actual = sel.value;
  sel.replaceChildren(el("option", { value: "", text: textoVacio }));
  for (const d of dispositivos) sel.append(el("option", { value: String(d.id), text: `${d.nombre} (${d.marca})` }));
  sel.value = actual;
}

async function cargarDispositivos() {
  dispositivos = await api("/api/dispositivos");
  llenarSelectEquipos($("f-equipo"), "Todos");
  llenarSelectEquipos($("ni-equipo"), "(ninguno)");
}

/* ---------------- dashboard ---------------- */

async function cargarDashboard() {
  try {
    const d = await api("/api/dashboard");
    renderTarjetas(d);
    renderTabla($("tabla-dispositivos"), [
      { titulo: "Equipo", celda: (x) => x.nombre },
      { titulo: "Marca", celda: (x) => x.marca },
      { titulo: "Estado", celda: (x) => badge(x.estado, "disp-" + x.estado) },
      { titulo: "Eventos", celda: (x) => String(x.eventos) },
      { titulo: "Críticos", celda: (x) => el("span", { class: x.criticos > 0 ? "critico-num" : "", text: String(x.criticos) }) },
      { titulo: "Último evento", celda: (x) => fmtFecha(x.ultimo_evento) },
      { titulo: "Inc. sin cerrar", celda: (x) => String(x.incidentes_abiertos) },
    ], d.dispositivos.lista, { vacio: "No hay dispositivos en el inventario" });
    renderGrafico(d.eventos.por_severidad);
    const opc = { vacio: "Sin eventos", claseFila: (f) => (f.sospechoso ? "fila-sosp" : "") };
    renderTabla($("tabla-criticos"), columnasEventos(true), d.eventos.criticos_recientes, { ...opc, vacio: "Sin eventos críticos" });
    renderTabla($("tabla-recientes"), columnasEventos(false), d.eventos.recientes, opc);
    renderTabla($("tabla-inc-dash"), columnasIncidentes(), d.incidentes.lista, { vacio: "No hay incidentes sin cerrar" });
    $("ultima-actualizacion").textContent = "Actualizado: " + new Date().toLocaleTimeString("es-CO");
  } catch (e) {
    avisar("No se pudo cargar el dashboard: " + e.message, "error");
  }
}

function renderTarjetas(d) {
  const e = d.eventos, v = d.dispositivos, i = d.incidentes;
  const tarjetas = [
    { titulo: "Dispositivos", valor: v.total, clase: "",
      detalle: `${v.por_estado.activo} activos · ${v.por_estado.mantenimiento} en mantenimiento · ${v.por_estado.inactivo} inactivos` },
    { titulo: "Eventos registrados", valor: e.total, clase: "", detalle: "Simulados y reales" },
    { titulo: "Eventos críticos (0 a 2)", valor: e.criticos, clase: e.criticos > 0 ? "alerta" : "", detalle: "Emergency, Alert y Critical" },
    { titulo: "Eventos sospechosos", valor: e.sospechosos, clase: e.sospechosos > 0 ? "aviso-t" : "", detalle: "Posible inyección en el texto del log" },
    { titulo: "Incidentes sin cerrar", valor: i.sin_cerrar, clase: "",
      detalle: `${i.por_estado.abierto} abiertos · ${i.por_estado.asignado + i.por_estado.en_progreso} en curso · ${i.por_estado.resuelto} resueltos` },
  ];
  $("tarjetas").replaceChildren(...tarjetas.map((t) => el("div", { class: "tarjeta " + t.clase },
    el("div", { class: "t-titulo", text: t.titulo }),
    el("div", { class: "t-valor", text: String(t.valor) }),
    el("div", { class: "t-detalle", text: t.detalle }))));
}

function renderGrafico(porSev) {
  const max = Math.max(1, ...porSev.map((s) => s.cantidad));
  $("grafico-sev").replaceChildren(...porSev.map((s) => {
    const barra = el("div", { class: "barra-valor sev-" + s.severidad });
    barra.style.width = (s.cantidad / max) * 100 + "%";   // CSSOM: permitido por la CSP
    return el("div", { class: "barra-fila" },
      el("span", { text: `${s.severidad} ${s.nombre}` }),
      el("div", { class: "barra-fondo" }, barra),
      el("span", { class: "num", text: String(s.cantidad) }));
  }));
}

/* ---------------- eventos ---------------- */

function parametrosEventos() {
  const p = new URLSearchParams();
  if ($("f-desde").value) p.set("desde", $("f-desde").value);
  if ($("f-hasta").value) p.set("hasta", $("f-hasta").value);
  if ($("f-marca").value) p.set("marca", $("f-marca").value);
  if ($("f-equipo").value) p.set("dispositivo_id", $("f-equipo").value);
  const sev = $("f-sev").value;
  if (sev.startsWith("max")) p.set("severidad_max", sev.slice(3));
  else if (sev !== "") p.set("severidad", sev);
  if ($("f-sosp").checked) p.set("sospechoso", "true");
  p.set("limite", String(POR_PAGINA + 1));            // uno extra para saber si hay otra página
  p.set("desplazamiento", String(paginaEventos * POR_PAGINA));
  return p.toString();
}

async function cargarEventos() {
  try {
    if (!dispositivos.length) await cargarDispositivos();
    const filas = await api("/api/eventos?" + parametrosEventos());
    const pagina = filas.slice(0, POR_PAGINA);
    renderTabla($("tabla-eventos"), columnasEventos(true), pagina, {
      vacio: "No hay eventos con esos filtros",
      claseFila: (f) => (f.sospechoso ? "fila-sosp" : ""),
    });
    $("pag-info").textContent = `Página ${paginaEventos + 1} · ${pagina.length} eventos`;
    $("pag-ant").disabled = paginaEventos === 0;
    $("pag-sig").disabled = filas.length <= POR_PAGINA;
  } catch (e) {
    avisar("No se pudieron cargar los eventos: " + e.message, "error");
  }
}

/* ---------------- incidentes ---------------- */

async function cargarIncidentes() {
  try {
    const estado = $("fi-estado").value;
    const filas = await api("/api/incidentes" + (estado ? "?estado=" + encodeURIComponent(estado) : ""));
    renderTabla($("tabla-incidentes"), columnasIncidentes(), filas, { vacio: "No hay incidentes" });
  } catch (e) {
    avisar("No se pudieron cargar los incidentes: " + e.message, "error");
  }
}

function abrirNuevoIncidente(evento = null) {
  $("form-nuevo-inc").reset();
  $("ni-sev").value = "4";
  $("ni-evento").value = evento ? String(evento.id) : "";
  if (evento) {
    // Solo se precargan datos estructurados; el texto del log NO se copia al formulario.
    $("ni-titulo").value = `Incidente sev ${evento.severidad} en ${evento.dispositivo || "equipo desconocido"}`;
    $("ni-desc").value = `Creado a partir del evento #${evento.id}.`;
    $("ni-sev").value = String(evento.severidad);
    $("ni-equipo").value = evento.dispositivo_id ? String(evento.dispositivo_id) : "";
  }
  abrirDialogo($("dlg-nuevo-inc"));
}

async function abrirDetalle(id) {
  try {
    const inc = await api(`/api/incidentes/${id}`);
    renderDetalle(inc);
    abrirDialogo($("dlg-detalle-inc"));
  } catch (e) {
    avisar(e.message, "error");
  }
}

function renderDetalle(inc) {
  const tablaEv = el("table");
  renderTabla(tablaEv, [
    { titulo: "Fecha", celda: (f) => fmtFecha(f.fecha_evento) },
    { titulo: "Severidad", celda: (f) => badgeSev(f.severidad) },
    { titulo: "Mensaje", celda: celdaMensaje },
    { titulo: "Origen", celda: (f) => badge(f.origen, "origen-" + f.origen) },
  ], inc.eventos_vinculados, { vacio: "Sin eventos vinculados" });

  const tablaHist = el("table");
  renderTabla(tablaHist, [
    { titulo: "Fecha", celda: (h) => fmtFecha(h.fecha) },
    { titulo: "Actor", celda: (h) => `${h.actor} (${h.tipo_actor})` },
    { titulo: "Acción", celda: (h) => h.accion },
    { titulo: "Detalle", celda: (h) => el("div", { class: "mensaje", text: h.detalle || "" }) },
  ], inc.historial, { vacio: "Sin historial" });

  const datos = el("dl", { class: "datos" },
    el("dt", { text: "Equipo" }), el("dd", { text: inc.dispositivo || "-" }),
    el("dt", { text: "Responsable" }), el("dd", { text: inc.asignado_a || "(sin asignar)" }),
    el("dt", { text: "Creado" }), el("dd", { text: fmtFecha(inc.fecha_creacion) }),
    el("dt", { text: "Cerrado" }), el("dd", { text: inc.fecha_cierre ? fmtFecha(inc.fecha_cierre) : "-" }));

  $("detalle-inc").replaceChildren(...[
    el("h3", { text: `Incidente #${inc.id}: ${inc.titulo}` }),
    el("p", {}, badgeSev(inc.severidad), " ", badge(inc.estado.replace("_", " "), "est-" + inc.estado)),
    datos,
    el("p", { text: inc.descripcion || "(sin descripción)" }),
    inc.notas_cierre ? el("p", { class: "notas", text: "Notas de cierre: " + inc.notas_cierre }) : null,
    el("h4", { text: "Eventos vinculados" }), el("div", { class: "scroll" }, tablaEv),
    el("h4", { text: "Historial (auditoría)" }), el("div", { class: "scroll" }, tablaHist),
    formularioActualizar(inc),
  ].filter(Boolean));
}

function formularioActualizar(inc) {
  if (inc.estado === "cerrado") return el("p", { class: "suave", text: "Incidente cerrado: no admite cambios." });

  const selEstado = el("select", {}, ...[inc.estado, ...SIGUIENTES[inc.estado]].map((e) => el("option", { value: e, text: e.replace("_", " ") })));
  const inpAsig = el("input", { maxlength: "64", value: inc.asignado_a || "" });
  const txtNotas = el("textarea", { rows: "3", maxlength: "2000" });
  const filaNotas = el("label", { class: "oculto" }, "Notas de cierre (obligatorias al cerrar)", txtNotas);
  selEstado.addEventListener("change", () => filaNotas.classList.toggle("oculto", selEstado.value !== "cerrado"));

  const form = el("form", { class: "form-grid" },
    el("h4", { text: "Seguimiento" }),
    el("label", {}, "Estado", selEstado),
    el("label", {}, "Responsable", inpAsig),
    filaNotas,
    el("div", { class: "botones" }, el("button", { type: "submit", text: "Guardar cambios" })));

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const cuerpo = {};
    if (selEstado.value !== inc.estado) cuerpo.estado = selEstado.value;
    const asig = inpAsig.value.trim();
    if (asig && asig !== (inc.asignado_a || "")) cuerpo.asignado_a = asig;
    if (selEstado.value === "cerrado") cuerpo.notas_cierre = txtNotas.value.trim();
    if (!Object.keys(cuerpo).length) return avisar("No hay cambios que guardar", "error");
    try {
      await api(`/api/incidentes/${inc.id}`, { method: "PATCH", body: JSON.stringify(cuerpo) });
      await abrirDetalle(inc.id);
      avisar("Incidente actualizado");
      refrescarVistaActual();
    } catch (e) {
      avisar(e.message, "error");    // el servidor es quien aplica las reglas
    }
  });
  return form;
}

/* ---------------- inventario ---------------- */

function leerFormDisp() {
  return {
    nombre: $("d-nombre").value.trim(), ip: $("d-ip").value.trim(), marca: $("d-marca").value,
    modelo: $("d-modelo").value.trim(), version: $("d-version").value.trim(),
    ubicacion: $("d-ubicacion").value.trim(), estado: $("d-estado").value,
  };
}

function limpiarFormDisp() {
  dispEditando = null;
  $("form-disp").reset();
  $("d-titulo").textContent = "Nuevo equipo";
  $("d-guardar").textContent = "Agregar equipo";
  $("d-cancelar").classList.add("oculto");
}

function editarDisp(d) {
  dispEditando = d;
  for (const campo of ["nombre", "ip", "marca", "modelo", "version", "ubicacion", "estado"]) $("d-" + campo).value = d[campo];
  $("d-titulo").textContent = `Editando: ${d.nombre}`;
  $("d-guardar").textContent = "Guardar cambios";
  $("d-cancelar").classList.remove("oculto");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function eliminarDisp(d) {
  if (!confirm(`¿Eliminar ${d.nombre}? Sus eventos se conservan, pero quedan sin equipo.`)) return;
  try {
    await api(`/api/dispositivos/${d.id}`, { method: "DELETE" });
    avisar("Equipo eliminado");
    await cargarInventario();
  } catch (e) {
    avisar(e.message, "error");
  }
}

async function cargarInventario() {
  try {
    await cargarDispositivos();
    renderTabla($("tabla-inventario"), [
      { titulo: "Nombre", celda: (d) => d.nombre },
      { titulo: "IP", celda: (d) => d.ip },
      { titulo: "Marca", celda: (d) => d.marca },
      { titulo: "Modelo", celda: (d) => d.modelo },
      { titulo: "Versión", celda: (d) => d.version },
      { titulo: "Ubicación", celda: (d) => d.ubicacion },
      { titulo: "Estado", celda: (d) => badge(d.estado, "disp-" + d.estado) },
      { titulo: "Actualizado", celda: (d) => fmtFecha(d.fecha_actualizacion) },
      { titulo: "Acciones", celda: (d) => el("div", { class: "botones" },
          el("button", { type: "button", class: "mini secundario", text: "Editar", onclick: () => editarDisp(d) }),
          el("button", { type: "button", class: "mini peligro", text: "Eliminar", onclick: () => eliminarDisp(d) })) },
    ], dispositivos, { vacio: "No hay equipos" });
  } catch (e) {
    avisar("No se pudo cargar el inventario: " + e.message, "error");
  }
}

/* ---------------- eventos de la interfaz ---------------- */

function iniciar() {
  document.querySelectorAll("#menu button").forEach((b) => b.addEventListener("click", () => mostrarVista(b.dataset.vista)));
  $("btn-refrescar").addEventListener("click", cargarDashboard);

  // Severidades del formulario de incidentes
  for (let n = 0; n <= 7; n++) $("ni-sev").append(el("option", { value: String(n), text: `${n} ${SEV[n]}` }));
  $("ni-sev").value = "4";

  // Filtros de eventos
  $("form-filtros-eventos").addEventListener("submit", (ev) => { ev.preventDefault(); paginaEventos = 0; cargarEventos(); });
  $("btn-limpiar").addEventListener("click", () => { $("form-filtros-eventos").reset(); paginaEventos = 0; cargarEventos(); });
  $("pag-ant").addEventListener("click", () => { if (paginaEventos > 0) { paginaEventos--; cargarEventos(); } });
  $("pag-sig").addEventListener("click", () => { paginaEventos++; cargarEventos(); });

  // Incidentes
  $("fi-estado").addEventListener("change", cargarIncidentes);
  $("btn-nuevo-inc").addEventListener("click", () => abrirNuevoIncidente());
  $("ni-cancelar").addEventListener("click", () => $("dlg-nuevo-inc").close());
  $("di-cerrar").addEventListener("click", () => $("dlg-detalle-inc").close());
  $("form-nuevo-inc").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const cuerpo = { titulo: $("ni-titulo").value.trim(), severidad: Number($("ni-sev").value), evento_ids: [] };
    const desc = $("ni-desc").value.trim();
    if (desc) cuerpo.descripcion = desc;
    if ($("ni-equipo").value) cuerpo.dispositivo_id = Number($("ni-equipo").value);
    const asig = $("ni-asig").value.trim();
    if (asig) cuerpo.asignado_a = asig;
    if ($("ni-evento").value) cuerpo.evento_ids = [Number($("ni-evento").value)];
    try {
      const inc = await api("/api/incidentes", { method: "POST", body: JSON.stringify(cuerpo) });
      $("dlg-nuevo-inc").close();
      avisar(`Incidente #${inc.id} creado`);
      refrescarVistaActual();
    } catch (e) {
      avisar(e.message, "error");
    }
  });

  // Inventario
  $("d-cancelar").addEventListener("click", limpiarFormDisp);
  $("form-disp").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = leerFormDisp();
    try {
      if (dispEditando) {
        const cambios = {};
        for (const [k, v] of Object.entries(datos)) if (v !== dispEditando[k]) cambios[k] = v;
        if (!Object.keys(cambios).length) return avisar("No hay cambios que guardar", "error");
        await api(`/api/dispositivos/${dispEditando.id}`, { method: "PATCH", body: JSON.stringify(cambios) });
        avisar("Equipo actualizado");
      } else {
        await api("/api/dispositivos", { method: "POST", body: JSON.stringify(datos) });
        avisar("Equipo creado");
      }
      limpiarFormDisp();
      await cargarInventario();
    } catch (e) {
      avisar(e.message, "error");
    }
  });

  cargarDispositivos().catch(() => {});
  mostrarVista("dashboard");
}

iniciar();