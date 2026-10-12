"use strict";
/* Vistas Configuraciones y Consola (v0.2.0).
   Se carga DESPUÉS de app.js y reutiliza sus utilidades (el, $, api, avisar, SEV,
   dispositivos, cargarDispositivos, CARGADORES).
   REGLA DE ORO: todo texto que viene de la API se muestra con textContent o nodos
   de texto; nunca con innerHTML. */

const FACILITIES_LOCAL = ["local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7"];

// Ejemplos por marca: los primeros son permitidos y los últimos se bloquean.
const EJEMPLOS = {
  Cisco: ["help", "show version", "show logging", "configure terminal", "reload", "show running-config"],
  Fortinet: ["help", "get system status", "execute log display", "config system global", "execute reboot", "show full-configuration"],
  Huawei: ["help", "display version", "display logbuffer", "system-view", "reboot", "display current-configuration"],
  Otro: ["help", "show version", "show logging", "configure terminal"],
};

const consolaEstado = { historial: [], pos: 0, listo: false };

/* ---------------- Configuraciones ---------------- */

async function cargarConfiguraciones() {
  try {
    await cargarDispositivos();
  } catch (e) {
    avisar("No se pudieron cargar los equipos: " + e.message, "error");
  }
  const sel = $("cfg-equipo");
  const actual = sel.value;
  sel.replaceChildren(
    el("option", { value: "", text: "(genérico, sin equipo)" }),
    ...dispositivos.filter((d) => d.marca !== "Otro")
      .map((d) => el("option", { value: String(d.id), text: `${d.nombre} (${d.marca})` })));
  sel.value = actual;
}

async function generarConfiguracion(ev) {
  ev.preventDefault();
  const cuerpo = {
    marca: $("cfg-marca").value,
    colector_ip: $("cfg-colector").value.trim(),
    puerto: Number($("cfg-puerto").value),
    protocolo: $("cfg-proto").value,
    severidad_max: Number($("cfg-sev").value),
    facility: $("cfg-facility").value,
  };
  const ntp = $("cfg-ntp").value.trim();
  if (ntp) cuerpo.ntp_ip = ntp;
  if ($("cfg-equipo").value) cuerpo.dispositivo_id = Number($("cfg-equipo").value);
  try {
    const r = await api("/api/configuraciones/syslog", { method: "POST", body: JSON.stringify(cuerpo) });
    $("cfg-titulo").textContent = `Configuración ${r.marca}` + (r.equipo ? ` para ${r.equipo}` : " (genérica)");
    $("cfg-salida").textContent = r.configuracion;
    $("cfg-verif").replaceChildren(...r.verificacion.map((v) =>
      el("li", {}, el("code", { text: v.comando }), " → " + v.esperado)));
    avisar("Configuración generada (solo texto: no se aplicó a ningún equipo)");
  } catch (e) {
    avisar(e.message, "error");
  }
}

async function copiarConfiguracion() {
  try {
    await navigator.clipboard.writeText($("cfg-salida").textContent);
    avisar("Configuración copiada al portapapeles");
  } catch (_) {
    avisar("No se pudo copiar: selecciona el texto y usa Ctrl+C", "error");
  }
}

/* ---------------- Consola simulada ---------------- */

function promptDe(d) {
  if (d.marca === "Cisco") return `${d.nombre}#`;
  if (d.marca === "Fortinet") return `${d.nombre} #`;
  if (d.marca === "Huawei") return `<${d.nombre}>`;
  return `${d.nombre}>`;
}

function dispositivoConsola() {
  return dispositivos.find((x) => String(x.id) === $("con-equipo").value) || null;
}

function imprimir(texto, clase = "") {
  const caja = $("con-salida");
  caja.append(el("div", { class: "con-linea " + clase, text: texto }));   // texto plano
  caja.scrollTop = caja.scrollHeight;
}

