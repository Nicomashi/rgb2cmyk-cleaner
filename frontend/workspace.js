import { layoutProbeReadouts } from "./probe-layout.js";
import { createI18n, bindStaticTranslations } from "./i18n.js";
let languageStorage;
try { languageStorage = window.localStorage; } catch { /* Storage may be disabled. */ }
const i18n = createI18n(languageStorage);
const t = i18n.t, translateMessage = i18n.translateMessage;
const $ = (id) => document.getElementById(id);
// Editor shortcuts (including repeated Space) are not keyboard focus navigation.
document.addEventListener("pointerdown", () => document.documentElement.classList.add("pointer-input"), true);
document.addEventListener("keydown", (e) => {
  if (["Tab", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(e.key))
    document.documentElement.classList.remove("pointer-input");
  else if (e.code === "Space" && e.target.closest?.("#viewport"))
    document.documentElement.classList.add("pointer-input");
}, true);
const workspaceId = document.querySelector('meta[name="workspace-id"]').content;
const defaults = {
  strength: 100,
  compensation: 0.82,
  neutral_protection: 100,
  max_k: 100,
  tac: 300,
  smooth_ties: true,
};
let ready = false,
  source = null,
  current = null,
  material = 0,
  revision = 0,
  busy = false,
  pending = false,
  loading = false,
  processTimer,
  progressTimer;
let requestController = null,
  uploadRequest = null,
  retryAction = null,
  sourceName = "",
  profileName = "FOGRA39";
let zoom = 1,
  offsetX = 0,
  offsetY = 0,
  split = 0.5,
  fitMode = true,
  drag = null,
  spaceDown = false;
let probes = [],
  nextProbe = 1,
  live = null,
  sampleBusy = false,
  samplePending = false,
  sampleTimer;
let fullJob = null,
  fullBusy = false,
  jobTimer,
  exportDownloaded = false;
let noticeMessage = "", noticeStale = false, progressTitle = "Открываем изображение";
const icon = (name) => `<sp-icon-${name} slot="icon"></sp-icon-${name}>`;
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function api(path, options = {}) {
  const r = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: { ...options.headers, "X-Workspace": workspaceId },
  });
  if (!r.ok) {
    let data;
    try {
      data = await r.json();
    } catch {}
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `Ошибка запроса (${r.status})`,
    );
  }
  return r.status === 204 ? null : r.json();
}
const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
function notice(message, retry = null) {
  noticeMessage = message;
  const stale = noticeStale = message.includes("Страница устарела") || message.includes("Обновите страницу для новой рабочей сессии");
  $("noticeText").textContent = translateMessage(message);
  $("notice").hidden = false;
  retryAction = stale ? () => location.reload() : retry;
  $("retry").textContent = t(stale ? "Обновить страницу" : "Повторить");
  $("retry").hidden = !retryAction;
}
function clearNotice() {
  $("notice").hidden = true;
  noticeMessage = "";
  retryAction = null;
}
$("dismissNotice").onclick = clearNotice;
$("retry").onclick = () => {
  const fn = retryAction;
  clearNotice();
  fn?.();
};
function settings() {
  const s = {};
  for (const k in defaults) {
    if (k === "smooth_ties") s[k] = $(k).checked;
    else {
      const v = Number($(k).value);
      const limits = {
        strength: [0, 100],
        compensation: [0, 2],
        neutral_protection: [0, 100],
        max_k: [0, 100],
        tac: [0, 400],
      };
      if (!Number.isFinite(v) || v < limits[k][0] || v > limits[k][1])
        throw new Error("Проверьте значения настроек.");
      s[k] = v;
    }
  }
  s.strength /= 100;
  s.neutral_protection /= 100;
  return s;
}
function syncButtons() {
  const disabled = !ready || loading;
  $("openFile").disabled = disabled;
  $("emptyOpen").disabled = disabled;
  $("demo").disabled = disabled;
  $("export").disabled = disabled || !current || busy || pending || fullBusy;
  $("exportPng").disabled = !current || busy || pending || loading;
  $("exportReport").disabled = $("exportPng").disabled;
  $("clearSamples").disabled = !probes.length || loading;
  for (const k in defaults) $(k).disabled = loading;
  for (const k of ["strength", "compensation", "neutral_protection"])
    $(k + "Number").disabled = loading;
  $("profile").disabled = loading;
  $("preset").disabled = loading;
}
function globalProgress(show, title = "Открываем изображение", percent = null) {
  loading = show;
  $("globalProgress").hidden = !show;
  progressTitle = title;
  $("globalTitle").textContent = t(title);
  $("globalBar").indeterminate = percent === null;
  if (percent !== null) $("globalBar").progress = percent;
  $("globalDetail").textContent =
    percent === null ? "" : `${Math.round(percent)}%`;
  $("app").querySelector("main").inert = show;
  $("app").querySelector("header").inert = show;
  if (show) $("globalProgress").focus({ preventScroll: true });
  syncButtons();
}
function previewProgress(show) {
  clearTimeout(progressTimer);
  if (show) {
    progressTimer = setTimeout(() => {
      if (!loading && (busy || pending)) $("previewProgress").hidden = false;
    }, 180);
  } else $("previewProgress").hidden = true;
}
function applyDefaults() {
  for (const [key, value] of Object.entries(defaults)) {
    if (typeof value === "boolean") $(key).checked = value;
    else $(key).value = value;
    if ($(key + "Number")) $(key + "Number").value = value;
  }
  $("preset").value = "default";
}
for (const key of ["strength", "compensation", "neutral_protection"]) {
  const slider = $(key),
    number = $(key + "Number");
  slider.addEventListener("input", () => {
    number.value = slider.value;
    changed();
  });
  slider.addEventListener("change", () => {
    number.value = slider.value;
  });
  number.addEventListener("change", () => {
    slider.value = number.value;
    changed();
  });
}
for (const key of ["max_k", "tac", "smooth_ties"])
  $(key).addEventListener("change", changed);
