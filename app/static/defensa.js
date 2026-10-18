"use strict";
/* Vista "Defensa IA" (v0.2.0): política resumida y flujo de acciones propuestas.
   Se carga DESPUÉS de app.js y reutiliza sus utilidades (el, $, api, avisar, badge,
   renderTabla, fmtFecha, abrirDialogo, dispositivos, cargarDispositivos, CARGADORES).
   REGLA DE ORO: todo texto que viene de la API (motivo, parámetros, historial) se
   muestra con textContent; nunca con innerHTML. Las reglas las aplica el BACKEND:
   esta pantalla solo las hace visibles. */

const FLUJO = ["Evento detectado", "Validación", "Propuesta", "Revisión humana", "Aprobación",
  "Ejecución autorizada", "Verificación", "Auditoría"];
const defensaEstado = { catalogo: [] };

function revisorActual() { return $("def-revisor").value.trim(); }

async function accionPaso(acc, paso, cuerpo) {
  try {
    await api(`/api/acciones/${acc.id}/${paso}`, { method: "POST", body: cuerpo ? JSON.stringify(cuerpo) : undefined });
    avisar(`Acción #${acc.id}: paso «${paso}» completado`);
  } catch (e) {
    avisar(`Acción #${acc.id}: ${e.message}`, "error");    // p. ej. separación de funciones
  }
  await cargarDefensa();
}

function botonesAccion(acc) {
  const b = (texto, fn, clase = "mini") => el("button", { type: "button", class: clase, text: texto, onclick: fn });
  const rev = () => ({ revisado_por: revisorActual() });
  const lista = [b("Historial", () => verAccion(acc.id), "mini secundario")];
  if (acc.estado === "propuesta") lista.push(b("Iniciar revisión", () => accionPaso(acc, "revisar", rev())));
  if (acc.estado === "en_revision") {
    lista.push(b("Aprobar", () => accionPaso(acc, "decidir", { ...rev(), decision: "aprobar" })));
    lista.push(b("Rechazar", () => accionPaso(acc, "decidir", { ...rev(), decision: "rechazar" }), "mini peligro"));
  }
  if (acc.estado === "aprobada") lista.push(b("Ejecutar (simulado)", () => accionPaso(acc, "ejecutar")));
  if (acc.estado === "ejecutada") lista.push(b("Verificar", () => accionPaso(acc, "verificar")));
  return el("div", { class: "botones" }, ...lista);
}

async function verAccion(id) {
  try {
    const acc = await api(`/api/acciones/${id}`);
    const tabla = el("table");
    renderTabla(tabla, [
      { titulo: "Fecha", celda: (h) => fmtFecha(h.fecha) },
      { titulo: "Actor", celda: (h) => `${h.actor} (${h.tipo_actor})` },
      { titulo: "Paso", celda: (h) => h.accion },
      { titulo: "Detalle", celda: (h) => el("div", { class: "mensaje", text: h.detalle || "" }) },
    ], acc.historial, { vacio: "Sin historial" });
    $("detalle-inc").replaceChildren(
      el("h3", { text: `Acción #${acc.id}: ${acc.accion}` }),
      el("p", {}, badge(acc.estado.replace("_", " "), "acc-" + acc.estado)),
      el("p", { class: "mensaje", text: "Parámetros: " + JSON.stringify(acc.parametros) }),
      el("p", { class: "mensaje", text: "Motivo (dato no confiable): " + (acc.motivo || "(sin motivo)") }),
      el("h4", { text: "Historial (auditoría)" }), el("div", { class: "scroll" }, tabla));
    abrirDialogo($("dlg-detalle-inc"));
  } catch (e) {
    avisar(e.message, "error");
  }
}

async function cargarDefensa() {
  try {
    await cargarDispositivos();
    if (!defensaEstado.catalogo.length) {
      defensaEstado.catalogo = await api("/api/acciones/catalogo");
      $("def-accion").replaceChildren(...defensaEstado.catalogo.map((a) =>
        el("option", { value: a.accion, text: a.accion, title: a.descripcion })));
      actualizarEjemplo();
    }
    $("def-disp").replaceChildren(...dispositivos.map((d) => el("option", { value: String(d.id), text: `${d.nombre} (${d.estado})` })));
    const filtro = $("def-filtro").value;
    const filas = await api("/api/acciones" + (filtro ? "?estado=" + encodeURIComponent(filtro) : ""));
    renderTabla($("tabla-acciones"), [
      { titulo: "#", celda: (a) => String(a.id) },
      { titulo: "Acción", celda: (a) => a.accion },
      { titulo: "Parámetros", celda: (a) => el("div", { class: "mensaje", text: JSON.stringify(a.parametros) }) },
      { titulo: "Propuesta por", celda: (a) => a.propuesto_por },
      { titulo: "Estado", celda: (a) => badge(a.estado.replace("_", " "), "acc-" + a.estado) },
      { titulo: "Revisor", celda: (a) => a.revisado_por || "-" },
      { titulo: "Pasos", celda: botonesAccion },
    ], filas, { vacio: "No hay acciones propuestas" });
  } catch (e) {
    avisar("No se pudieron cargar las acciones: " + e.message, "error");
  }
}

function actualizarEjemplo() {
  const a = defensaEstado.catalogo.find((x) => x.accion === $("def-accion").value);
  const esIncidente = a && a.accion === "crear_incidente";
  $("def-campos-inc").classList.toggle("oculto", !esIncidente);
  $("def-descripcion").textContent = a ? `${a.descripcion} Riesgo: ${a.riesgo}.` : "";
}

function construirParametros() {
  const accion = $("def-accion").value;
  const params = {};
  if ($("def-disp").value) params.dispositivo_id = Number($("def-disp").value);
  if (accion === "crear_incidente") {
    params.titulo = $("def-titulo").value.trim();
    params.severidad = Number($("def-sev").value);
  }
  return params;
}

async function proponerAccion(ev) {
  ev.preventDefault();
  const cuerpo = {
    accion: $("def-accion").value,
    parametros: construirParametros(),
    propuesto_por: $("def-proponente").value.trim(),
    tipo_actor: $("def-tipo").value,
  };
  const motivo = $("def-motivo").value.trim();
  if (motivo) cuerpo.motivo = motivo;
  try {
    const a = await api("/api/acciones", { method: "POST", body: JSON.stringify(cuerpo) });
    avisar(`Acción #${a.id} propuesta: espera revisión humana (todavía no cambió nada)`);
  } catch (e) {
    avisar(e.message, "error");
  }
  await cargarDefensa();
}

function iniciarDefensa() {
  CARGADORES.defensa = cargarDefensa;
  $("flujo-pasos").replaceChildren(...FLUJO.map((p, i) =>
    el("li", { text: p, class: [3, 4].includes(i) ? "paso-humano" : "" })));
  for (let n = 0; n <= 7; n++) $("def-sev").append(el("option", { value: String(n), text: `${n} ${SEV[n]}` }));
  $("def-sev").value = "3";
  $("def-accion").addEventListener("change", actualizarEjemplo);
  $("def-filtro").addEventListener("change", cargarDefensa);
  $("form-def").addEventListener("submit", proponerAccion);
}

iniciarDefensa();