function pintarEjemplos() {
  const d = dispositivoConsola();
  $("con-ejemplos").replaceChildren(...(d ? EJEMPLOS[d.marca] || EJEMPLOS.Otro : []).map((c) =>
    el("button", { type: "button", class: "mini secundario", text: c, onclick: () => enviarComando(c) })));
  $("con-prompt").textContent = d ? promptDe(d) : "";
}

function alCambiarEquipo() {
  const d = dispositivoConsola();
  pintarEjemplos();
  if (d) imprimir(`Conectado a ${d.nombre} (${d.ip}) - SESIÓN SIMULADA. Escribe help.`, "con-info");
}

async function cargarConsola() {
  try {
    await cargarDispositivos();
  } catch (e) {
    return avisar("No se pudieron cargar los equipos: " + e.message, "error");
  }
  const sel = $("con-equipo");
  const actual = sel.value;
  sel.replaceChildren(...dispositivos.filter((d) => d.estado !== "inactivo")
    .map((d) => el("option", { value: String(d.id), text: `${d.nombre} (${d.marca})` })));
  if (actual) sel.value = actual;
  if (!consolaEstado.listo) {
    consolaEstado.listo = true;
    imprimir("CONSOLA SIMULADA - SOLO LECTURA. No se conecta a ningún equipo.", "con-info");
    alCambiarEquipo();
  } else {
    pintarEjemplos();
  }
  $("con-entrada").focus();
}

async function enviarComando(texto) {
  const d = dispositivoConsola();
  if (!d) return avisar("Selecciona un equipo", "error");
  imprimir(`${promptDe(d)} ${texto}`, "con-cmd");
  if (["clear", "cls"].includes(texto.trim().toLowerCase())) {
    $("con-salida").replaceChildren();
    return;
  }
  consolaEstado.historial.push(texto);
  consolaEstado.pos = consolaEstado.historial.length;
  try {
    const r = await api("/api/consola/ejecutar", {
      method: "POST",
      body: JSON.stringify({ dispositivo_id: d.id, comando: texto }),
    });
    imprimir(r.salida, r.permitido ? "con-ok" : "con-bloq");
  } catch (e) {
    imprimir("% Error: " + e.message, "con-bloq");
  }
}

/* ---------------- arranque ---------------- */

function iniciarHerramientas() {
  CARGADORES.configuraciones = cargarConfiguraciones;
  CARGADORES.consola = cargarConsola;

  for (let n = 0; n <= 7; n++) $("cfg-sev").append(el("option", { value: String(n), text: `${n} ${SEV[n]}` }));
  $("cfg-sev").value = "6";
  for (const f of FACILITIES_LOCAL) $("cfg-facility").append(el("option", { value: f, text: f }));
  $("cfg-facility").value = "local6";

  $("cfg-equipo").addEventListener("change", () => {
    const d = dispositivos.find((x) => String(x.id) === $("cfg-equipo").value);
    if (d && d.marca !== "Otro") $("cfg-marca").value = d.marca;    // la marca sigue al equipo
  });
  $("form-cfg").addEventListener("submit", generarConfiguracion);
  $("cfg-copiar").addEventListener("click", copiarConfiguracion);

  $("con-equipo").addEventListener("change", alCambiarEquipo);
  $("con-limpiar").addEventListener("click", () => $("con-salida").replaceChildren());
  $("con-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const texto = $("con-entrada").value;
    if (!texto.trim()) return;
    $("con-entrada").value = "";
    enviarComando(texto);
  });
  $("con-entrada").addEventListener("keydown", (ev) => {      // historial con flechas
    const h = consolaEstado.historial;
    if (ev.key === "ArrowUp" && h.length) {
      consolaEstado.pos = Math.max(0, consolaEstado.pos - 1);
      $("con-entrada").value = h[consolaEstado.pos];
      ev.preventDefault();
    } else if (ev.key === "ArrowDown" && h.length) {
      consolaEstado.pos = Math.min(h.length, consolaEstado.pos + 1);
      $("con-entrada").value = h[consolaEstado.pos] || "";
      ev.preventDefault();
    }
  });
}

iniciarHerramientas();