function changed() {
  try {
    settings();
  } catch (e) {
    notice(e.message);
    return;
  }
  $("preset").value = "custom";
  schedule();
}
function schedule() {
  revision++;
  pending = !!source;
  clearTimeout(processTimer);
  if (!source || !ready) return;

  markSamplesStale();
  syncButtons();
  previewProgress(true);
  processTimer = setTimeout(process, 180);
}
function decode(src) {
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve();
    im.onerror = () => reject(new Error("Не удалось показать изображение."));
    im.src = src;
  });
}
async function process() {
  if (!ready || !source) return;
  if (busy) {
    pending = true;
    return;
  }
  const m = material,
    r = revision;
  let parameters;
  try {
    parameters = settings();
  } catch (e) {
    pending = false;
    previewProgress(false);
    notice(e.message);
    syncButtons();
    return;
  }
  busy = true;
  pending = false;
  syncButtons();
  const controller = new AbortController();
  requestController = controller;
  try {
    const data = await api("/api/process", {
      ...json({
        source: source.id,
        profile: $("profile").value,
        settings: parameters,
        channel: $("channel").value,
        before_mode: $("beforeMode").value,
      }),
      signal: controller.signal,
    });
    if (m !== material || r !== revision) return;
    await Promise.all([decode(data.before), decode(data.after)]);
    if (m !== material || r !== revision) return;
    const first = !current;
    current = data;
    $("before").src = data.before;
    $("after").src = data.after;
    $("empty").hidden = true;
    for (const id of ["scene", "divider", "zoomBar"]) $(id).hidden = false;
    renderMetadata();
    if (first || fitMode) fit();
    else renderView();
    renderMarkers();
    renderLive();
    clearNotice();
    if (loading) globalProgress(false);
    refreshSamples();
  } catch (e) {
    if (m === material && e.name !== "AbortError") {
      pending = false;
      globalProgress(false);
      notice(e.message, () => schedule());
    }
  } finally {
    busy = false;
    if (requestController === controller) requestController = null;
    if (m === material) {
      if (r !== revision && source) pending = true;
      if (pending) {
        clearTimeout(processTimer);
        process();
      } else {
        previewProgress(false);
        syncButtons();
        refreshSamples();
      }
    } else if (pending && source) process();
  }
}
function renderMetadata() {
  const data = current;
  if (!data) {
    $("fileTooltip").textContent = t("PNG, JPEG, TIFF · 8 бит");
    $("beforeMode").querySelector('[value="source"]').textContent = t("Исходник · RGB");
    return;
  }
  $("before").alt = translateMessage(data.left_label);
  $("after").alt = translateMessage(data.right_label);
  $("metadata").textContent = `${data.original_size.join(" × ")} · ${data.source_profile}`;
  $("resultMeta").textContent = `${data.source_mode} → CMYK`;
  $("beforeMode").querySelector('[value="source"]').textContent = t("Исходник · {mode}", {mode: data.source_mode});
  const details = [
    t("Превью: {width} × {height}. Экспорт: {size}.", {width: data.width, height: data.height, size: data.original_size.join(" × ")}),
    ...data.notes.map(note => translateMessage(note)),
    t("Изменено: {changed}%. Макс. TAC: {before}% → {after}%.", {changed: data.stats.changed_pct, before: data.stats.tac_before, after: data.stats.tac_after}),
  ];
  if (data.stats.tac_exceeded_pct)
    details.push(t("Выше лимита TAC: {percent}% пикселей. Лимит ограничивает добавление K.", {percent: data.stats.tac_exceeded_pct}));
  $("fileTooltip").textContent = details.join(" ");
}
function renderExportLabels() {
  $("exportLabel").textContent = t(fullBusy ? "Подготовка TIFF" : "Скачать TIFF");
  if (fullBusy) $("exportText").textContent = fullJob?.status === "cancelling"
    ? t("Отмена…") : fullJob ? `TIFF · ${fullJob.progress}%` : t("Подготовка TIFF");
}
function clearMaterial() {
  material++;
  revision++;

  clearTimeout(processTimer);
  clearTimeout(sampleTimer);
  clearTimeout(jobTimer);
  clearTimeout(progressTimer);
  requestController?.abort();
  uploadRequest?.abort();
  pending = false;
  source = null;
  current = null;
  probes = [];
  live = null;
  nextProbe = 1;
  fullJob = null;
  fullBusy = false;
  exportDownloaded = false;
  fitMode = true;
  split = 0.5;
  drag = null;
  samplePending = false;
  $("filename").textContent = t("Файл не открыт");
  $("filename").removeAttribute("title");
  renderMetadata();
  $("metadata").textContent = "—";
  $("resultMeta").textContent = "";
  $("before").removeAttribute("src");
  $("after").removeAttribute("src");
  $("empty").hidden = false;
  for (const id of [
    "scene",
    "divider",
    "zoomBar",
    "previewProgress",
    "exportState",
  ])
    $(id).hidden = true;
  $("markers").replaceChildren();
  $("sampleList").replaceChildren();
  $("exportLabel").textContent = t("Скачать TIFF");
  renderLive();
  syncButtons();
  clearNotice();
}
function setSource(item) {
  source = item;
  sourceName = item.name;
  $("filename").textContent = item.name;
  $("filename").title = item.name;
  revision++;
  pending = true;
  process();
}
function xhrUpload(file, path) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    uploadRequest = xhr;
    xhr.open("POST", path);
    xhr.setRequestHeader("X-Workspace", workspaceId);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        globalProgress(true, "Загружаем файл", (e.loaded / e.total) * 100);
    };
    xhr.upload.onload = () => globalProgress(true, "Читаем изображение");
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else
        reject(
          new Error(
            typeof xhr.response?.detail === "string"
              ? xhr.response.detail
              : "Не удалось открыть файл.",
          ),
        );
    };
    xhr.onerror = () =>
      reject(new Error("Сервер недоступен. Проверьте соединение."));
    xhr.onabort = () => reject(new DOMException("Отменено", "AbortError"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
async function openFile(file) {
  if (!file || loading || !ready) return;
  clearMaterial();
  const m = material;
  globalProgress(true, "Загружаем файл");
  try {
    const item = await xhrUpload(file, "/api/upload");
    if (m !== material) return;
    uploadRequest = null;
    globalProgress(true, "Готовим превью");
    setSource(item);
  } catch (e) {
    if (m === material) {
      globalProgress(false);
      if (e.name !== "AbortError") notice(e.message, () => openFile(file));
    }
  } finally {
    if (m === material) uploadRequest = null;
    $("file").value = "";
  }
}
$("openFile").onclick = $("emptyOpen").onclick = () => $("file").click();
$("file").onchange = () => openFile($("file").files[0]);
$("demo").onclick = async () => {
  if (!ready || loading) return;
  clearMaterial();
  const m = material;
  globalProgress(true, "Открываем демо");
  const controller = new AbortController();
  requestController = controller;
  try {
    const item = await api("/api/demo", {
      method: "POST",
      signal: controller.signal,
    });
    if (m === material) {
      globalProgress(true, "Готовим превью");
      setSource(item);
    }
  } catch (e) {
    if (m === material) {
      globalProgress(false);
      if (e.name !== "AbortError") notice(e.message, () => $("demo").click());
    }
  }
};
$("cancelUpload").onclick = async () => {
  clearMaterial();
  globalProgress(true, "Отменяем");
  $("cancelUpload").disabled = true;
  try {
    await api("/api/materials/clear", { method: "POST" });
  } catch (e) {
    notice(e.message);
  } finally {
    globalProgress(false);
    $("cancelUpload").disabled = false;
    $("openFile").focus();
  }
};
let oldProfile = "source";
$("profile").onchange = () => {
  if ($("profile").value === "upload") {
    $("profile").value = oldProfile;
    $("icc").click();
  } else {
    oldProfile = $("profile").value;
    schedule();
  }
};
$("icc").onchange = async () => {
  const file = $("icc").files[0];
  if (!file) return;
  globalProgress(true, "Читаем ICC");
  const m = material;
  try {
    const form = new FormData();
    form.append("file", file);
    const item = await api("/api/profile", { method: "POST", body: form });
    if (m !== material) return;
    const option = new Option(item.name, item.id);
    $("profile").add(option, $("profile").options.length - 1);
    $("profile").value = item.id;
    oldProfile = item.id;
    profileName = item.name;
    globalProgress(false);
    schedule();
  } catch (e) {
    if (m === material) {
      globalProgress(false);
      notice(e.message);
    }
  }
  $("icc").value = "";
};
$("channel").onchange = () => {
  $("beforeMode").disabled = $("channel").value !== "color";
  schedule();
};
$("beforeMode").onchange = schedule;
function download(url, name) {
  const a = document.createElement("a");
  a.href = url;
  if (name) a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
}
$("preset").onchange = () => {
  const choice = $("preset").value;
  if (choice === "default") {
    applyDefaults();
    schedule();
  } else if (choice === "load") {
    $("presetFile").click();
    $("preset").value = "custom";
  } else if (choice === "save") {
    const blob = new Blob(
      [
        JSON.stringify(
          { version: 1, mode: "A", settings: settings() },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    download(url, "cmyk-clean-preset.json");
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("preset").value = "custom";
  }
};
$("presetFile").onchange = async () => {
  try {
    const file = $("presetFile").files[0];
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); }
    catch { throw new Error("Некорректный пресет."); }
    if (!data || typeof data !== "object" || !data.settings)
      throw new Error("Некорректный пресет.");
    if (data.version !== 1 || data.mode !== "A")
      throw new Error("Нужен пресет режима A, версия 1.");
    const s = data.settings;
    for (const [k, [lo, hi]] of Object.entries({
      strength: [0, 1],
      compensation: [0, 2],
      neutral_protection: [0, 1],
      max_k: [0, 100],
      tac: [0, 400],
    }))
      if (
        typeof s[k] !== "number" ||
        !Number.isFinite(s[k]) ||
        s[k] < lo ||
        s[k] > hi
      )
        throw new Error("Некорректный пресет.");
    if (typeof s.smooth_ties !== "boolean")
      throw new Error("Некорректный пресет.");
    for (const k in defaults) {
      if (k === "smooth_ties") $(k).checked = s[k];
      else
        $(k).value =
          s[k] * (["strength", "neutral_protection"].includes(k) ? 100 : 1);
      if ($(k + "Number")) $(k + "Number").value = $(k).value;
    }
    changed();
  } catch (e) {
    notice(e.message);
  }
  $("presetFile").value = "";
};
// One transform, shared by both images and all original-pixel coordinates.
function renderView() {
  if (!current) return;
  const [w, h] = current.original_size;
  $("scene").style.width = w + "px";
  $("scene").style.height = h + "px";
  $("scene").style.transform =
    `translate(${offsetX}px,${offsetY}px) scale(${zoom})`;
  const edge = $("viewport").clientWidth * split;
  const clip = Math.max(
    0,
    Math.min(100, ((edge - offsetX) / (w * zoom)) * 100),
  );
  $("after").style.clipPath = `inset(0 0 0 ${clip}%)`;
  $("divider").style.left = split * 100 + "%";
  $("divider").setAttribute("aria-valuenow", String(Math.round(split * 100)));
  $("zoomValue").value = Math.round(zoom * 100);
  for (const marker of $("markers").children)
    marker.style.transform = `translate(-50%,-50%) scale(${1 / zoom})`;
  renderMarkerReadouts();
}
function fit() {
  if (!current) return;
  const v = $("viewport"),
    [w, h] = current.original_size;
  zoom = Math.min((v.clientWidth - 32) / w, (v.clientHeight - 32) / h, 1);
  zoom = Math.max(0.001, zoom);
  offsetX = (v.clientWidth - w * zoom) / 2;
  offsetY = (v.clientHeight - h * zoom) / 2;
  fitMode = true;
  renderView();
}
function setZoom(
  value,
  x = $("viewport").clientWidth / 2,
  y = $("viewport").clientHeight / 2,
) {
  if (!current) return;
  const next = Math.max(0.01, Math.min(8, value));
  offsetX = x - ((x - offsetX) * next) / zoom;
  offsetY = y - ((y - offsetY) * next) / zoom;
  zoom = next;
  fitMode = false;
  renderView();
}
$("zoomIn").onclick = () => setZoom(zoom * 1.25);
$("zoomOut").onclick = () => setZoom(zoom / 1.25);
$("zoomValue").onchange = () => {
  const value = Number($("zoomValue").value);
  if (Number.isFinite(value) && value > 0) setZoom(value / 100);
  else renderView();
};
$("fit").onclick = fit;
$("actual").onclick = () => setZoom(1);
$("hand").addEventListener("change", () =>
  $("viewport").classList.toggle("hand", $("hand").selected),
);
new ResizeObserver(() => {
  if (current) {
    if (fitMode) fit();
    else renderView();
  }
}).observe($("viewport"));
function localPoint(e) {
  const r = $("viewport").getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
function imagePoint(e) {
  if (!current) return null;
  const p = localPoint(e),
    x = Math.floor((p.x - offsetX) / zoom),
    y = Math.floor((p.y - offsetY) / zoom);
  return x >= 0 &&
    y >= 0 &&
    x < current.original_size[0] &&
    y < current.original_size[1]
    ? { x, y }
    : null;
}
function clampPoint(e) {
  const p = localPoint(e);
  return {
    x: Math.max(
      0,
      Math.min(
        current.original_size[0] - 1,
        Math.floor((p.x - offsetX) / zoom),
      ),
    ),
    y: Math.max(
      0,
      Math.min(
        current.original_size[1] - 1,
        Math.floor((p.y - offsetY) / zoom),
      ),
    ),
  };
}
$("viewport").addEventListener(
  "wheel",
  (e) => {
    if (!current || e.target.closest(".zoom-bar")) return;
    e.preventDefault();
    const p = localPoint(e);
    setZoom(zoom * Math.exp(-e.deltaY * 0.002), p.x, p.y);
  },
  { passive: false },
);
$("divider").addEventListener("pointerdown", (e) => {
  if (!current || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  drag = { type: "split", pointer: e.pointerId };
  $("divider").setPointerCapture(e.pointerId);
  $("divider").focus({ preventScroll: true });
});
$("divider").addEventListener("pointermove", (e) => {
  if (drag?.type === "split" && drag.pointer === e.pointerId) {
    split = Math.max(
      0,
      Math.min(1, localPoint(e).x / $("viewport").clientWidth),
    );
    renderView();
  }
});
$("divider").addEventListener("pointerup", endDrag);
$("divider").addEventListener("pointercancel", endDrag);
$("divider").addEventListener("keydown", (e) => {
  const delta = e.shiftKey ? 0.1 : 0.01;
  const choices = {
    ArrowLeft: split - delta,
    ArrowRight: split + delta,
    Home: 0,
    End: 1,
  };
  if (e.key in choices) {
    e.preventDefault();
    split = Math.max(0, Math.min(1, choices[e.key]));
    renderView();
  }
});
$("viewport").addEventListener("pointerdown", (e) => {
  if (
    !current ||
    e.button !== 0 ||
    e.target.closest(".zoom-bar,#notice,.preview-progress")
  )
    return;
  const marker = e.target.closest(".marker");
  if (marker) {
    e.preventDefault();
    drag = {
      type: "probe",
      id: Number(marker.dataset.id),
      pointer: e.pointerId,
    };
    $("viewport").setPointerCapture(e.pointerId);
    return;
  }
  const point = imagePoint(e);
  if (e.shiftKey && point) {
    e.preventDefault();
    pin(point);
    return;
  }
  e.preventDefault();
  const p = localPoint(e);
  drag = {
    type: "pan",
    pointer: e.pointerId,
    x: p.x,
    y: p.y,
    ox: offsetX,
    oy: offsetY,
  };
  $("viewport").classList.add("panning");
  $("viewport").setPointerCapture(e.pointerId);
  $("viewport").focus({ preventScroll: true });
});
$("viewport").addEventListener("pointermove", (e) => {
  if (!current) return;
  if (drag?.pointer === e.pointerId) {
    if (drag.type === "pan") {
      const p = localPoint(e);
      offsetX = drag.ox + p.x - drag.x;
      offsetY = drag.oy + p.y - drag.y;
      fitMode = false;
      renderView();
    } else if (drag.type === "probe") {
      const point = clampPoint(e),
        probe = probes.find((p) => p.id === drag.id);
      if (probe) {
        Object.assign(probe, point);
        probe.data = null;

        renderMarkers();
        renderProbes();
        queueSamples();
      }
    }
    return;
  }
  if (e.target.closest(".zoom-bar,#notice,#divider")) return;
  const point = imagePoint(e);
  if (!point) {
    if (live) {
      live = null;
      renderLive();
    }
    return;
  }
  if (live?.x === point.x && live?.y === point.y) return;
  live = { ...point, data: live?.data };

  renderLive();
  queueSamples();
});
$("viewport").addEventListener("pointerleave", () => {
  if (!drag) {
    live = null;

    renderLive();
  }
});
function endDrag(e) {
  if (!drag || drag.pointer !== e.pointerId) return;
  const was = drag;
  drag = null;
  $("viewport").classList.remove("panning");
  if (e.currentTarget.hasPointerCapture(e.pointerId))
    e.currentTarget.releasePointerCapture(e.pointerId);
  if (was.type === "probe") refreshSamples();
}
$("viewport").addEventListener("pointerup", endDrag);
$("viewport").addEventListener("pointercancel", endDrag);
$("viewport").addEventListener("keydown", (e) => {
  if (e.target.closest("input,select,sp-number-field")) return;
  if (e.key === "0") {
    e.preventDefault();
    fit();
  }
  if (e.key === "1") {
    e.preventDefault();
    setZoom(1);
  }
  if (e.key === "+" || e.key === "=") {
    e.preventDefault();
    setZoom(zoom * 1.25);
  }
  if (e.key === "-") {
    e.preventDefault();
    setZoom(zoom / 1.25);
  }
  if (e.key === " ") {
    e.preventDefault();
    spaceDown = true;
    $("viewport").classList.add("hand");
  }
});
window.addEventListener("keyup", (e) => {
  if (e.key === " ") {
    spaceDown = false;
    $("viewport").classList.toggle("hand", $("hand").selected);
  }
});
window.addEventListener("blur", () => {
  spaceDown = false;
  drag = null;
  $("viewport").classList.remove("panning");
  $("viewport").classList.remove("show-probe-values");
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Alt" && current) {
    e.preventDefault();
    $("viewport").classList.add("show-probe-values");
  }
});
window.addEventListener("keyup", (e) => {
  if (e.key === "Alt") $("viewport").classList.remove("show-probe-values");
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) $("viewport").classList.remove("show-probe-values");
});
function pin(point) {
  if (probes.length >= 32) {
    notice("Максимум 32 пробника. Удалите ненужный.");
    return;
  }
  probes.push({ id: nextProbe++, ...point });

  renderMarkers();
  renderProbes();
  syncButtons();
  refreshSamples();
}
function renderMarkers() {
  if (!current) return;
  $("markers").innerHTML = probes
    .map(
      (p) =>
        `<button class="marker" data-id="${p.id}" aria-label="${escape(t("Пробник {id}. Стрелки — перемещение, Delete — удалить.", {id: p.id}))}" style="left:${p.x + 0.5}px;top:${p.y + 0.5}px;transform:translate(-50%,-50%) scale(${1 / zoom})"><span class="probe-leader" aria-hidden="true"></span>${icon("crosshairs")}<b>${p.id}</b><span class="probe-readout" aria-hidden="true"></span></button>`,
    )
    .join("");
  renderMarkerReadouts();
}
function renderMarkerReadouts() {
  if (!current) return;
  const viewport = $("viewport");
  const points = probes.map(p => ({ id: p.id, x: offsetX + (p.x + 0.5) * zoom, y: offsetY + (p.y + 0.5) * zoom }));
  const vr = viewport.getBoundingClientRect(), zr = $("zoomBar").getBoundingClientRect();
  const positions = new Map(layoutProbeReadouts(points, viewport.clientWidth, viewport.clientHeight,
    [{ x: zr.left - vr.left, y: zr.top - vr.top, width: zr.width, height: zr.height }]).map(r => [r.id, r]));
  for (const p of probes) {
    const label = $("markers").querySelector(`[data-id="${p.id}"] .probe-readout`);
    if (!label) continue;
    const d = p.data;
    const row = (values) => `<span class="probe-numbers">${values.map((v) => `<span>${Math.round(v)}</span>`).join("")}</span>`;
    const html = d
      ? `<span class="probe-color"><i style="background:rgb(${d.swatch_cmyk_before.join(",")})"></i><i style="background:rgb(${d.swatch_after.join(",")})"></i></span><span>${row(d.before)}${row(d.after)}</span>`
      : "—";
    if (label.innerHTML !== html) label.innerHTML = html;
    label.classList.toggle("stale", busy || pending || !d);
    const point = points.find(point => point.id === p.id), rect = positions.get(p.id);
    const leader = label.parentElement.querySelector(".probe-leader");
    label.hidden = leader.hidden = !rect;
    if (!rect) continue;
    label.style.left = `${rect.x - point.x + 19}px`;
    label.style.top = `${rect.y - point.y + 19}px`;
    const dx = Math.max(rect.x, Math.min(point.x, rect.x + rect.width)) - point.x;
    const dy = Math.max(rect.y, Math.min(point.y, rect.y + rect.height)) - point.y;
    const distance = Math.hypot(dx, dy), angle = Math.atan2(dy, dx);
    leader.style.left = `${19 + 20 * Math.cos(angle)}px`;
    leader.style.top = `${19 + 20 * Math.sin(angle)}px`;
    leader.style.width = `${Math.max(0, distance - 20)}px`;
    leader.style.transform = `rotate(${angle}rad)`;
  }
}
$("markers").addEventListener("keydown", (e) => {
  const marker = e.target.closest(".marker");
  if (!marker || !current) return;
  const id = Number(marker.dataset.id),
    p = probes.find((p) => p.id === id);
  if (["Delete", "Backspace"].includes(e.key)) {
    e.preventDefault();
    removeProbe(id);
    return;
  }
  const step = e.shiftKey ? 10 : 1;
  const delta = {
    ArrowLeft: [-step, 0],
    ArrowRight: [step, 0],
    ArrowUp: [0, -step],
    ArrowDown: [0, step],
  }[e.key];
  if (delta) {
    e.preventDefault();
    e.stopPropagation();
    p.x = Math.max(0, Math.min(current.original_size[0] - 1, p.x + delta[0]));
    p.y = Math.max(0, Math.min(current.original_size[1] - 1, p.y + delta[1]));
    p.data = null;

    renderMarkers();
    $("markers").querySelector(`[data-id="${id}"]`)?.focus();
    renderProbes();
    refreshSamples();
  }
});
function sampleHTML(p, isLive = false) {
  const d = p?.data;
  const fmt = (v) =>
    v.map((n) => `<span>${Math.round(n)}</span>`).join("");
  const swatch = d
    ? `<i style="background:rgb(${d.swatch_cmyk_before.join(",")})"></i><i style="background:rgb(${d.swatch_after.join(",")})"></i>`
    : "<i></i>";
  const title = d
    ? `X ${d.x} · Y ${d.y} · TAC ${d.tac}% · ${t("Пиксели оригинала")}`
    : isLive
      ? t("Наведите на изображение")
      : t("Пересчёт");
  return `<span class="sample-id">${isLive ? icon("eyedropper") : p.id}</span><span class="sample-swatch" title="${escape(title)}">${swatch}</span><div class="sample-values"><div><small title="${t("CMYK до очистки, %")}">${t("До")}</small><span class="channel-values">${d ? fmt(d.before) : "—"}</span></div><div><small title="${t("CMYK после очистки, %")}">${t("После")}</small><span class="channel-values">${d ? fmt(d.after) : "—"}</span></div></div>${isLive ? "<span></span>" : `<sp-action-button quiet data-remove="${p.id}" label="${escape(t("Удалить пробник {id}", {id: p.id}))}">${icon("delete")}<sp-tooltip self-managed>${escape(t("Удалить пробник {id}", {id: p.id}))}</sp-tooltip></sp-action-button>`}`;
}
function renderLive() {
  $("liveSample").innerHTML = sampleHTML(live, true);
  $("liveSample").classList.toggle("stale", busy || pending);
}
function renderProbes() {
  renderMarkerReadouts();
  const focused = document.activeElement?.dataset?.remove;
  const html = probes
    .map(
      (p) =>
        `<div class="sample-row${busy || pending ? " stale" : ""}" data-probe="${p.id}">${sampleHTML(p)}</div>`,
    )
    .join("");
  if ($("sampleList").innerHTML !== html) {
    const scrollTop = $("sampleList").scrollTop;
    $("sampleList").innerHTML = html;
    if (focused)
      $("sampleList").querySelector(`[data-remove="${focused}"]`)?.focus({ preventScroll: true });
    $("sampleList").scrollTop = scrollTop;
  }
}
function removeProbe(id) {
  probes = probes.filter((p) => p.id !== id);

  renderMarkers();
  renderProbes();
  syncButtons();
}
$("sampleList").addEventListener("click", (e) => {
  const b = e.target.closest("[data-remove]");
  if (b) removeProbe(Number(b.dataset.remove));
});
$("clearSamples").onclick = () => {
  probes = [];

  renderMarkers();
  renderProbes();
  syncButtons();
};
$("area").onchange = () => {

  for (const p of probes) p.data = null;
  if (live) live.data = null;
  renderLive();
  renderProbes();
  refreshSamples();
};
function markSamplesStale() {
  renderLive();
  renderProbes();
}
function queueSamples() {
  samplePending = true;
  if (!sampleTimer)
    sampleTimer = setTimeout(() => {
      sampleTimer = null;
      refreshSamples();
    }, 100);
}
async function refreshSamples() {
  if (!current || busy || pending || loading) return;
  if (sampleBusy) {
    samplePending = true;
    return;
  }
  const all = [
    ...(live ? [{ ...live, id: "live" }] : []),
    ...probes.map((p) => ({ ...p })),
  ];
  if (!all.length) return;
  sampleBusy = true;
  samplePending = false;
  const m = material,
    token = current.id,
    area = Number($("area").value);
  try {
    const data = await api(
      "/api/samples/" + token,
      json({
        points: all.map(({ x, y }) => ({ x, y })),
        area: Number($("area").value),
      }),
    );
    if (
      m !== material ||
      current?.id !== token ||
      area !== Number($("area").value)
    )
      return;
    all.forEach((old, i) => {
      const target =
        old.id === "live" ? live : probes.find((p) => p.id === old.id);
      if (
        target &&
        (old.id === "live" || (old.x === target.x && old.y === target.y))
      )
        target.data = data.points[i];
    });
    renderLive();
    renderProbes();
  } catch (e) {
    if (m === material && current?.id === token)
      notice("Не удалось получить цвет: " + e.message, refreshSamples);
  } finally {
    sampleBusy = false;
    if (samplePending) queueSamples();
  }
}
// Explicit export, frozen settings for each running job.
function showJob(job) {
  fullJob = job;
  fullBusy = ["queued", "running", "cancelling"].includes(job.status);
  $("exportState").hidden = !fullBusy;
  $("exportProgress").indeterminate = job.status === "queued";
  $("exportProgress").progress = job.progress;
  $("cancelExport").disabled = job.status === "cancelling";
  renderExportLabels();
  if (job.status === "complete" && !exportDownloaded) {
    exportDownloaded = true;
    download(job.download);
  }
  if (job.status === "failed")
    notice(job.error || "Ошибка экспорта", startExport);
  syncButtons();
}
async function pollJob(id, m) {
  try {
    const job = await api("/api/full-export/" + id);
    if (m !== material || fullJob?.id !== id) return;
    showJob(job);
    if (fullBusy) jobTimer = setTimeout(() => pollJob(id, m), 500);
  } catch (e) {
    if (m === material) {
      fullBusy = false;
      $("exportState").hidden = true;
      syncButtons();
      notice(e.message, () => pollJob(id, m));
    }
  }
}
async function startExport() {
  if (!current || busy || pending || fullBusy) return;
  fullBusy = true;
  fullJob = null;
  exportDownloaded = false;
  syncButtons();
  const m = material;
  $("exportState").hidden = false;
  $("exportProgress").indeterminate = true;
  $("exportText").textContent = t("Подготовка TIFF");
  try {
    const job = await api("/api/full-export/" + current.id, { method: "POST" });
    if (m !== material) return;
    showJob(job);
    if (fullBusy) jobTimer = setTimeout(() => pollJob(job.id, m), 300);
  } catch (e) {
    if (m === material) {
      fullBusy = false;
      $("exportState").hidden = true;
      syncButtons();
      notice(e.message, startExport);
    }
  }
}
$("export").onclick = startExport;
$("cancelExport").onclick = async () => {
  if (!fullJob) return;
  const m = material;
  try {
    const job = await api("/api/full-export/" + fullJob.id + "/cancel", {
      method: "POST",
    });
    if (m === material) showJob(job);
  } catch (e) {
    notice(e.message);
  }
};
$("exportPng").onclick = () => {
  if (current) download("/api/export/" + current.id + "?kind=png");
};
$("exportReport").onclick = () => {
  if (current)
    download(
      fullJob?.status === "complete"
        ? fullJob.report_url
        : "/api/export/" + current.id + "?kind=report",
    );
};
for (const type of ["dragenter", "dragover"])
  $("viewport").addEventListener(type, (e) => {
    e.preventDefault();
    if (!loading) $("viewport").classList.add("dragover");
  });
$("viewport").addEventListener("dragleave", () =>
  $("viewport").classList.remove("dragover"),
);
$("viewport").addEventListener("drop", (e) => {
  e.preventDefault();
  $("viewport").classList.remove("dragover");
  if (!loading) openFile(e.dataTransfer.files[0]);
});
window.addEventListener("paste", (e) => {
  if (e.target.closest("input,textarea")) return;
  const file = [...(e.clipboardData?.files || [])].find((f) =>
    f.type.startsWith("image/"),
  );
  if (file && !loading) {
    e.preventDefault();
    openFile(file);
  }
});
// Tooltips on hover/focus; help buttons additionally open an accessible click popover.
for (const button of document.querySelectorAll("[data-help]")) {
  const tip = document.createElement("sp-tooltip");
  tip.setAttribute("self-managed", "");
  tip.setAttribute("placement", "left");
  tip.textContent = button.dataset.help;
  button.append(tip);
  button.onclick = (e) => {
    e.stopPropagation();
    const previous = $("helpPopover");
    if (previous?.dataset.owner === button.label) {
      previous.remove();
      return;
    }
    previous?.remove();
    const pop = document.createElement("div");
    pop.id = "helpPopover";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", button.label);
    pop.dataset.owner = button.label;
    pop.textContent = button.dataset.help;
    document.querySelector("sp-theme").append(pop);
    const r = button.getBoundingClientRect();
    pop.style.left =
      Math.max(8, Math.min(innerWidth - 276, r.left - 264)) + "px";
    pop.style.top =
      Math.min(innerHeight - pop.offsetHeight - 8, r.bottom + 5) + "px";
  };
}
window.addEventListener("click", (e) => {
  if (!e.target.closest("#helpPopover,[data-help]")) $("helpPopover")?.remove();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("helpPopover")?.remove();
});
window.addEventListener("pagehide", () => {
  requestController?.abort();
  uploadRequest?.abort();
  navigator.sendBeacon(`/api/workspace/${workspaceId}/close`);
});
window.addEventListener("pageshow", (e) => {
  if (e.persisted) location.reload();
});
const applyStaticLanguage = bindStaticTranslations(document, i18n);
function applyLanguage() {
  applyStaticLanguage();
  $("language").value = i18n.language;
  if (!source) $("filename").textContent = t("Файл не открыт");
  renderMetadata();
  renderExportLabels();
  $("globalTitle").textContent = t(progressTitle);
  if (noticeMessage) {
    $("noticeText").textContent = translateMessage(noticeMessage);
    $("retry").textContent = t(noticeStale ? "Обновить страницу" : "Повторить");
  }
  $("helpPopover")?.remove();
  renderMarkers();
  renderLive();
  renderProbes();
}
$("language").addEventListener("change", () => {
  if (i18n.setLanguage($("language").value)) applyLanguage();
});
applyLanguage();
applyDefaults();
clearMaterial();
async function init() {
  try {
    await api("/api/workspace/open", { method: "POST" });
    const data = await api("/api/catalog");
    profileName = data.profile;
    $("profile").options[0].title = profileName;
    ready = true;
    syncButtons();
  } catch (e) {
    notice(e.message, () => location.reload());
  }
}
init();
