(() => {
  var __defProp = Object.defineProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };

  // romancer/ui/icons.js
  var paths = { overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z", resources: "M4 4h16v16H4z M8 8h2 M14 8h2 M8 12h2 M14 12h2 M8 16h8", scripts: "M5 3h10l4 4v14H5z M9 11h6 M9 15h6 M15 3v5h4", assets: "M3 3h18v18H3z M3 16l5-5 4 4 4-7 5 8 M8 7h.01", playtest: "M8 4l12 8-12 8z", debug: "M8 8h8v10H8z M10 8V5h4v3 M4 10h4 M16 10h4 M4 16h4 M16 16h4 M10 18v3 M14 18v3", routes: "M5 5h.01 M19 19h.01 M5 7v6a4 4 0 004 4h6 M17 15l2 2-2 2 M5 3a2 2 0 100 4 2 2 0 000-4 M19 17a2 2 0 100 4 2 2 0 000-4", regression: "M4 20V4 M4 16h4l4-6 4 3 5-8 M17 5h4v4", release: "M12 3v12 M7 8l5-5 5 5 M4 15v6h16v-6", settings: "M12 8a4 4 0 100 8 4 4 0 000-8 M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5.6 5.6L7 7 M17 17l1.4 1.4 M5.6 18.4L7 17 M17 7l1.4-1.4", plus: "M12 5v14 M5 12h14", arrow: "M5 12h14 M13 6l6 6-6 6", folder: "M3 7V4h7l2 3h9v13H3z", search: "M10 3a7 7 0 100 14 7 7 0 000-14 M15 15l6 6", check: "M5 12l4 4L19 6", close: "M6 6l12 12 M18 6L6 18", download: "M12 3v12 M7 10l5 5 5-5 M4 17v4h16v-4", chevron: "M9 5l7 7-7 7", clock: "M12 3a9 9 0 100 18 9 9 0 000-18 M12 7v5l3 2", shield: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6" };
  paths.levels = "M3 3h18v18H3z M3 9h18 M9 9v12 M15 3v6 M15 15h6";
  paths.sound = "M9 18V5l11-2v13 M9 8l11-2 M9 18a3 2 0 11-6 0 3 2 0 016 0 M20 16a3 2 0 11-6 0 3 2 0 016 0";
  function icon(name, extra = "") {
    return `<svg class="icon ${extra}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.resources}"/></svg>`;
  }

  // romancer/ui/tool_help.js
  var TERMS = [
    [/offset/i, "A byte's position in the selected file, counted from zero. CPU addresses are different."],
    [/stride/i, "Bytes from the start of one record to the start of the next. This can include unused bytes."],
    [/capacity|allocation/i, "Maximum storage reserved for this resource. An edit must fit, including terminators and padding."],
    [/palette/i, "A set of stored colors. Pixels refer to color indexes; the selected format determines their stored values."],
    [/pointer/i, "A stored reference to another location. Its width, byte order and base determine how it is decoded."],
    [/byte order|endian/i, "Little endian stores the least significant byte first. Big endian stores the most significant byte first."],
    [/encoding|glyph/i, "The mapping between stored bytes and displayed characters. A game may use its own character table."],
    [/terminator/i, "The byte that marks the end of a text record. It also uses space inside the slot."],
    [/padding/i, "The value used to fill unused bytes in a fixed-size text slot."],
    [/bank/i, "A numbered group of data. ROM banks and palette banks are different; use the declared layout."],
    [/address/i, "A location in a declared CPU memory window. Translating it to a file offset may require the active bank."],
    [/tile format|codec/i, "How the bytes encode pixels or samples. Selecting a format does not prove where the game stores that resource."],
    [/tile index|brush value/i, "The numeric entry to place in a declared grid. Its game-specific meaning must be verified."],
    [/crc/i, "A checksum of the selected byte scope. A mismatch needs an expected value for exactly the same scope."],
    [/sha.?256/i, "A hash used to identify exact bytes. A changed ROM has a different identity."],
    [/length|bytes to|byte count/i, "Number of bytes in this range, starting at the selected offset."],
    [/control code/i, "A non-text instruction embedded in a text record, such as a pause or line break."],
    [/collision/i, "Declared values used for movement or interaction. A numeric value alone does not prove what it does."]
  ];
  function fieldExplanation(label) {
    var _a;
    return ((_a = TERMS.find(([pattern]) => pattern.test(label))) == null ? void 0 : _a[1]) || "";
  }

  // romancer/ui/common.js
  var esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  var size = (n) => n >= 1048576 ? (n / 1048576).toFixed(1) + " MiB" : n >= 1024 ? (n / 1024).toFixed(1) + " KiB" : n + " B";
  var short = (value) => String(value || "—").slice(0, 12);
  var badge = (text, tone = "neutral") => `<span class="badge ${tone}">${esc(text)}</span>`;
  var unavailableSequence = 0;
  function unavailableReason(action) {
    const reasons = {
      "asset-paste": "Copy a tile first.",
      "asset-font-change": "This glyph has a fixed advance; it has no editable width byte.",
      "configure-layout": "Declare a font for this source first.",
      "configure-menu": "Declare a font for this source first.",
      "hex-review": "Change at least one byte first.",
      "hex-clear": "There are no staged byte edits.",
      "runtime-play": "Load the selected game first.",
      "runtime-save": "Load the selected game first.",
      "runtime-restore": "Load the matching game and choose a saved state.",
      "runtime-close": "No game is loaded.",
      "sound-capture": "Load this exact source in Playtest first.",
      "script-plan": "Load an editable text definition first.",
      "compression-review": "Create a build of the decoded resource first."
    };
    if (reasons[action]) return reasons[action];
    if (/page|previous|next/.test(action)) return "No more items in this direction.";
    if (/(?:apply|build)$/.test(action)) return "Review the changes first.";
    if (/package|export/.test(action)) return "Prepare and select an export first.";
    if (/state|checkpoint/.test(action)) return "Load the matching ROM and core first.";
    if (/runtime|profile/.test(action)) return "Choose compatible content and a saved core setup.";
    if (/undo|redo/.test(action)) return "No edit history in this direction.";
    if (/stop/.test(action)) return "Start recording first.";
    return "Complete the required setup for this selection.";
  }
  function setUnavailable(node, disabled, reason) {
    node.disabled = !!disabled;
    let wrapper = node.closest(".unavailable-control");
    if (!wrapper && disabled) {
      wrapper = document.createElement("span");
      wrapper.className = "unavailable-control";
      node.before(wrapper);
      wrapper.append(node);
      const caption2 = document.createElement("span");
      caption2.className = "unavailable-reason";
      caption2.id = "unavailable-" + ++unavailableSequence;
      wrapper.append(caption2);
    }
    if (!wrapper) return;
    const caption = wrapper.querySelector(".unavailable-reason");
    caption.hidden = !disabled;
    wrapper.tabIndex = disabled ? 0 : -1;
    if (disabled) {
      const text = reason || unavailableReason(node.dataset.action);
      caption.textContent = text;
      wrapper.setAttribute("role", "group");
      wrapper.setAttribute("aria-label", node.textContent + ": " + text);
      node.setAttribute("aria-describedby", caption.id);
    } else {
      wrapper.removeAttribute("role");
      wrapper.removeAttribute("aria-label");
      node.removeAttribute("aria-describedby");
    }
  }
  function button(label, action, options = {}) {
    const reason = options.disabled ? options.reason || unavailableReason(action) : "", id = reason ? "unavailable-" + ++unavailableSequence : "";
    const html = `<button type="button" data-action="${esc(action)}" ${options.id ? `data-id="${esc(options.id)}"` : ""} ${options.name ? `data-name="${esc(options.name)}"` : ""} class="${options.primary ? "primary " : ""}${esc(options.class || "")}" ${options.disabled ? `disabled aria-describedby="${id}"` : ""}>${options.icon ? icon(options.icon) : ""}${esc(label)}</button>`;
    return reason ? `<span class="unavailable-control" role="group" tabindex="0" aria-label="${esc(label + ": " + reason)}">${html}<span class="unavailable-reason" id="${id}">${esc(reason)}</span></span>` : html;
  }
  function fieldTitle(id, label) {
    const explanation = fieldExplanation(label);
    return `<span class="field-title"><span>${esc(label)}</span>${explanation ? `<span class="field-help" tabindex="0" aria-label="About ${esc(label)}" aria-describedby="field-help-${esc(id)}">?<span id="field-help-${esc(id)}" role="tooltip" class="field-help-tip">${esc(explanation)}</span></span>` : ""}</span>`;
  }
  var field = (id, label, value = "", options = {}) => `<label class="field">${fieldTitle(id, label)}<input id="${id}" ${options.type ? `type="${options.type}"` : ""} value="${esc(value)}" placeholder="${esc(options.placeholder || "")}" ${options.readonly ? "readonly" : ""} ${options.min !== void 0 ? `min="${options.min}"` : ""}>${options.hint ? `<small>${esc(options.hint)}</small>` : ""}</label>`;
  var area = (id, label, value = "", rows = 5) => `<label class="field"><span>${esc(label)}</span><textarea id="${id}" rows="${rows}" spellcheck="false">${esc(value)}</textarea></label>`;
  var select = (id, label, options, value) => `<label class="field">${fieldTitle(id, label)}<select id="${id}">${options.map(([key3, text]) => `<option value="${esc(key3)}" ${String(key3) === String(value) ? "selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
  var jsonEditor = (id, label, value, open = false) => `<details class="config" ${open ? "open" : ""}><summary>${esc(label)} <span>JSON descriptor</span></summary>${area(id, label, typeof value === "string" ? value : JSON.stringify(value, null, 2), 8)}</details>`;
  var read = (id) => {
    const node = document.getElementById(id);
    if (!node) throw new Error("This control is no longer visible. Reopen its screen.");
    return node.value;
  };
  var json = (id) => {
    var _a, _b, _c;
    try {
      return JSON.parse(read(id));
    } catch {
      throw new Error("Check the JSON in “" + (((_c = (_b = (_a = document.getElementById(id)) == null ? void 0 : _a.closest("label")) == null ? void 0 : _b.querySelector(".field-title > span,span")) == null ? void 0 : _c.textContent) || id) + "”.");
    }
  };
  function report(result, title = "Result") {
    if (!result) return "";
    const tone = result.ok === false || ["FAIL", "BLOCKED", "REGRESSION"].includes(result.status) ? "danger" : ["PASS", "BUILT", "VERIFIED", "SCOPE_COVERED"].includes(result.status) ? "good" : "neutral";
    return `<section class="card result"><div class="card-heading"><h3>${esc(title)}</h3>${badge(result.status || "READY", tone)}</div>${result.error ? `<p class="error">${esc(typeof result.error === "string" ? result.error : result.error.message)}</p>` : ""}<details><summary>Inspect the full report</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details></section>`;
  }
  var empty = (title, message, action = "") => `<div class="empty">${icon("folder")}<h3>${esc(title)}</h3><p>${esc(message)}</p>${action}</div>`;
  function heading(kicker, title, description, actions2 = "") {
    return `<header class="page-heading"><div><h1>${esc(title)}</h1></div><div class="actions">${actions2}${title === "Help" ? "" : button("Help", "help-topic", { icon: "shield" })}</div></header>`;
  }
  function requireProject(ctx2) {
    if (!ctx2.state.project) return empty("Open a project to begin", "Import your own source or explore the original demonstration fixture.", button("Open demonstration", "demo", { primary: true, icon: "arrow" }));
    return null;
  }

  // romancer/ui/tool_inputs.js
  var selectionKey = (state2) => {
    var _a, _b, _c;
    return [(_a = state2.project) == null ? void 0 : _a.project_id, (_b = state2.artifact) == null ? void 0 : _b.artifact_id, (_c = state2.artifact) == null ? void 0 : _c.sha256].join(":") + (state2.selectionRevision === void 0 ? "" : ":" + state2.selectionRevision);
  };
  function fileInput(id, label, accept) {
    return `<label class="field"><span>${esc(label)}</span><input type="file" id="${id}" accept="${accept}"></label>`;
  }
  function downloadDocument(document2, name, type = "application/json") {
    const blob = new Blob([typeof document2 === "string" ? document2 : JSON.stringify(document2, null, 2)], { type }), url = URL.createObjectURL(blob), link = window.document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 2e3);
  }

  // romancer/ui/preferences.js
  var memory = /* @__PURE__ */ new Map();
  function readPreference(key3, fallback = null) {
    try {
      return localStorage.getItem(key3) ?? memory.get(key3) ?? fallback;
    } catch {
      return memory.get(key3) ?? fallback;
    }
  }
  function writePreference(key3, value) {
    memory.set(key3, String(value));
    try {
      localStorage.setItem(key3, String(value));
    } catch {
    }
  }
  function removePreference(key3) {
    memory.delete(key3);
    try {
      localStorage.removeItem(key3);
    } catch {
    }
  }

  // romancer/ui/workspace_resume.js
  function seedWorkspaceLocation(saved) {
    if (!saved) return;
    writePreference("romancer-project", saved.project_id);
    writePreference("romancer-artifact:" + saved.project_id, saved.artifact_id);
    writePreference("romancer-location:" + saved.project_id + ":" + saved.artifact_id, JSON.stringify(saved));
  }
  var WorkspaceLocationWriter = class {
    constructor(api2, failed = () => {
    }) {
      this.api = api2;
      this.failed = failed;
      this.pending = null;
      this.hasPending = false;
      this.promise = null;
    }
    enqueue(location2) {
      this.pending = location2;
      this.hasPending = true;
      if (!this.promise) this.promise = this.drain().finally(() => {
        this.promise = null;
        if (this.hasPending) this.enqueue(this.pending);
      });
      return this.promise;
    }
    async drain() {
      while (this.hasPending) {
        const location2 = this.pending;
        this.hasPending = false;
        try {
          await this.api.call("settings.workspace.save", { location: location2 });
        } catch (error) {
          this.failed(error);
        }
      }
    }
  };
  var pages = /* @__PURE__ */ new Set(["overview", "resources", "scripts", "assets", "tables", "levels", "sound", "playtest", "release", "automation", "help", "settings", "debug", "routes", "regression", "tutorials"]);
  var integer = (value, max) => Number.isSafeInteger(value) && value >= 0 && value <= max;
  var locationKey = (state2) => {
    var _a, _b;
    return "romancer-location:" + ((_a = state2.project) == null ? void 0 : _a.project_id) + ":" + ((_b = state2.artifact) == null ? void 0 : _b.artifact_id);
  };
  function locationSnapshot(state2, scroll = 0) {
    var _a, _b;
    const a = state2.artifact;
    if (!state2.project || !a || !pages.has(state2.page)) return null;
    const data = (_a = state2.results) == null ? void 0 : _a["resource.inspect"], bound = (data == null ? void 0 : data.artifact_id) === a.artifact_id && data.sha256 === a.sha256;
    const offset = bound ? data.offset : 0, selected2 = ((_b = state2.hexDraft) == null ? void 0 : _b.scope) === selectionKey(state2) ? state2.hexDraft.selected : offset;
    return {
      version: 1,
      project_id: state2.project.project_id,
      artifact_id: a.artifact_id,
      sha256: a.sha256,
      page: state2.page,
      offset: integer(offset, Math.max(0, a.size - 1)) ? offset : 0,
      selected: integer(selected2, Math.max(0, a.size - 1)) ? selected2 : offset,
      scroll: Number.isFinite(scroll) ? Math.max(0, Math.min(1e7, scroll)) : 0,
      assetPage: integer(state2.assetPage, 1e5) ? state2.assetPage : 0,
      scriptPage: integer(state2.scriptPage, 1e5) ? state2.scriptPage : 0,
      catalogPage: integer(state2.catalogPage, 1e5) ? state2.catalogPage : 0,
      catalogQuery: typeof state2.catalogQuery === "string" ? state2.catalogQuery.slice(0, 256) : ""
    };
  }
  function restoreLocation(state2, saved) {
    var _a;
    const a = state2.artifact;
    if (!a || !saved || saved.version !== 1 || saved.project_id !== ((_a = state2.project) == null ? void 0 : _a.project_id) || saved.artifact_id !== a.artifact_id || saved.sha256 !== a.sha256 || !pages.has(saved.page)) return false;
    if (!integer(saved.offset, Math.max(0, a.size - 1)) || !integer(saved.selected, Math.max(0, a.size - 1)) || !Number.isFinite(saved.scroll) || saved.scroll < 0 || saved.scroll > 1e7) return false;
    if (!["assetPage", "scriptPage", "catalogPage"].every((k) => integer(saved[k], 1e5)) || typeof saved.catalogQuery !== "string" || saved.catalogQuery.length > 256) return false;
    Object.assign(state2, { page: saved.page, resourceJump: saved.offset, resumeHexSelection: saved.selected, resumeScroll: saved.scroll, assetPage: saved.assetPage, scriptPage: saved.scriptPage, catalogPage: saved.catalogPage, catalogQuery: saved.catalogQuery });
    state2.resumeIdentity = saved.project_id + ":" + a.artifact_id + ":" + a.sha256;
    return true;
  }

  // romancer/ui/interface_scale.js
  function applyInterfaceScale(value) {
    const scale = [100, 125, 150, 200].includes(Number(value)) ? Number(value) : 100, factor = scale / 100 * 0.75, root = document.documentElement;
    root.style.zoom = String(factor);
    root.style.setProperty("--workspace-height", String(window.innerHeight / factor) + "px");
    root.classList.toggle("scaled-compact", window.innerWidth / factor <= 1100);
    root.classList.toggle("scaled-narrow", window.innerWidth / factor <= 820);
    return scale;
  }

  // romancer/ui/app_settings.js
  var DEFAULT_SETTINGS = Object.freeze({ theme: "romancer", scale: 100, autoDeepScan: true, autoGraphics: true, rememberWorkspace: true, volume: 80, startMuted: false, loopPreview: false, reduceMotion: false, advancedTools: false });
  var keys = Object.keys(DEFAULT_SETTINGS);
  var booleanKeys = keys.filter((key3) => typeof DEFAULT_SETTINGS[key3] === "boolean");
  function validateSettings(values) {
    if (!values || typeof values !== "object" || Array.isArray(values) || Object.keys(values).length !== keys.length || Object.keys(values).some((key3) => !keys.includes(key3))) throw Error("Settings contain missing or unknown fields.");
    if (!["romancer", "dark", "light"].includes(values.theme)) throw Error("Choose a valid theme.");
    if (!Number.isSafeInteger(values.scale) || ![100, 125, 150, 200].includes(values.scale)) throw Error("Choose a supported interface scale.");
    if (!Number.isSafeInteger(values.volume) || values.volume < 0 || values.volume > 100) throw Error("Volume must be a whole number from 0 to 100.");
    for (const key3 of booleanKeys) if (typeof values[key3] !== "boolean") throw Error(key3 + " must be true or false.");
    return Object.fromEntries(keys.map((key3) => [key3, values[key3]]));
  }
  function checkedPacket(packet) {
    var _a;
    if (!packet || packet.ok === false || !Number.isSafeInteger(packet.revision) || packet.revision < 0) throw Error(((_a = packet == null ? void 0 : packet.error) == null ? void 0 : _a.message) || (packet == null ? void 0 : packet.error) || "Settings response has an invalid revision.");
    return { revision: packet.revision, values: validateSettings(packet.values) };
  }
  var cached = { revision: 0, values: { ...DEFAULT_SETTINGS } };
  var cacheVersion = 0;
  try {
    const saved = readPreference("romancer-settings");
    if (saved) cached = checkedPacket(JSON.parse(saved));
    else {
      const scale = Number(readPreference("romancer-scale", 100));
      if ([100, 125, 150, 200].includes(scale)) cached.values.scale = scale;
    }
  } catch {
  }
  function getSettings() {
    return { ...cached.values };
  }
  function settingsAppearance(values = getSettings()) {
    var _a;
    const next = validateSettings(values), root = (_a = globalThis.document) == null ? void 0 : _a.documentElement;
    if (root) {
      root.dataset.theme = next.theme;
      root.classList.toggle("reduce-motion", next.reduceMotion);
      if (globalThis.window) applyInterfaceScale(next.scale);
    }
    return next;
  }
  function hydrateSettings(packet) {
    const next = checkedPacket(packet);
    settingsAppearance(next.values);
    cached = next;
    cacheVersion++;
    writePreference("romancer-settings", JSON.stringify(next));
    writePreference("romancer-scale", String(next.values.scale));
    return getSettings();
  }
  async function loadSettings(api2) {
    const version = cacheVersion, packet = checkedPacket(await api2.call("settings.get", {}));
    if (cacheVersion === version || packet.revision > cached.revision) return hydrateSettings(packet);
    return getSettings();
  }
  async function saveSettings(api2, values) {
    const next = validateSettings(values), revision = cached.revision, packet = checkedPacket(await api2.call("settings.save", { revision, values: next }));
    if (packet.revision !== revision + 1 || JSON.stringify(packet.values) !== JSON.stringify(next)) throw Error("Settings save returned different values. Reopen Settings to reload them.");
    if (packet.revision >= cached.revision) return hydrateSettings(packet);
    return getSettings();
  }

  // romancer/ui/workspace_status.js
  function saveStatus(snapshot) {
    return snapshot.failed ? { label: "Save failed", tone: "danger" } : snapshot.pending ? { label: "Saving…", tone: "warm" } : { label: "Saved", tone: "good" };
  }
  function guardClose(event, queue, state2 = {}) {
    const active = state2.job && !["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(state2.job.status);
    if (!queue.snapshot().unsafe && !hasStagedChanges(state2) && !active) return;
    event.preventDefault();
    event.returnValue = "";
  }
  function artifactStatus(artifact) {
    return artifact ? { label: artifact.kind === "source" ? "Original" : "Build", tone: artifact.kind === "source" ? "neutral" : "good" } : { label: "No file", tone: "neutral" };
  }
  var equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  function changed(items) {
    return Array.isArray(items) && items.some((c) => c.before_pixels ? !equal(c.before_pixels, c.after_pixels) : Object.hasOwn(c, "before") ? !equal(c.before, c.after) : true);
  }
  function hasStagedChanges(state2) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n;
    if (!state2.project || !state2.artifact) return false;
    if (((_a = state2.pending) == null ? void 0 : _a.artifact_id) === state2.artifact.artifact_id || ((_b = state2.gameEditPlan) == null ? void 0 : _b.scope) === selectionKey(state2)) return true;
    if (((_c = state2.gameMapsView) == null ? void 0 : _c.scope) === selectionKey(state2) && [...((_d = state2.gameMapsView.models) == null ? void 0 : _d.values()) || []].some((model) => model.values().length)) return true;
    const prefix = state2.project.project_id + ":" + state2.artifact.artifact_id + ":";
    for (const [key3, value] of Object.entries(state2.drafts || {})) {
      if (!key3.startsWith(prefix)) continue;
      if (/:(?:asset-changes|table-changes|level-changes|sound-changes)$/.test(key3)) {
        try {
          const data = JSON.parse(value);
          if (changed(Array.isArray(data) ? data : data == null ? void 0 : data.changes)) return true;
        } catch {
        }
      }
      if (key3.endsWith(":hex-changes")) {
        try {
          const saved = JSON.parse(value);
          if (saved.artifact_id === state2.artifact.artifact_id && saved.sha256 === state2.artifact.sha256 && ((_e = saved.edits) == null ? void 0 : _e.length)) return true;
        } catch {
        }
      }
      if (key3.endsWith(":game-map-changes")) {
        try {
          const saved = JSON.parse(value);
          if (saved.source_sha256 === state2.artifact.sha256 && Object.values(saved.changes_by_header || {}).some(changed)) return true;
        } catch {
        }
      }
      if (key3.includes(":game-")) {
        const field2 = (_h = (_g = (_f = state2.gameVisualModel) == null ? void 0 : _f.model) == null ? void 0 : _g.fields) == null ? void 0 : _h.find((f) => key3.endsWith(":game-" + f.id));
        if (field2 && String(field2.value) !== String(value)) return true;
      }
      if (key3.endsWith(":paint-buffer")) {
        try {
          const paint = JSON.parse(value), doc = (_i = state2.results) == null ? void 0 : _i["assets.inspect"];
          const bitmap = (doc == null ? void 0 : doc.document_id) === paint.document_id ? doc.bitmaps.find((b) => b.id === paint.bitmap_id) : null;
          if ((bitmap == null ? void 0 : bitmap.cells[paint.cell_index]) && !equal(paint.pixels, bitmap.cells[paint.cell_index].pixels)) return true;
        } catch {
        }
      }
      const table = (_j = state2.results) == null ? void 0 : _j["tables.inspect"];
      if (table && key3.includes(":table-cell-" + table.document_id)) {
        for (const row of table.rows) for (const [index, cell] of row.cells.entries()) if (key3.endsWith("-" + row.index + "-" + index) && String(value) !== String(cell.value)) return true;
      }
      const script = (_k = state2.results) == null ? void 0 : _k["script.inspect"];
      if ((script == null ? void 0 : script.records) && key3.includes(":script-segment-")) {
        for (const [index, record] of script.records.entries()) for (const segment of record.segments) if (key3.endsWith(":script-segment-" + index + "-" + segment.index) && String(value) !== String(segment.text)) return true;
      }
    }
    return ((_l = state2.hexDraft) == null ? void 0 : _l.scope) === selectionKey(state2) && !!((_n = (_m = state2.hexDraft) == null ? void 0 : _m.changes) == null ? void 0 : _n.size);
  }
  function workspaceStatus(state2, snapshot, includeFile = true) {
    const file = artifactStatus(state2.artifact), save = saveStatus(snapshot);
    return `<div class="workspace-state" aria-label="File and edit status">${includeFile ? badge(file.label, file.tone) : ""}${hasStagedChanges(state2) ? badge("Staged changes · build required", "warm") : ""}<span id="draft-save-status" role="status" aria-live="polite" class="save-state ${save.tone}">${esc(save.label)}</span>${snapshot.failed ? '<button type="button" data-action="draft-retry">Retry save</button>' : ""}</div>`;
  }

  // romancer/ui/shortcuts.js
  var SHORTCUTS = [["Ctrl+S", "Save drafts now"], ["Ctrl+Z", "Undo the active editor"], ["Ctrl+Y / Ctrl+Shift+Z", "Redo the active editor"], ["Ctrl+K", "Search the workspace"], ["?", "Show keyboard shortcuts"]];
  function shortcutFor(event, { modalOpen = false, gameFocused = false } = {}) {
    var _a, _b;
    if (event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229 || event.metaKey || event.altKey || modalOpen || gameFocused) return null;
    const editing = !!((_b = (_a = event.target) == null ? void 0 : _a.closest) == null ? void 0 : _b.call(_a, 'input,textarea,select,[contenteditable]:not([contenteditable="false"])')), key3 = event.key.toLowerCase();
    if (event.ctrlKey) {
      if (!event.shiftKey && key3 === "s") return "save";
      if (!event.shiftKey && key3 === "k") return "search";
      if (editing) return null;
      if (key3 === "z") return event.shiftKey ? "redo" : "undo";
      if (!event.shiftKey && key3 === "y") return "redo";
    } else if (!editing && event.key === "?") return "help";
    return null;
  }
  function historyAction(page, editor, direction, available) {
    const suffix = direction < 0 ? "undo" : "redo";
    const prefix = page === "levels" ? editor === "level-canvas" ? "levels" : editor === "maps-edit" ? "maps" : null : page === "assets" ? editor === "sprite-canvas" ? "sprite" : editor === "paint-canvas" ? "pixel" : null : null;
    const action = prefix && prefix + "-" + suffix;
    return action && available(action) ? action : "draft-" + suffix;
  }
  function rememberEditor(state2, event, refresh) {
    var _a, _b, _c, _d;
    const canvas = (_b = (_a = event.target).closest) == null ? void 0 : _b.call(_a, "canvas");
    if (canvas) state2.historyEditor = canvas.id;
    else if ((_d = (_c = event.target).closest) == null ? void 0 : _d.call(_c, "input,textarea,select,[contenteditable]")) state2.historyEditor = "field";
    else return;
    refresh();
  }

  // romancer/ui/runtime_setup.js
  var families = [["nes", "NES"], ["snes", "SNES"], ["genesis", "Genesis"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]];
  var defaultKeys = { up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight", a: "z", b: "x", x: "a", y: "s", l: "q", r: "w", start: "Enter", select: "Shift" };
  async function runtimeSetup(ctx2) {
    var _a, _b, _c, _d, _e;
    const { state: state2 } = ctx2, family = state2.profileFamily || ((_a = state2.artifact) == null ? void 0 : _a.system_id) || "nes";
    if (state2.profileLoadedFamily !== family) {
      const saved = await ctx2.api.call("profiles.get", { system_id: family });
      state2.profile = saved.profile;
      state2.profileEngine = saved.engine || "";
      state2.profileLoadedFamily = family;
    }
    const profile = state2.profile;
    let available = false, setupError = "";
    if (profile) {
      try {
        const checked = await ctx2.api.call("profiles.validate", { system_id: family });
        available = checked.ok;
      } catch (error) {
        setupError = error.message;
      }
    }
    state2.profileAvailable = available;
    const candidates = (((_b = state2.results["profiles.scan_local"]) == null ? void 0 : _b.candidates) || []).filter((row) => row.systems.includes(family));
    ctx2.use({
      "profile-scan": () => ctx2.run("profiles.scan_local", { directories: [] }, { refresh: false }),
      "profile-auto": async (node) => {
        const candidate = candidates.find((row) => row.candidate_id === node.dataset.id);
        if (!candidate) throw new Error("Scan local cores and choose a result.");
        const result = await ctx2.run("profiles.configure_local", { system_id: family, candidate }, { refresh: false, render: false });
        state2.profile = result.profile;
        state2.profileLoadedFamily = family;
        await ctx2.render();
        ctx2.notify("Ready to load this system.");
      },
      "profile-open": async () => {
        state2.profileFamily = read("profile-family");
        state2.profileLoadedFamily = null;
        const result = await ctx2.api.call("profiles.get", { system_id: state2.profileFamily });
        state2.profile = result.profile;
        state2.profileEngine = result.engine || "";
        state2.profileLoadedFamily = state2.profileFamily;
        if (result.profile) {
          ctx2.setDraft("core-path", result.profile.core);
          ctx2.setDraft("core-options", JSON.stringify(result.profile.options, null, 2));
          ctx2.setDraft("system-path", result.profile.system_dir || "");
          for (const [key3, value] of Object.entries(result.profile.input_map)) ctx2.setDraft("key-" + key3, value);
        }
        await ctx2.render();
      },
      "profile-save": async () => {
        if (read("profile-family") !== state2.profileLoadedFamily) throw new Error("Open the selected system setup before saving.");
        const input_map = Object.fromEntries(Object.keys(defaultKeys).map((k) => [k, read("key-" + k)]));
        const result = await ctx2.run("profiles.save", { system_id: read("profile-family"), core: read("core-path"), options: json("core-options"), system_dir: read("system-path").trim() || null, input_map }, { refresh: false, render: false });
        state2.profile = result.profile;
        state2.profileFamily = result.profile.system_id;
        state2.profileEngine = "";
        state2.profileLoadedFamily = result.profile.system_id;
        ctx2.notify("System setup saved.");
        await ctx2.render();
      },
      "profile-validate": () => ctx2.run("profiles.validate", { system_id: read("profile-family") }, { refresh: false }),
      "profile-option": () => {
        const key3 = read("option-key"), value = read("option-value");
        if (!key3) throw new Error("Enter an option name.");
        ctx2.setDraft("core-options", JSON.stringify({ ...json("core-options"), [key3]: value }, null, 2));
        return ctx2.render();
      }
    });
    return `<p class="notice ${setupError ? "warm" : ""}">${available ? `Ready to load${state2.profileEngine ? " · " + esc(state2.profileEngine) + " included" : ""}` : profile ? esc(setupError) : "Choose a local emulator core to playtest."}</p>${!profile ? `${button("Find local cores", "profile-scan")}<div class="actions">${candidates.map((row) => button("Use " + row.core.split(/[\\/]/).at(-1), "profile-auto", { id: row.candidate_id })).join("")}</div>${state2.results["profiles.scan_local"] && !candidates.length ? "<p>No matching core found. Open Advanced setup to choose one.</p>" : ""}` : ""}<div class="field-row">${select("profile-family", "System", families, family)}${select("runtime-content", "Content", [...state2.artifact ? [[state2.artifact.artifact_id, state2.artifact.name]] : []], ctx2.draft("runtime-content", ((_c = state2.artifact) == null ? void 0 : _c.artifact_id) || "disc:" + ((_e = (_d = state2.project.containers) == null ? void 0 : _d[0]) == null ? void 0 : _e.container_id)))}</div><div class="actions">${button("Open saved setup", "profile-open")}${button("Check setup", "profile-validate")}</div><details class="config"><summary>Advanced options & controller keys</summary>${field("system-path", "System-file folder (optional)", ctx2.draft("system-path", (profile == null ? void 0 : profile.system_dir) || ""))}<div class="field-row">${field("option-key", "Option name", ctx2.draft("option-key", ""))}${field("option-value", "Option value", ctx2.draft("option-value", ""))}</div>${button("Set option", "profile-option")}<div class="field-row">${Object.entries(defaultKeys).map(([key3, value]) => field("key-" + key3, key3.toUpperCase(), ctx2.draft("key-" + key3, (profile == null ? void 0 : profile.input_map[key3]) || value))).join("")}</div></details>${button("Save system setup", "profile-save")}`;
  }
  function wavFromPCM(encoded, rate) {
    if (!Number.isInteger(rate) || rate < 1 || rate > 192e3) throw new Error("Unsupported sample rate.");
    const raw = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    if (!raw.length || raw.length > 1048576 || raw.length % 4) throw new Error("Invalid PCM capture.");
    const buffer = new ArrayBuffer(44 + raw.length), view = new DataView(buffer), bytes = new Uint8Array(buffer);
    function text(offset, value) {
      for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i);
    }
    text(0, "RIFF");
    view.setUint32(4, 36 + raw.length, true);
    text(8, "WAVEfmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 2, true);
    view.setUint32(24, rate, true);
    view.setUint32(28, rate * 4, true);
    view.setUint16(32, 4, true);
    view.setUint16(34, 16, true);
    text(36, "data");
    view.setUint32(40, raw.length, true);
    bytes.set(raw, 44);
    return bytes;
  }
  var audioURL;
  var audioNode;
  function disposeAudio() {
    if (audioNode) {
      try {
        audioNode.pause();
        audioNode.removeAttribute("src");
        audioNode.load();
      } catch {
      }
      audioNode = null;
    }
    if (audioURL) {
      URL.revokeObjectURL(audioURL);
      audioURL = null;
    }
  }
  function mountAudio(record) {
    const player = document.getElementById("pcm-player"), canvas = document.getElementById("pcm-wave");
    if (!player || !canvas || !(record == null ? void 0 : record.observed)) return;
    disposeAudio();
    audioNode = player;
    const wav = wavFromPCM(record.pcm_s16le_base64, record.sample_rate);
    audioURL = URL.createObjectURL(new Blob([wav], { type: "audio/wav" }));
    player.src = audioURL;
    const prefs = getSettings();
    player.volume = prefs.volume / 100;
    player.muted = prefs.startMuted;
    player.loop = prefs.loopPreview;
    const samples = new DataView(wav.buffer, 44), frames = (wav.length - 44) / 4, context = canvas.getContext("2d");
    context.fillStyle = "#101b20";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#76dbc3";
    context.beginPath();
    for (let x = 0; x < canvas.width; x++) {
      const frame = Math.min(frames - 1, Math.floor(x / canvas.width * frames)), value = samples.getInt16(frame * 4, true) / 32768, y = canvas.height / 2 - value * canvas.height * 0.45;
      if (x) context.lineTo(x, y);
      else context.moveTo(x, y);
    }
    context.stroke();
  }

  // romancer/ui/workbench_usability.js
  function chooseArtifact(project, id) {
    const rows = project.sources.concat(project.builds);
    return rows.find((r) => r.artifact_id === id) || project.sources[0] || project.builds[0] || null;
  }
  function shouldSaveField(node) {
    return !!node.id && !node.id.startsWith("settings-") && !node.closest("dialog") && !["global-search", "project-select", "artifact-select"].includes(node.id) && !["file", "hidden", "checkbox", "radio"].includes(node.type);
  }
  var retainedScroll = (previous, next, scroll) => previous === next ? Math.max(0, scroll) : 0;
  function detailsEntries(root) {
    const counts = /* @__PURE__ */ new Map();
    return [...root.querySelectorAll("details")].map((node) => {
      var _a;
      const summary = ((_a = node.querySelector(":scope > summary")) == null ? void 0 : _a.textContent.split(" ·")[0].trim()) || "", index = counts.get(summary) || 0;
      counts.set(summary, index + 1);
      return [node.id || summary + ":" + index, node];
    });
  }
  var rememberDetails = (root) => root ? new Map(detailsEntries(root).map(([key3, node]) => [key3, node.open])) : /* @__PURE__ */ new Map();
  function restoreDetails(root, saved) {
    for (const [key3, node] of detailsEntries(root)) if (saved.has(key3)) node.open = saved.get(key3);
  }
  async function runScoped(ctx2, operation, parameters, options = {}, updateJob2 = () => {
  }) {
    const { state: state2 } = ctx2, scope = selectionKey(state2), current2 = () => scope === selectionKey(state2);
    const changed2 = () => Error("Action finished for the previous selection. Open that project or file to review its result.");
    let result;
    try {
      result = await ctx2.api.job(operation, parameters, updateJob2);
    } catch (error) {
      if (!current2()) throw changed2();
      if (error.result) state2.results[operation] = error.result;
      if (options.render !== false) await ctx2.render();
      throw error;
    }
    if (!current2()) throw changed2();
    if (options.refresh !== false) await ctx2.refreshProject();
    if (!current2()) throw changed2();
    state2.results[operation] = result;
    if (options.render !== false) await ctx2.render();
    return result;
  }

  // romancer/ui/cartridge_verification.js
  var checkLabel = (status) => ({ PASS: "Consistent", FAIL: "Mismatch", WARN: "Needs attention", NOT_CHECKED: "Not checked" })[status] || "Not checked";
  var checkTone = (status) => ({ PASS: "good", FAIL: "danger", WARN: "warm" })[status] || "neutral";
  function registerVerificationNavigation(ctx2) {
    const scope = selectionKey(ctx2.state);
    ctx2.use({ "rom-verification-view": async (node) => {
      var _a, _b, _c, _d, _e, _f;
      const { state: state2 } = ctx2, health = (_c = (_b = (_a = state2.romScans) == null ? void 0 : _a[scope]) == null ? void 0 : _b.result) == null ? void 0 : _c.health, offset = Number(node.dataset.id);
      if (scope !== selectionKey(state2) || ((_d = health == null ? void 0 : health.source) == null ? void 0 : _d.sha256) !== ((_e = state2.artifact) == null ? void 0 : _e.sha256) || !Number.isSafeInteger(offset) || offset < 0 || offset >= state2.artifact.size || !((_f = health.checks) == null ? void 0 : _f.some((check) => {
        var _a2;
        return (_a2 = check.locations) == null ? void 0 : _a2.some((location2) => location2.offset === offset);
      }))) throw Error("Scan the selected source again before opening verification bytes.");
      state2.resourceJump = offset;
      await ctx2.navigate("resources");
    } });
  }
  function verificationResults(health) {
    var _a;
    if (!((_a = health == null ? void 0 : health.checks) == null ? void 0 : _a.length)) return "";
    const counts = {};
    for (const check of health.checks) counts[check.status] = (counts[check.status] || 0) + 1;
    const summary = Object.entries(counts).map(([status, n]) => n + " " + checkLabel(status).toLowerCase()).join(" · ");
    return `<details class="cartridge-verification" ${counts.FAIL || counts.WARN ? "open" : ""}><summary>Cartridge verification · ${esc(summary)}</summary><div class="table-wrap"><table><thead><tr><th>Check</th><th>Result</th><th>Details</th></tr></thead><tbody>${health.checks.map((check) => `<tr><td>${esc(check.name)}${Number.isSafeInteger(check.cpu_address) ? `<br><code>CPU 0x${check.cpu_address.toString(16).toUpperCase()}</code>` : ""}</td><td>${badge(checkLabel(check.status), checkTone(check.status))}</td><td>${esc(check.detail)}${(check.locations || []).map((location2) => button(location2.label || "View bytes", "rom-verification-view", { id: String(location2.offset) })).join("")}</td></tr>`).join("")}</tbody></table></div><p>These are static cartridge checks. Revision matching and successful gameplay require separate evidence.</p></details>`;
  }

  // romancer/ui/cheat_clues.js
  var hex = (value) => "0x" + Number(value).toString(16).toUpperCase();
  function documentFor(state2) {
    var _a, _b, _c, _d, _e;
    const own = (_a = state2.results) == null ? void 0 : _a["cheats.inspect"];
    if ((own == null ? void 0 : own.scope) === selectionKey(state2) && own.source_sha256 === ((_b = state2.artifact) == null ? void 0 : _b.sha256)) return own;
    return (_e = (_d = (_c = state2.romScans) == null ? void 0 : _c[selectionKey(state2)]) == null ? void 0 : _d.result) == null ? void 0 : _e.cheat_references;
  }
  function registerCheatNavigation(ctx2) {
    const scope = selectionKey(ctx2.state);
    ctx2.use({ "cheat-view-bytes": async (node) => {
      var _a, _b;
      if (scope !== selectionKey(ctx2.state)) throw Error("The selected source changed. Scan it again.");
      const offset = Number(node.dataset.id), doc = documentFor(ctx2.state);
      const found = (doc == null ? void 0 : doc.source_sha256) === ((_a = ctx2.state.artifact) == null ? void 0 : _a.sha256) && ((_b = doc.entries) == null ? void 0 : _b.some((row) => {
        var _a2;
        return (_a2 = row.alternatives) == null ? void 0 : _a2.some((group) => group.some((part) => {
          var _a3;
          return (_a3 = part.locations) == null ? void 0 : _a3.some((location2) => location2.offset === offset);
        }));
      }));
      if (!Number.isSafeInteger(offset) || offset < 0 || !found) throw Error("Scan the selected source before opening a code location.");
      ctx2.state.resourceJump = offset;
      await ctx2.navigate("resources");
    } });
  }
  function cheatClues(doc, { paging = false } = {}) {
    if (!doc || !doc.catalog_count) return "";
    const rows = doc.entries || [], page = doc.page || 0, limit = doc.limit || 20, pages2 = Math.max(1, Math.ceil((doc.total || 0) / limit));
    const pager = paging && pages2 > 1 ? `<div class="actions">${button("Previous", "cheat-page", { id: String(page - 1), disabled: page === 0 })}<span>Page ${page + 1} of ${pages2}</span>${button("Next", "cheat-page", { id: String(page + 1), disabled: page + 1 >= pages2 })}</div>` : "";
    const limits = doc.response_truncated ? '<p class="notice warm">Some reference text or decoded details were shortened for the result limit. Full imported text remains in the local catalog.</p>' : "";
    return `<details class="cheat-clues"><summary>Code references · ${doc.total} matching entries</summary><p>Labels describe the source’s claim. Operation on this ROM has not been independently verified. Bank candidates do not establish the active bank.</p>${limits}${!rows.length ? `<p>${doc.catalog_count} references imported; no matching references for this ROM. Other games’ offsets are not applied here.</p>` : `<div class="table-wrap"><table><thead><tr><th>Source label</th><th>Revision</th><th>Decoded locations</th></tr></thead><tbody>${rows.map((row) => {
      var _a;
      return `<tr><td><strong>${esc(row.label)}</strong><br><code>${esc(row.code_text)}</code>${row.decode_truncated ? `<p class="notice warm">${row.omitted_code_parts} code parts omitted by the analysis budget. This is an incomplete combination.</p>` : ""}<details><summary>Source</summary><p>${esc(row.game_title)} · ${esc(row.source_location || "Location not recorded")}</p>${row.source_refs_truncated || ((_a = row.truncated_fields) == null ? void 0 : _a.length) ? "<p>Provenance details shortened; full text retained in the catalog.</p>" : ""}${/^https?:\/\//i.test(row.source_url || "") ? `<a href="${esc(row.source_url)}" target="_blank" rel="noreferrer noopener">Reference</a>` : ""}</details></td><td>${badge(row.revision_status || "UNSPECIFIED", "neutral")}<br><small>Gameplay unverified</small></td><td>${(row.alternatives || []).map((group, index) => `<div>${row.alternatives.length > 1 ? `Alternative ${index + 1} · ` : ""}${group.map((part) => {
        var _a2;
        return `<p><code>${esc(part.code)}</code>${((_a2 = part.decoded) == null ? void 0 : _a2.address) !== void 0 ? " · CPU " + hex(part.decoded.address) + " · replacement " + hex(part.decoded.value) + (part.decoded.compare !== null && part.decoded.compare !== void 0 ? " · expected " + hex(part.decoded.compare) : "") : ""}${part.error ? "<br>" + esc(part.error) : ""}${part.mapping_reason ? "<br>" + esc(part.mapping_reason) : ""}${(part.locations || []).map((location2) => `<br>${button("Inspect " + hex(location2.offset), "cheat-view-bytes", { id: String(location2.offset) })} <small>${esc(location2.mapping_status || "candidate")} · ${esc(location2.compare_status || "No compare byte")} · stored ${esc(location2.before_hex || "")}</small>`).join("")}</p>`;
      }).join("")}</div>`).join("")}</td></tr>`;
    }).join("")}</tbody></table></div>`}${pager}${!paging && (doc.total || 0) > rows.length ? `<p>Showing ${rows.length} of ${doc.total}. Use Code reference catalog in Resources to search or page through the rest.</p>` : ""}<p>These references do not create edits or run cheats. Use a checked definition or investigate the bytes before making a separate build.</p></details>`;
  }
  function cheatControls(ctx2) {
    var _a, _b, _c;
    const { state: state2 } = ctx2;
    if (!state2.project) return "";
    const project = state2.project.project_id, scope = selectionKey(state2), current2 = () => scope === selectionKey(state2);
    const doc = documentFor(state2);
    registerCheatNavigation(ctx2);
    const inspect = async (page, query) => {
      if (!current2() || !state2.artifact) throw Error("The selected source changed. Choose a source first.");
      const generation = state2.cheatRequestGeneration = (state2.cheatRequestGeneration || 0) + 1;
      const result = await ctx2.api.call("cheats.inspect", { ...ctx2.sourceParams(), query, page, limit: 20 });
      if (!current2() || state2.cheatRequestGeneration !== generation) return;
      state2.results["cheats.inspect"] = { ...result, query, scope };
      await ctx2.render();
    };
    ctx2.use({
      "cheat-import": async () => {
        var _a2, _b2, _c2;
        const file = (_a2 = document.getElementById("cheat-file")) == null ? void 0 : _a2.files[0];
        if (!file) throw Error("Choose a local code catalog first.");
        const input = await ctx2.api.uploadInput(project, file, "catalog");
        if (((_b2 = state2.project) == null ? void 0 : _b2.project_id) !== project) throw Error("The project changed. Import into the selected project again.");
        const result = await ctx2.api.job("cheats.import", { project_id: project, input_id: input.input_id });
        if (((_c2 = state2.project) == null ? void 0 : _c2.project_id) !== project) return;
        state2.cheatRequestGeneration = (state2.cheatRequestGeneration || 0) + 1;
        delete state2.results["cheats.inspect"];
        state2.romScans = {};
        ctx2.notify(`${result.count} code references imported. The source ROM is unchanged.`);
        await ctx2.render();
        if (current2() && state2.artifact) await ensureRomScan(ctx2, true);
      },
      "cheat-inspect": () => inspect(0, read("cheat-query").trim()),
      "cheat-page": (node) => {
        const page = Number(node.dataset.id);
        if (!Number.isInteger(page) || page < 0 || page > 2e4) throw Error("Invalid reference page.");
        return inspect(page, (doc == null ? void 0 : doc.query) || "");
      }
    });
    return `<details class="card"><summary>Code reference catalog${doc ? ` · ${doc.catalog_count} entries` : ""}</summary><p>Import documented codes as investigation leads. Required combinations and alternate revision codes stay grouped; publication references do not certify gameplay.</p>${fileInput("cheat-file", "Local TXT, JSON, JSONL, CSV or TSV catalog", ".txt,.json,.jsonl,.csv,.tsv")}${button("Import code references", "cheat-import")}<div class="field-row">${field("cheat-query", "Find source labels", (doc == null ? void 0 : doc.query) ?? ctx2.draft("cheat-query", ""))}${button("Inspect matching references", "cheat-inspect", { disabled: !state2.artifact })}</div>${cheatClues(((_b = (_a = state2.results) == null ? void 0 : _a["cheats.inspect"]) == null ? void 0 : _b.scope) === scope && state2.results["cheats.inspect"].source_sha256 === ((_c = state2.artifact) == null ? void 0 : _c.sha256) ? state2.results["cheats.inspect"] : null, { paging: true })}</details>`;
  }

  // romancer/ui/engine_findings.js
  function registerEngineNavigation(ctx2) {
    const scope = selectionKey(ctx2.state);
    ctx2.use({ "engine-view-bytes": async (node) => {
      var _a, _b, _c, _d, _e;
      const doc = (_c = (_b = (_a = ctx2.state.romScans) == null ? void 0 : _a[scope]) == null ? void 0 : _b.result) == null ? void 0 : _c.engine_recognition, offset = Number(node.dataset.id);
      if (scope !== selectionKey(ctx2.state) || (doc == null ? void 0 : doc.source_sha256) !== ((_d = ctx2.state.artifact) == null ? void 0 : _d.sha256) || !Number.isSafeInteger(offset) || !((_e = doc.findings) == null ? void 0 : _e.some((row) => {
        var _a2;
        return (_a2 = row.locations) == null ? void 0 : _a2.some((location2) => location2.offset === offset);
      }))) throw Error("Scan the selected source before opening an engine location.");
      ctx2.state.resourceJump = offset;
      await ctx2.navigate("resources");
    } });
  }
  function engineFindings(doc) {
    var _a;
    if (!((_a = doc == null ? void 0 : doc.findings) == null ? void 0 : _a.length)) {
      if ((doc == null ? void 0 : doc.status) === "AMBIGUOUS") return '<p class="notice warm">Multiple engine structures matched. The result is ambiguous; no table was selected.</p>';
      if ((doc == null ? void 0 : doc.status) === "BUDGET_EXCEEDED") return `<p class="notice warm">Engine scan reached its work budget: ${esc(doc.budget_reason || "limit reached")}. No complete finding is reported.</p>`;
      return "";
    }
    return `<details class="engine-findings"><summary>Recognized data structures · ${doc.findings.length}</summary><p>Recognition follows code references and validates linked records in this ROM. Playback and editing support are checked separately.</p>${doc.findings.map((row) => {
      const evidence2 = row.evidence || {};
      return `<div class="notice"><strong>${esc(row.label || row.family)}</strong> ${badge("Code + linked data", "good")}<p>${evidence2.song_entries !== void 0 ? `${evidence2.song_entries} song-table entries · ${evidence2.nonempty_songs} nonempty songs. ` : ""}${evidence2.anchor_count !== void 0 ? `${evidence2.anchor_count} code references agree. ` : ""}Engine version and gameplay are not certified by this scan.</p><div class="actions">${(row.locations || []).map((location2) => button("View " + location2.label, "engine-view-bytes", { id: String(location2.offset) })).join("")}</div>${/^https?:\/\//i.test(row.reference || "") ? `<a href="${esc(row.reference)}" target="_blank" rel="noreferrer noopener">Format reference</a>` : ""}</div>`;
    }).join("")}</details>`;
  }

  // romancer/ui/rom_scan.js
  async function ensureRomScan(ctx2, rescan = false) {
    var _a, _b, _c;
    const { state: state2 } = ctx2;
    if (!state2.artifact || !state2.project) return;
    if (!rescan && !getSettings().autoDeepScan) return;
    const scope = selectionKey(state2);
    state2.romScans ??= {};
    if (!rescan && state2.romScans[scope]) return;
    const params = { ...ctx2.sourceParams() }, entry = { status: "SCANNING", job_id: null, result: null };
    state2.romScans[scope] = entry;
    while (Object.keys(state2.romScans).length > 8) delete state2.romScans[Object.keys(state2.romScans)[0]];
    const repaint = () => {
      var _a2;
      if (selectionKey(state2) !== scope || ((_a2 = state2.romScans) == null ? void 0 : _a2[scope]) !== entry) return;
      const node = document.getElementById("rom-scan-panel");
      if (node) node.outerHTML = panel(ctx2, entry);
    };
    repaint();
    try {
      const start = await ctx2.api.call("rom.scan.start", { ...params, rescan });
      entry.job_id = start.job_id;
      if (start.status === "READY") entry.result = start.result;
      else {
        repaint();
        while (!entry.result) {
          if (((_a = state2.romScans) == null ? void 0 : _a[scope]) !== entry) return;
          const job = await ctx2.api.call("jobs.get", { job_id: start.job_id });
          if (["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(job.status)) {
            if (job.status !== "COMPLETED" || !((_b = job.result) == null ? void 0 : _b.ok)) throw Error(((_c = job.result) == null ? void 0 : _c.error) || "Scan " + job.status.toLowerCase());
            entry.result = job.result;
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
      }
      entry.status = "READY";
    } catch (error) {
      entry.status = "ERROR";
      entry.error = error.message;
    }
    repaint();
  }
  function scanControls(ctx2) {
    var _a;
    if (!ctx2.state.artifact) return "";
    registerCheatNavigation(ctx2);
    registerEngineNavigation(ctx2);
    registerVerificationNavigation(ctx2);
    const scope = selectionKey(ctx2.state), current2 = () => selectionKey(ctx2.state) === scope;
    ctx2.use({
      "graphics-index-play": () => ctx2.navigate("playtest"),
      "structure-inspect": (node) => {
        var _a2, _b, _c, _d;
        if (!current2()) return;
        const offset = Number(node.dataset.id);
        if (!((_d = (_c = (_b = (_a2 = ctx2.state.romScans) == null ? void 0 : _a2[scope]) == null ? void 0 : _b.result) == null ? void 0 : _c.structures) == null ? void 0 : _d.candidates.some((c) => c.offset === offset))) throw Error("Rescan this ROM first.");
        ctx2.state.resourceJump = offset;
        return ctx2.navigate("resources");
      },
      "sound-index-open": () => ctx2.navigate("sound"),
      "graphics-index-view": async (node) => {
        var _a2, _b, _c;
        if (!current2()) return;
        const index = (_c = (_b = (_a2 = ctx2.state.romScans) == null ? void 0 : _a2[scope]) == null ? void 0 : _b.result) == null ? void 0 : _c.graphics_index, offset = Number(node.dataset.id);
        if (!index || ![...index.banks.map((b) => b.offset), ...index.repeated_patterns.flatMap((p) => p.offsets)].includes(offset)) throw Error("Rescan the graphics index first.");
        ctx2.state.resourceJump = offset;
        await ctx2.navigate("resources");
      },
      "rom-rescan": () => {
        if (!current2()) return;
        return ensureRomScan(ctx2, true);
      },
      "rom-scan-cancel": async () => {
        var _a2;
        if (!current2()) return;
        const entry = (_a2 = ctx2.state.romScans) == null ? void 0 : _a2[scope];
        if (entry == null ? void 0 : entry.job_id) await ctx2.api.call("jobs.cancel", { job_id: entry.job_id });
      },
      "rom-scan-filter": () => {
        var _a2;
        if (!current2()) return;
        ctx2.state.romScanQuery = read("rom-scan-query").trim();
        const node = document.getElementById("rom-scan-panel");
        if (node) node.outerHTML = panel(ctx2, (_a2 = ctx2.state.romScans) == null ? void 0 : _a2[scope]);
      },
      "rom-scan-inspect": async (node) => {
        var _a2, _b;
        if (!current2()) return;
        const entry = (_a2 = ctx2.state.romScans) == null ? void 0 : _a2[scope], offset = Number(node.dataset.id);
        if (!((_b = entry == null ? void 0 : entry.result) == null ? void 0 : _b.candidates.some((c) => c.offset === offset))) throw Error("Rescan this selected ROM first.");
        ctx2.state.resourceJump = offset;
        await ctx2.navigate("resources");
      }
    });
    return panel(ctx2, (_a = ctx2.state.romScans) == null ? void 0 : _a[scope]);
  }
  function panel(ctx2, entry) {
    var _a, _b, _c, _d;
    const result = entry == null ? void 0 : entry.result, model = result == null ? void 0 : result.identification, known = model == null ? void 0 : model.profile, refs = (_a = result == null ? void 0 : result.catalog) == null ? void 0 : _a.file, matched = (refs == null ? void 0 : refs.status) === "MATCHED" ? (_b = refs.matches[0]) == null ? void 0 : _b.name : null;
    const query = ((_c = ctx2.state.romScanQuery) == null ? void 0 : _c.toLowerCase()) || "", candidates = ((result == null ? void 0 : result.candidates) || []).filter((c) => !query || [c.kind, c.preview, c.format, c.offset.toString(16)].join(" ").toLowerCase().includes(query));
    return `<section class="card" id="rom-scan-panel"><div class="card-heading"><h3>ROM investigation</h3>${(entry == null ? void 0 : entry.status) === "SCANNING" ? badge("Scanning", "warm") + button("Cancel scan", "rom-scan-cancel", { disabled: !entry.job_id }) : button("Rescan ROM", "rom-rescan", { icon: "search" })}</div>${(entry == null ? void 0 : entry.status) === "ERROR" ? `<p class="notice warm">${esc(entry.error)}</p>` : !result ? '<p class="subtle">' + (getSettings().autoDeepScan ? "Automatic offline identification and resource scan. You can keep working." : "Automatic deep scan is off in Settings. Choose Rescan ROM to investigate this file.") + "</p>" : `<p><strong>${known ? esc(known.name) + (model.status === "MATCHED" ? " · exact revision" : " · based on matched source") : matched ? esc(matched) + " · local catalog match" : esc(((_d = result.system_id) == null ? void 0 : _d.toUpperCase()) || "Unresolved system") + " · game revision unknown"}</strong></p><p class="subtle">${result.health ? "CRC32 " + esc(result.health.crc32) + " · " : ""}${size(result.coverage.file_bytes_read)} of ${size(result.coverage.file_size)} read. ${result.coverage.whole_file_read ? "Whole file covered." : "Partial coverage."} Candidate meanings need confirmation.</p>${verificationResults(result.health)}${graphicsIndex(ctx2, result.graphics_index)}${soundIndex(result.sound_system, result.engine_recognition)}${engineFindings(result.engine_recognition)}${cheatClues(result.cheat_references)}${structureIndex(result.structures)}<details><summary>Discoveries · ${Object.entries(result.counts).map(([kind, count]) => esc(kind) + " " + count + (result.coverage.segments.some((s) => {
      var _a2;
      return (_a2 = s[kind]) == null ? void 0 : _a2.results_truncated;
    }) ? "+" : "")).join(" · ")}</summary><p>Showing up to ${result.coverage.result_limit_per_kind} results per kind. Graphics are sampled; compressed streams have work limits. Exact mapped game edits are in Overview.</p><div class="toolbar">${field("rom-scan-query", "Filter discoveries", ctx2.state.romScanQuery || "", { placeholder: "text, codec, offset or preview" })}${button("Filter", "rom-scan-filter")}</div>${candidates.length ? `<div class="table-wrap"><table><thead><tr><th>Location</th><th>Candidate</th><th>Preview</th><th></th></tr></thead><tbody>${candidates.slice(0, 20).map((c) => `<tr><td><code>0x${c.offset.toString(16).toUpperCase()}</code></td><td>${esc(c.kind)}<br><small>${esc(c.confidence)}</small></td><td>${esc(c.preview)}</td><td>${button("View bytes", "rom-scan-inspect", { id: String(c.offset) })}</td></tr>`).join("")}</tbody></table></div><p class="subtle">${Math.min(20, candidates.length)} of ${candidates.length} stored discoveries. Filter to narrow results.</p>` : "<p>No matching candidates. Custom encodings and layouts need a definition.</p>"}<details><summary>Coverage and limits</summary>${result.limits.map((note) => `<p>${esc(note)}</p>`).join("")}<p>${result.coverage.segments.filter((s) => {
      var _a2, _b2;
      return (_b2 = (_a2 = s.compression) == null ? void 0 : _a2.compression) == null ? void 0 : _b2.partial;
    }).length} windows reached the compressed-stream work budget.</p></details></details>`}</section>`;
  }
  function graphicsIndex(ctx2, index) {
    var _a, _b;
    if (!index || index.status !== "STORAGE_CANDIDATES") return "";
    const scope = selectionKey(ctx2.state), observed = (_b = (_a = ctx2.state.graphicsInvestigations) == null ? void 0 : _a[scope]) == null ? void 0 : _b.result;
    return `<div class="graphics-index"><h4>Graphics organization</h4><p>${index.sampled_cells} stored cells sampled · stride ${index.cell_sampling_stride} · ${esc(index.codec)}</p><p>${observed ? "Gameplay candidates available" : "Waiting for gameplay"} · ${button("Investigate in Playtest", "graphics-index-play")}</p><details><summary>Storage banks and repeated patterns</summary><p>Storage groups are candidates. Byte-identical data can suggest reuse; it does not prove shared game objects or palette ownership.</p><table><thead><tr><th>Bank range</th><th>Nonflat samples</th><th></th></tr></thead><tbody>${index.banks.slice(0, 8).map((bank) => `<tr><td><code>0x${bank.offset.toString(16).toUpperCase()}</code> · ${size(bank.length)}</td><td>${bank.sampled_nonflat_cells}</td><td>${button("View bank", "graphics-index-view", { id: String(bank.offset) })}</td></tr>`).join("")}</tbody></table><p>${index.repeated_patterns.length} repeated-pattern groups stored (up to32).</p>${index.repeated_patterns.slice(0, 8).map((pattern) => `<p>${pattern.count} byte-identical cells · ${pattern.offsets.map((offset) => button("0x" + offset.toString(16).toUpperCase(), "graphics-index-view", { id: String(offset) })).join(" ")}</p>`).join("")}<p class="subtle">Initial indexing assumes tile alignment and samples up to65,536cells. Gameplay matching searches every byte alignment in each requested range.</p></details></div>`;
  }
  function soundIndex(info, recognition) {
    var _a;
    if (!info) return "";
    const recognized = (recognition == null ? void 0 : recognition.status) === "MATCH" ? (_a = recognition.findings) == null ? void 0 : _a[0] : null;
    return `<div><h4>Sound hardware & driver</h4><p>${esc(info.hardware.name)}</p><p>Driver: ${recognized ? esc(recognized.label) + " · structure recognized" : esc(info.driver.name) + " · " + esc(info.driver.status)}</p>${button("Open music & sound", "sound-index-open")}</div>`;
  }
  function structureIndex(data) {
    var _a;
    if (!((_a = data == null ? void 0 : data.candidates) == null ? void 0 : _a.length)) return "";
    return `<details><summary>Numeric address candidates · ${data.candidates.length}</summary><p>Numeric words that fall inside supported ROM address windows. A pointer dereference or game purpose has not been observed. Showing up to64 results from bounded sampled windows.</p>${data.candidates.slice(0, 16).map((c) => `<p>${button("0x" + c.offset.toString(16), "structure-inspect", { id: String(c.offset) })} stores 0x${c.stored_value.toString(16)} · possible file offset 0x${c.target_offset.toString(16)}</p>`).join("")}</details>`;
  }

  // romancer/ui/playback_controls.js
  var defaultKeys2 = { up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight", a: "z", b: "x", start: "Enter", select: "Shift" };
  function padForSelection(pads, selection2 = -1) {
    if (selection2 === -2) return null;
    if (selection2 === -1) return [...pads].find((p) => (p == null ? void 0 : p.connected) !== false && p) || null;
    return [...pads].find((p) => (p == null ? void 0 : p.index) === selection2 && p.connected !== false) || null;
  }
  function controllerButtons(pad) {
    var _a, _b, _c, _d, _e, _f;
    if (!pad) return [];
    const names4 = ["b", "a", "y", "x", "l", "r", null, null, "select", "start", null, null, "up", "down", "left", "right"], result = [];
    for (let i = 0; i < names4.length; i++) if (names4[i] && ((_b = (_a = pad.buttons) == null ? void 0 : _a[i]) == null ? void 0 : _b.pressed)) result.push(names4[i]);
    if (((_c = pad.axes) == null ? void 0 : _c[0]) < -0.35) result.push("left");
    if (((_d = pad.axes) == null ? void 0 : _d[0]) > 0.35) result.push("right");
    if (((_e = pad.axes) == null ? void 0 : _e[1]) < -0.35) result.push("up");
    if (((_f = pad.axes) == null ? void 0 : _f[1]) > 0.35) result.push("down");
    return [...new Set(result)];
  }
  function stopPlayback(state2) {
    var _a, _b;
    state2.playbackTicket = (state2.playbackTicket || 0) + 1;
    state2.playing = false;
    state2.heldButtons = [];
    (_a = state2.liveAudio) == null ? void 0 : _a.stop();
    (_b = state2.controlAbort) == null ? void 0 : _b.abort();
    state2.controlAbort = null;
  }
  function mountController(ctx2) {
    var _a;
    const control = document.getElementById("runtime-controller");
    if (!control) return;
    (_a = ctx2.state.controlAbort) == null ? void 0 : _a.abort();
    const abort = new AbortController();
    ctx2.state.controlAbort = abort;
    const options = { signal: abort.signal };
    const release = () => {
      ctx2.state.heldButtons = [];
      if (ctx2.state.playing) {
        stopPlayback(ctx2.state);
        ctx2.render();
      }
    };
    control.addEventListener("keydown", (event) => {
      var _a2;
      if (event.target !== control) return;
      const map = ((_a2 = ctx2.state.profile) == null ? void 0 : _a2.input_map) || defaultKeys2, key3 = Object.keys(map).find((k) => map[k] === event.key);
      if (key3) {
        event.preventDefault();
        ctx2.state.heldButtons = [.../* @__PURE__ */ new Set([...ctx2.state.heldButtons || [], key3])];
      }
    }, options);
    control.addEventListener("keyup", (event) => {
      var _a2;
      const map = ((_a2 = ctx2.state.profile) == null ? void 0 : _a2.input_map) || defaultKeys2, key3 = Object.keys(map).find((k) => map[k] === event.key);
      if (key3) {
        event.preventDefault();
        ctx2.state.heldButtons = (ctx2.state.heldButtons || []).filter((k) => k !== key3);
      }
    }, options);
    control.addEventListener("blur", release, options);
    window.addEventListener("blur", release, options);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) release();
    }, options);
  }

  // romancer/ui/graphics_investigation.js
  function comparePlacements(before, after) {
    var _a, _b, _c, _d;
    if (!(before == null ? void 0 : before.matches) || !(after == null ? void 0 : after.matches) || ((_a = before.coverage) == null ? void 0 : _a.offset) !== ((_b = after.coverage) == null ? void 0 : _b.offset) || ((_c = before.coverage) == null ? void 0 : _c.bytes_scanned) !== ((_d = after.coverage) == null ? void 0 : _d.bytes_scanned)) return null;
    const keys2 = (result) => new Set(result.matches.slice(0, 256).map((m) => [m.offset, m.x, m.y, m.height, !!m.flip_x, !!m.flip_y].join(":"))), a = keys2(before), b = keys2(after);
    return { added: [...b].filter((k) => !a.has(k)).length, absent: [...a].filter((k) => !b.has(k)).length, retained: [...b].filter((k) => a.has(k)).length, semantic_ownership_known: false };
  }
  function candidateGroups(result, height) {
    const groups = /* @__PURE__ */ new Map();
    ((result == null ? void 0 : result.matches) || []).forEach((match, index) => {
      if (match.height !== height) return;
      const key3 = [match.x, match.y, match.height].join(":");
      if (!groups.has(key3)) groups.set(key3, { x: match.x, y: match.y, height, choices: [] });
      groups.get(key3).choices.push({ index, ...match });
    });
    return [...groups.values()].sort((a, b) => a.y - b.y || a.x - b.x);
  }
  async function ensureGraphicsObservation(ctx2, { force = false, region = null, offset = 0, length = null } = {}) {
    var _a, _b, _c, _d, _e;
    if (!force && !getSettings().autoGraphics) return;
    const { state: state2 } = ctx2;
    if (state2.page !== "playtest" || state2.playing || !state2.runtime || !state2.frame || !((_a = state2.artifact) == null ? void 0 : _a.size)) return;
    if (state2.runtime.game_sha256 && state2.runtime.game_sha256 !== state2.artifact.sha256) return;
    const scope = selectionKey(state2), frame = state2.frame, session = state2.runtime.session_dir, params = { ...ctx2.sourceParams() }, sourceSize = state2.artifact.size;
    region = region ? { ...region } : null;
    state2.graphicsInvestigations ??= {};
    const previous = state2.graphicsInvestigations[scope];
    if (!force && ((previous == null ? void 0 : previous.status) === "SCANNING" || (previous == null ? void 0 : previous.frame_sha256) === state2.frame.sha256)) return;
    if (force && (previous == null ? void 0 : previous.status) === "SCANNING" && previous.job_id) await ctx2.api.call("jobs.cancel", { job_id: previous.job_id });
    if (selectionKey(state2) !== scope || state2.playing || ((_b = state2.frame) == null ? void 0 : _b.sha256) !== frame.sha256 || ((_c = state2.runtime) == null ? void 0 : _c.session_dir) !== session) return;
    const entry = { status: "SCANNING", frame_sha256: frame.sha256, result: null, job_id: null, session, region };
    state2.graphicsInvestigations[scope] = entry;
    while (Object.keys(state2.graphicsInvestigations).length > 8) delete state2.graphicsInvestigations[Object.keys(state2.graphicsInvestigations)[0]];
    const owned = () => {
      var _a2;
      return ((_a2 = state2.graphicsInvestigations) == null ? void 0 : _a2[scope]) === entry;
    };
    const repaint = () => {
      if (!owned() || selectionKey(state2) !== scope) return;
      const node = document.getElementById("graphics-investigation");
      if (node) node.outerHTML = graphicsInvestigation(ctx2);
    };
    repaint();
    try {
      const submitted = await ctx2.api.call("jobs.submit", { operation: "graphics.observe", parameters: { ...params, frame_sha256: entry.frame_sha256, region, offset, length: length ?? sourceSize - offset } });
      entry.job_id = submitted.job_id;
      if (!owned()) {
        await ctx2.api.call("jobs.cancel", { job_id: entry.job_id });
        return;
      }
      repaint();
      while (owned()) {
        const job = await ctx2.api.call("jobs.get", { job_id: entry.job_id });
        if (["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(job.status)) {
          if (job.status !== "COMPLETED" || !((_d = job.result) == null ? void 0 : _d.ok)) throw Error(((_e = job.result) == null ? void 0 : _e.error) || "Graphics scan " + job.status.toLowerCase());
          entry.result = job.result;
          entry.status = "READY";
          if ((previous == null ? void 0 : previous.session) === session && JSON.stringify(previous.region) === JSON.stringify(region)) entry.placementComparison = comparePlacements(previous.result, entry.result);
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    } catch (error) {
      entry.status = "ERROR";
      entry.error = error.message;
    }
    repaint();
  }
  function graphicsInvestigation(ctx2) {
    var _a, _b, _c, _d, _e;
    const { state: state2 } = ctx2;
    if (!state2.artifact) return "";
    const scope = selectionKey(state2), current2 = () => selectionKey(state2) === scope, entry = (_a = state2.graphicsInvestigations) == null ? void 0 : _a[scope], result = entry == null ? void 0 : entry.result;
    const partHeight = ((result == null ? void 0 : result.matches.some((m) => m.height === state2.graphicsPartHeight)) ? state2.graphicsPartHeight : null) || ((result == null ? void 0 : result.matches.some((m) => m.height === 16)) ? 16 : 8), allGroups = candidateGroups(result, partHeight), groups = allGroups.slice(0, 16), coverage = result == null ? void 0 : result.coverage;
    ctx2.use({
      "graphics-show-region": async () => {
        if (!current2()) return;
        stopPlayback(state2);
        state2.graphicsRegionOpen = true;
        await ctx2.render();
        const node = document.getElementById("visual-checkpoints");
        if (node) {
          node.open = true;
          node.scrollIntoView({ block: "start" });
        }
      },
      "graphics-analyze": () => {
        var _a2;
        if (!current2()) return;
        stopPlayback(state2);
        const selected2 = state2.visualRegion;
        if (!selected2 || selected2.scope !== scope || selected2.frame_sha256 !== ((_a2 = state2.frame) == null ? void 0 : _a2.sha256)) throw Error("Select a region in the captured frame below first.");
        return ensureGraphicsObservation(ctx2, { force: true, region: selected2.region, offset: Number(read("graphics-offset")), length: Number(read("graphics-length")) });
      },
      "graphics-analyze-frame": () => {
        if (!current2()) return;
        stopPlayback(state2);
        return ensureGraphicsObservation(ctx2, { force: true, offset: Number(read("graphics-offset")), length: Number(read("graphics-length")) });
      },
      "graphics-next": () => {
        if (!current2() || !coverage) return;
        return ensureGraphicsObservation(ctx2, { force: true, offset: coverage.next_offset, length: state2.artifact.size - coverage.next_offset });
      },
      "graphics-cancel": () => (entry == null ? void 0 : entry.job_id) ? ctx2.api.call("jobs.cancel", { job_id: entry.job_id }) : void 0,
      "graphics-part-height": (node) => {
        state2.graphicsPartHeight = Number(node.dataset.id);
        return ctx2.render();
      },
      "graphics-edit-candidates": async () => {
        if (!current2() || !(result == null ? void 0 : result.evidence_id)) throw Error("Analyze this selected source first.");
        const matches = groups.map((_, i) => read("graphics-choice-" + i)).filter((v) => v !== "").map(Number);
        if (!matches.length) throw Error("Choose candidate source offsets for the parts you want to edit.");
        const declared2 = await ctx2.run("graphics.declare", { ...ctx2.sourceParams(), evidence_id: result.evidence_id, matches }, { render: false });
        if (!current2()) return;
        state2.results["assets.inspect"] = declared2.inspection;
        await ctx2.navigate("assets");
        if (!current2()) return;
        const bitmap = declared2.inspection.bitmaps[0], layout = { document_id: declared2.inspection.document_id, bitmap_id: bitmap.id, ...declared2.layout };
        ctx2.setDraft("asset-schema", JSON.stringify(declared2.schema, null, 2));
        ctx2.setDraft("sprite-layout", JSON.stringify(layout));
        ctx2.setDraft("sprite-first", "0");
        ctx2.setDraft("sprite-columns", String(layout.columns));
        ctx2.setDraft("sprite-rows", String(layout.rows));
        ctx2.setDraft("sprite-order", layout.order || "rows");
        ctx2.setDraft("sprite-map", layout.indices.map((v, i) => v === null ? "." : String(v) + (layout.flips[i] & 1 ? "h" : "") + (layout.flips[i] & 2 ? "v" : "")).join(", "));
        state2.spriteHistory = null;
        await ctx2.render();
      }
    });
    return `<section class="card" id="graphics-investigation"><div class="card-heading"><h3>Gameplay graphics</h3>${(entry == null ? void 0 : entry.status) === "SCANNING" ? button("Cancel analysis", "graphics-cancel", { disabled: !entry.job_id }) : ""}</div><p>Import scanning indexes tile storage. Paused gameplay adds pixel matches without a game definition.</p>
 ${(entry == null ? void 0 : entry.status) === "SCANNING" ? '<p role="status">Analyzing captured pixels and source bytes. Playback and navigation remain available.</p>' : (entry == null ? void 0 : entry.status) === "ERROR" ? `<p class="notice warm">${esc(entry.error)}</p>` : !result ? '<p class="subtle">Play to a useful screen, then pause. A bounded scan starts automatically.</p>' : `<p><strong>${result.matches.length} pixel candidates · source use unproven</strong></p><p class="subtle">${size(coverage.bytes_scanned)} examined from 0x${coverage.offset.toString(16).toUpperCase()} · ${coverage.whole_source ? "whole source range" : "partial source range"}. Frame positions may be sampled; repeated or unseen alternatives remain unresolved.</p>${((_b = result.frame) == null ? void 0 : _b.sha256) !== ((_c = state2.frame) == null ? void 0 : _c.sha256) ? '<p class="notice warm">These candidates describe an earlier captured frame.</p>' : ""}
 ${entry.placementComparison ? `<p>${entry.placementComparison.added} candidate placements added · ${entry.placementComparison.absent} absent compared with the previous capture. This does not identify animation ownership.</p>` : ""}<div class="actions">${button("8 × 8 tiles", "graphics-part-height", { id: "8" })}${result.matches.some((m) => m.height === 16) ? button("8 × 16 parts", "graphics-part-height", { id: "16" }) : ""}${coverage.next_offset < state2.artifact.size ? button("Continue ROM range", "graphics-next", { disabled: state2.playing }) : ""}</div>
 ${groups.length ? `<p>${allGroups.length > 16 ? "Select a smaller object region above; this frame contains too many placements for one editing layout." : "Choose source candidates to assemble."} A single result in this search does not establish a unique source.</p>${allGroups.length > 16 ? "<details><summary>Sample placements</summary>" : ""}<div class="table-wrap"><table><thead><tr><th>Frame placement</th><th>Candidate source</th></tr></thead><tbody>${groups.slice(0, 64).map((group, i) => `<tr><td>${group.x}, ${group.y} ·8×${group.height}</td><td>${select("graphics-choice-" + i, "Part " + (i + 1), [["", "Choose a source offset"], ...group.choices.map((m) => [String(m.index), "0x" + m.offset.toString(16).toUpperCase() + (m.flip_x ? " · flip H" : "") + (m.flip_y ? " · flip V" : "")])], group.choices.length === 1 ? String(group.choices[0].index) : "")}</td></tr>`).join("")}</tbody></table></div>${button("Load candidate layout", "graphics-edit-candidates", { primary: true, disabled: state2.playing || allGroups.length > 16 })}${allGroups.length > 16 ? "</details>" : ""}` : "<p>No informative literal parts found. Try a smaller region or another ROM range. Compression and RAM-generated graphics need additional tracing.</p>"}<details><summary>Analysis evidence and limits</summary><p>Frame ${esc((_d = result.frame) == null ? void 0 : _d.index)} · <code>${esc((_e = result.frame) == null ? void 0 : _e.sha256)}</code></p>${(result.limits || []).map((v) => `<p>${esc(v)}</p>`).join("")}</details>`}
 <details><summary>Focused analysis</summary><p>Use the captured-frame region selector above to isolate an object, then analyze that region. Coordinates and source offsets stay explicit.</p><div class="field-row">${field("graphics-offset", "ROM start offset", ctx2.draft("graphics-offset", "0"))}${field("graphics-length", "ROM bytes to request", ctx2.draft("graphics-length", String(state2.artifact.size || 1)))}</div><div class="actions">${button("Analyze selected region", "graphics-analyze", { disabled: !state2.frame })}${button("Analyze whole frame", "graphics-analyze-frame", { disabled: !state2.frame || (entry == null ? void 0 : entry.status) === "SCANNING" })}</div><p class="subtle">Each background job examines up to512KiB, at every byte alignment. More ranges can be scanned without blocking the editor.</p></details></section>`;
  }

  // romancer/ui/project_manager.js
  function newProjectForm(name = "") {
    return `<p>A separate workspace for your sources, builds and discoveries.</p><label class="field"><span>Project name</span><input id="new-project-name" value="${esc(name)}" maxlength="120" placeholder="My ROM project" required></label><div class="actions">${button("Create & import ROM", "create-project-import", { primary: true, icon: "plus" })}${button("Create empty project", "create-project")}</div>`;
  }
  function projectActions(ctx2) {
    const { state: state2 } = ctx2;
    const create = async (withImport) => {
      const project = await ctx2.api.call("project.create", { name: read("new-project-name").trim() });
      ctx2.closeModal();
      await ctx2.openProject(project.project_id);
      if (withImport) await ctx2.importDialog();
    };
    const manager = async () => {
      const [live, trash] = await Promise.all([ctx2.api.call("projects.list", {}), ctx2.api.call("projects.trash", {})]);
      state2.projects = live.projects;
      ctx2.modal("Projects", `<div class="actions">${button("New project", "new-project", { primary: true, icon: "plus" })}</div>${live.projects.length ? live.projects.map((p) => `<div class="resource-row"><div class="resource-meta"><strong>${esc(p.name)}</strong><small>${p.sources.length} sources · ${p.builds.length} builds</small></div><div class="actions">${button("Open", "manager-open", { id: p.project_id })}${button("Delete project", "manager-delete", { id: p.project_id })}</div></div>`).join("") : "<p>No projects yet.</p>"}<details><summary>Trash · ${trash.projects.length}</summary><p>Restore a deleted project with its sources and builds intact.</p>${trash.projects.map((p) => `<div class="resource-row"><strong class="resource-meta">${esc(p.name)}</strong>${button("Restore", "manager-restore", { id: p.trash_id })}</div>`).join("") || "<p>Trash is empty.</p>"}</details>`);
    };
    return {
      "new-project": () => {
        var _a, _b;
        return ctx2.modal("New project", newProjectForm(((_b = (_a = state2.droppedImportFile) == null ? void 0 : _a.name) == null ? void 0 : _b.replace(/\.[^.]+$/, "")) || ""));
      },
      "create-project": () => create(false),
      "create-project-import": () => create(true),
      "projects-manage": manager,
      "manager-open": async (node) => {
        ctx2.closeModal();
        await ctx2.openProject(node.dataset.id);
      },
      "manager-delete": async (node) => {
        const result = await ctx2.api.call("projects.list", {}), p = result.projects.find((p2) => p2.project_id === node.dataset.id);
        if (!p) throw Error("Project is no longer available.");
        ctx2.modal("Delete project?", `<p>Move <strong>${esc(p.name)}</strong> and its project files to Trash?</p><p>Your original ROM files stay where they are. You can restore this project from Projects → Trash.</p><div class="actions">${button("Move to Trash", "manager-delete-confirm", { id: p.project_id })}${button("Keep project", "projects-manage", { primary: true })}</div>`);
      },
      "manager-delete-confirm": async (node) => {
        var _a;
        await ctx2.flushDrafts();
        if (((_a = state2.project) == null ? void 0 : _a.project_id) === node.dataset.id) await ctx2.closeProject();
        await ctx2.api.call("project.delete", { project_id: node.dataset.id });
        await ctx2.refreshProject();
        await ctx2.render();
        await manager();
        ctx2.notify("Project moved to Trash.");
      },
      "manager-restore": async (node) => {
        await ctx2.api.call("project.undelete", { trash_id: node.dataset.id });
        await ctx2.refreshProject();
        await ctx2.render();
        await manager();
        ctx2.notify("Project restored.");
      }
    };
  }

  // romancer/ui/project_flow.js
  function selectionTicket(state2) {
    state2.selectionRevision = (state2.selectionRevision || 0) + 1;
    return state2.selectionRevision;
  }
  function selectionCurrent(state2, ticket) {
    return state2.selectionRevision === ticket;
  }
  function releaseProjectResources(state2) {
    var _a, _b;
    state2.gameVisualModel = null;
    (_a = state2.animationClock) == null ? void 0 : _a.stop();
    state2.animationClock = null;
    state2.animationPlaying = false;
    state2.animationIndex = 0;
    state2.valueSearch = null;
    state2.valueVideo = null;
    (_b = state2.soundPlayer) == null ? void 0 : _b.close();
    state2.soundPlayer = null;
    state2.soundPreview = null;
    for (const key3 of ["investigationSeries", "gameMapsView", "gameMapEditor", "levelEditor", "levelClipboard", "levelRect", "paint", "pixelHistories", "pixelHistoryScope", "spriteHistory", "hexDraft", "hexReview", "hexSearch", "hexNumbers", "hexExplanation", "hexBookmarks", "hexComparison", "historyComparison", "translationSheet", "translationReview"]) state2[key3] = null;
    state2.drafts = {};
    state2.romScans = {};
    state2.graphicsInvestigations = {};
    state2.graphicsPartHeight = null;
    state2.graphicsRegionOpen = false;
    state2.results = {};
  }
  function clearProjectState(state2) {
    selectionTicket(state2);
    releaseProjectResources(state2);
    for (const key3 of ["project", "artifact", "runtime", "frame", "snapshot", "pending", "paint", "profileFamily", "profileLoadedFamily", "candidateReview", "resourcePrefill", "openDeclaration"]) state2[key3] = null;
    state2.results = {};
    state2.playing = false;
    state2.heldButtons = [];
    state2.page = "overview";
    state2.scriptPage = 0;
    state2.assetPage = 0;
    state2.catalogPage = 0;
    state2.catalogQuery = "";
  }
  function droppedSource(files) {
    if (!files || files.length !== 1) throw new Error("Drop one file at a time.");
    const file = files[0];
    if (!Number.isSafeInteger(file.size) || file.size < 1) throw new Error("The selected file is empty. Choose a ROM file.");
    if (file.size > 64 * 1024 * 1024) throw new Error("Files larger than64 MiB need Advanced path import.");
    return file;
  }
  function helpForError(message) {
    const text = String(message).toLowerCase();
    if (/old.byte|precondition/.test(text)) return { topic: "discovery", label: "Check source bytes" };
    if (/core|bios|playtest|native|architecture/.test(text)) return { topic: "playtest", label: "Playtest setup help" };
    if (/stale|revision|changed|lock|draft|backup|restore/.test(text)) return { topic: "recovery", label: "Recovery help" };
    if (/text|slot|encoding|terminator|control|overflow/.test(text)) return { topic: "text", label: "Text editing help" };
    if (/table|record|numeric|stride|integer/.test(text)) return { topic: "tables", label: "Data table help" };
    if (/palette|pixel|tile|graphic|glyph/.test(text)) return { topic: "graphics", label: "Graphics help" };
    if (/compression|lz10|rle|allocation/.test(text)) return { topic: "compression", label: "Compression help" };
    if (/patch|bps|export/.test(text)) return { topic: "export", label: "Patch export help" };
    return { topic: "start", label: "Open help" };
  }
  var DraftQueue = class {
    constructor(onChange = () => {
    }) {
      this.pending = /* @__PURE__ */ new Map();
      this.failed = /* @__PURE__ */ new Map();
      this.operations = /* @__PURE__ */ new Map();
      this.onChange = onChange;
    }
    snapshot() {
      return { pending: this.pending.size, failed: this.failed.size, state: this.failed.size ? "failed" : this.pending.size ? "saving" : "saved", unsafe: !!(this.pending.size || this.failed.size) };
    }
    changed() {
      try {
        this.onChange(this.snapshot());
      } catch {
      }
    }
    enqueue(key3, operation, onError) {
      this.operations.set(key3, { operation, onError });
      const prior = this.pending.get(key3) || Promise.resolve();
      const next = prior.then(operation).then(() => this.failed.delete(key3)).catch((error) => {
        this.failed.set(key3, error);
        try {
          onError(error);
        } catch {
        }
      });
      this.pending.set(key3, next);
      this.changed();
      void next.finally(() => {
        if (this.pending.get(key3) === next) {
          this.pending.delete(key3);
          if (!this.failed.has(key3)) this.operations.delete(key3);
        }
        this.changed();
      });
    }
    async retry() {
      for (const key3 of this.failed.keys()) if (!this.pending.has(key3)) {
        const task = this.operations.get(key3);
        if (task) this.enqueue(key3, task.operation, task.onError);
      }
      await this.flush();
    }
    async flush() {
      while (this.pending.size) await Promise.all([...this.pending.values()]);
      if (this.failed.size) throw Error("Draft not saved. Your unsaved edits are still here. Retry saving before changing source or project.");
    }
    clear() {
      if (this.pending.size || this.failed.size) throw Error("Unsaved edits must be saved before clearing drafts.");
      this.failed.clear();
      this.operations.clear();
      this.changed();
    }
  };

  // romancer/ui/tutorial.js
  function renderHub(data) {
    const lessons = (data == null ? void 0 : data.lessons) || [], progress = (data == null ? void 0 : data.progress) || {};
    return `<p>Short, optional lessons. Checks mark finished lessons; skipped lessons stay unchecked.</p><div class="grid-even">${["Basic", "Advanced"].map((section) => `<section class="card"><h2>${section}</h2>${lessons.filter((l) => l.section === section).map((lesson) => {
      const status = progress[lesson.id], done = status === "completed";
      return `<div class="lesson-row"><span class="lesson-check ${done ? "complete" : ""}" aria-label="${done ? "Completed" : status === "skipped" ? "Skipped" : "Not started"}">${done ? "✓" : status === "skipped" ? "–" : "○"}</span><div class="resource-meta"><strong>${esc(lesson.title)}</strong><small>${lesson.steps.length} steps${status === "skipped" ? " · Skipped" : ""}</small></div>${button(done ? "Replay" : "Start", "tutorial-start", { id: lesson.id })}</div>`;
    }).join("")}</section>`).join("")}</div>`;
  }
  function createTutorial(ctx2) {
    const { state: state2 } = ctx2;
    state2.tutorial = null;
    let busy = false, revision = 0, lastHighlight = "";
    const lesson = () => {
      var _a;
      return (_a = state2.tutorialData) == null ? void 0 : _a.lessons.find((l) => {
        var _a2;
        return l.id === ((_a2 = state2.tutorial) == null ? void 0 : _a2.lesson_id);
      });
    };
    async function dismissPrompt(openHub2) {
      var _a;
      const checked = ((_a = document.getElementById("tutorial-never")) == null ? void 0 : _a.checked) === true;
      try {
        state2.tutorialData = await ctx2.api.call("tutorial.preferences", { never_ask_again: checked });
      } finally {
        ctx2.closeModal();
      }
      if (openHub2) await ctx2.navigate("tutorials");
    }
    async function init() {
      var _a;
      try {
        state2.tutorialData = await ctx2.api.call("tutorial.get");
        if (state2.tutorialData.prompt && !((_a = document.getElementById("modal")) == null ? void 0 : _a.open)) ctx2.modal("A quick tour?", `<p>Four short lessons. Start with Basic, or explore Advanced.</p><label class="tutorial-choice"><input type="checkbox" id="tutorial-never">Never ask again</label><div class="actions">${button("Start tutorial", "tutorial-accept", { primary: true })}${button("Not now", "tutorial-decline")}</div>`);
      } catch {
        ctx2.notify("Tutorials are unavailable right now. Your workspace is ready.");
      }
    }
    async function start(id) {
      var _a, _b, _c, _d;
      if (busy) return;
      if (state2.tutorial) throw Error("Finish or skip the current lesson first.");
      const selected2 = (_a = state2.tutorialData) == null ? void 0 : _a.lessons.find((l) => l.id === id);
      if (!selected2) throw Error("Choose a lesson from Tutorials.");
      busy = true;
      const request2 = ++revision, ticket = selectionTicket(state2), previous = ((_b = state2.project) == null ? void 0 : _b.project_id) || null, previousArtifact = ((_c = state2.artifact) == null ? void 0 : _c.artifact_id) || null;
      try {
        const practice = await ctx2.api.call("tutorial.practice");
        if (request2 !== revision || !selectionCurrent(state2, ticket)) return;
        await ctx2.openProject(practice.project_id);
        if (request2 !== revision || ((_d = state2.project) == null ? void 0 : _d.project_id) !== practice.project_id) return;
        state2.tutorial = { lesson_id: id, step: 0, visited: [0], practice: practice.project_id, previous, previousArtifact, minimized: false };
        lastHighlight = "";
        await ctx2.navigate(selected2.steps[0].page);
      } finally {
        busy = false;
      }
    }
    async function move(direction) {
      var _a;
      const active = state2.tutorial, current2 = lesson();
      if (!active || !current2 || busy) return;
      if (((_a = state2.project) == null ? void 0 : _a.project_id) !== active.practice || state2.page !== current2.steps[active.step].page) return resume();
      const next = active.step + direction;
      if (next < 0 || next >= current2.steps.length) return;
      active.step = next;
      if (!active.visited.includes(next)) active.visited.push(next);
      await ctx2.navigate(current2.steps[next].page);
    }
    async function end(outcome) {
      var _a, _b, _c;
      const active = state2.tutorial, current2 = lesson();
      if (!active || !current2 || busy) return;
      if (outcome === "completed" && (active.step !== current2.steps.length - 1 || active.visited.length !== current2.steps.length)) throw Error("Reach the last step before finishing this lesson.");
      busy = true;
      const request2 = revision, ticket = state2.selectionRevision;
      try {
        const result = await ctx2.api.call("tutorial.progress", { lesson_id: active.lesson_id, outcome });
        if (request2 !== revision || state2.tutorial !== active) return;
        state2.tutorialData = result;
        state2.tutorial = null;
        revision++;
        if (!selectionCurrent(state2, ticket)) {
          await ctx2.render();
          return;
        }
        if (((_a = state2.project) == null ? void 0 : _a.project_id) === active.practice && active.previous && active.previous !== active.practice) {
          const restore = ctx2.openProject(active.previous), restoreTicket = state2.selectionRevision;
          await restore;
          if (!selectionCurrent(state2, restoreTicket)) {
            await ctx2.render();
            return;
          }
          if (active.previousArtifact && ((_b = state2.artifact) == null ? void 0 : _b.artifact_id) !== active.previousArtifact) await ctx2.setArtifact(active.previousArtifact);
          if (!selectionCurrent(state2, restoreTicket)) {
            await ctx2.render();
            return;
          }
        } else if (((_c = state2.project) == null ? void 0 : _c.project_id) === active.practice && !active.previous) {
          await ctx2.closeProject();
        }
        await ctx2.navigate("tutorials");
      } finally {
        busy = false;
      }
    }
    async function resume() {
      var _a, _b;
      const active = state2.tutorial, current2 = lesson();
      if (!active || !current2 || busy) return;
      if (((_a = state2.project) == null ? void 0 : _a.project_id) !== active.practice) await ctx2.openProject(active.practice);
      if (state2.tutorial !== active || ((_b = state2.project) == null ? void 0 : _b.project_id) !== active.practice) return;
      active.minimized = false;
      await ctx2.navigate(current2.steps[active.step].page);
    }
    async function openHub() {
      if (state2.tutorial) await end("skipped");
      else await ctx2.navigate("tutorials");
    }
    function bind() {
      ctx2.use({
        "tutorial-hub": openHub,
        "tutorial-accept": () => dismissPrompt(true),
        "tutorial-decline": () => dismissPrompt(false),
        "tutorial-start": (node) => start(node.dataset.id),
        "tutorial-next": () => move(1),
        "tutorial-back": () => move(-1),
        "tutorial-finish": () => end("completed"),
        "tutorial-skip": () => end("skipped"),
        "tutorial-resume": resume,
        "tutorial-toggle": async () => {
          if (state2.tutorial) {
            state2.tutorial.minimized = !state2.tutorial.minimized;
            await ctx2.render();
          }
        }
      });
    }
    function panel2() {
      var _a;
      const active = state2.tutorial, current2 = lesson();
      if (!active || !current2 || active.minimized) return "";
      const step = current2.steps[active.step], paused = ((_a = state2.project) == null ? void 0 : _a.project_id) !== active.practice || state2.page !== step.page;
      return `<aside class="tutorial-panel" aria-label="Guided tutorial"><div class="card-heading"><strong>${esc(current2.title)}</strong>${button("Minimize", "tutorial-toggle")}</div><p class="subtle">Step ${active.step + 1} of ${current2.steps.length}</p><h2 id="tutorial-title" tabindex="-1">${esc(paused ? "Lesson paused" : step.title)}</h2><p>${esc(paused ? "Resume to return to the practice workshop." : step.body)}</p><div class="actions">${paused ? button("Resume lesson", "tutorial-resume", { primary: true }) : `${button("Back", "tutorial-back", { disabled: active.step === 0 })}${active.step === current2.steps.length - 1 ? button("Finish lesson", "tutorial-finish", { primary: true }) : button("Next", "tutorial-next", { primary: true })}`}${button("Skip lesson", "tutorial-skip")}</div></aside>`;
    }
    function mount12() {
      var _a, _b;
      const active = state2.tutorial, current2 = lesson();
      document.documentElement.classList.toggle("tutorial-running", !!active && !active.minimized);
      document.querySelectorAll(".tutorial-target").forEach((node) => node.classList.remove("tutorial-target"));
      if (!active || !current2 || active.minimized || ((_a = state2.project) == null ? void 0 : _a.project_id) !== active.practice || state2.page !== current2.steps[active.step].page) return;
      const step = current2.steps[active.step], target = document.querySelector(step.target) || document.querySelector("#main .page-heading");
      if (target) {
        const detail = target.closest("details");
        if (detail) detail.open = true;
        target.classList.add("tutorial-target");
        const key3 = active.lesson_id + ":" + active.step;
        if (key3 !== lastHighlight) {
          lastHighlight = key3;
          target.scrollIntoView({ block: "center" });
          (_b = document.getElementById("tutorial-title")) == null ? void 0 : _b.focus({ preventScroll: true });
        }
      }
    }
    return { init, bind, panel: panel2, mount: mount12, dismissPrompt };
  }

  // romancer/ui/views/tutorials.js
  var tutorials_exports = {};
  __export(tutorials_exports, {
    render: () => render
  });
  async function render(ctx2) {
    ctx2.state.tutorialData = await ctx2.api.call("tutorial.get");
    return heading("", "Tutorials", "") + renderHub(ctx2.state.tutorialData);
  }

  // romancer/ui/views/automation.js
  var automation_exports = {};
  __export(automation_exports, {
    render: () => render2
  });
  async function localJSON(id, max) {
    var _a;
    const file = (_a = document.getElementById(id)) == null ? void 0 : _a.files[0];
    if (!file || file.size > max) throw new Error("Choose a JSON file within the stated limit.");
    try {
      return JSON.parse(await file.text());
    } catch {
      throw new Error("This file is not valid JSON.");
    }
  }
  async function render2(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    if (!state2.artifact) return empty("Import a ROM first", "Recipes and definitions belong to an exact source revision.");
    const saved = (await ctx2.api.call("recipes.list", ctx2.sourceParams())).recipes, plans = [...new Set([...((_a = state2.pending) == null ? void 0 : _a.artifact_id) === state2.artifact.artifact_id ? [state2.pending.plan_id] : [], ...state2.project.builds.filter((b) => b.source_id === state2.artifact.artifact_id).map((b) => b.plan_id)].filter(Boolean))];
    const selected2 = () => {
      const recipe = saved[Number(read("recipe-select"))];
      if (!recipe) throw new Error("Save or import a recipe first.");
      return recipe;
    };
    ctx2.use({
      "recipe-capture": () => ctx2.run("recipes.from_plan", { ...ctx2.sourceParams(), plan_id: read("recipe-plan"), name: read("recipe-name") }),
      "recipe-import": async () => ctx2.run("recipes.import", { ...ctx2.sourceParams(), recipe: await localJSON("recipe-file", 256 * 1024) }),
      "recipe-preview": async () => {
        const recipe = selected2(), result = await ctx2.run("recipes.preview", { ...ctx2.sourceParams(), recipe }, { render: false });
        state2.pending = { kind: "recipe", plan_id: result.plan_id, artifact_id: state2.artifact.artifact_id, recipe_id: result.recipe_id };
        return ctx2.render();
      },
      "recipe-build": async () => {
        var _a2;
        if (((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "recipe" || state2.pending.artifact_id !== state2.artifact.artifact_id) throw new Error("Preview a recipe for this source first.");
        await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: state2.pending.plan_id }, { render: false });
        state2.pending = null;
        await ctx2.render();
        ctx2.notify("Separate recipe build created.");
      },
      "recipe-export": async () => {
        const result = await ctx2.run("recipes.export", { ...ctx2.sourceParams(), recipe: selected2() }, { render: false });
        await ctx2.api.download(state2.project.project_id, result.export.export_id, "romancer-recipe.json");
        return ctx2.render();
      },
      "definition-export": async () => {
        const result = await ctx2.run("definitions.export", { ...ctx2.sourceParams(), kind: read("definition-kind") }, { render: false });
        await ctx2.api.download(state2.project.project_id, result.export.export_id, "romancer-definition.json");
        return ctx2.render();
      },
      "definition-import": async () => {
        await ctx2.run("definitions.import", { ...ctx2.sourceParams(), document: await localJSON("definition-file", 1024 * 1024) }, { render: false });
        state2.results = {};
        state2.pending = null;
        await ctx2.render();
        ctx2.notify("Definition checked and loaded.");
      }
    });
    return `${heading("", "Recipes & definitions", "")}<div class="identity"><strong>${esc(state2.artifact.name)}</strong><span>Exact source revision</span></div><div class="grid-two"><section class="card"><h3>Repeat an edit</h3><p>Save a reviewed plan, then replay it on the same original.</p>${select("recipe-select", "Saved recipe", saved.map((r, i) => [i, r.name]), ctx2.draft("recipe-select", "0"))}<div class="actions">${button("Preview recipe", "recipe-preview", { primary: true, disabled: !saved.length })}${((_b = state2.pending) == null ? void 0 : _b.kind) === "recipe" ? button("Create recipe build", "recipe-build", { primary: true }) : ""}${button("Export recipe", "recipe-export", { disabled: !saved.length })}</div><details class="config"><summary>Save a plan as a recipe</summary>${field("recipe-name", "Recipe name", ctx2.draft("recipe-name", "My edits"))}${select("recipe-plan", "Reviewed plan", plans.map((id, i) => [id, "Plan " + (i + 1) + " · " + id.slice(0, 8)]), ctx2.draft("recipe-plan", plans[0]))}${button("Save recipe", "recipe-capture", { disabled: !plans.length })}</details><details class="config"><summary>Import recipe</summary><label class="field"><span>Recipe JSON, up to256KiB</span><input id="recipe-file" type="file" accept=".json,application/json"></label>${button("Check and save recipe", "recipe-import")}</details></section><section class="card"><h3>Resource definitions</h3><p>Share checked text, graphics, tables, levels or sound definitions for the same source.</p>${select("definition-kind", "Resource", [["script", "Text"], ["assets", "Graphics & fonts"], ["tables", "Data tables"], ["levels", "Levels & objects"], ["sound", "Music & sound"]], ctx2.draft("definition-kind", "script"))}${button("Export definition", "definition-export")}<label class="field"><span>Definition JSON, up to1MiB</span><input id="definition-file" type="file" accept=".json,application/json"></label>${button("Check and import definition", "definition-import")}<p class="subtle">Original files and native reports are excluded.</p></section></div>${report(state2.results["recipes.preview"], "Recipe preview")}${report(state2.results["recipes.from_plan"] || state2.results["recipes.import"], "Saved recipe")}${report(state2.results["build.apply"], "Recipe build")}`;
  }

  // romancer/ui/views/tables.js
  var tables_exports = {};
  __export(tables_exports, {
    mount: () => mount,
    render: () => render3
  });

  // romancer/ui/edit_preview.js
  function numberDelta(before, after) {
    if (typeof after === "string" && !after.trim()) throw Error("Enter a whole number.");
    const next = typeof after === "string" ? Number(after) : after;
    if (!Number.isSafeInteger(before) || !Number.isSafeInteger(next)) throw Error("Enter a whole number.");
    return { before, after: next, delta: next - before, percent: before === 0 ? null : (next - before) / Math.abs(before) * 100 };
  }
  var signed = (value) => (value > 0 ? "+" : "") + value;
  function numericBounds(type) {
    const match = /^([us])(8|16|24|32)$/.exec(type);
    if (!match) return { minimum: -Infinity, maximum: Infinity };
    const bits = Number(match[2]), signed2 = match[1] === "s";
    return { minimum: signed2 ? -(2 ** (bits - 1)) : 0, maximum: 2 ** (bits - Number(signed2)) - 1 };
  }
  function numberComparison(before, after, { minimum = -Infinity, maximum = Infinity, compact = false } = {}) {
    let d;
    try {
      d = numberDelta(before, after);
    } catch (error) {
      return `<p class="error" role="status">${esc(error.message)}</p>`;
    }
    if (compact && d.before === d.after) return `<span class="preview-caption">Original ${d.before} · unchanged</span>`;
    const max = Math.max(1, Math.abs(d.before), Math.abs(d.after)), percent = d.percent === null ? "from zero" : signed(Number(d.percent.toFixed(1))) + "%";
    return `<div class="number-comparison ${compact ? "compact" : ""}" aria-label="Stored value comparison"><div class="preview-pair">${[["Original", d.before], ["Edited", d.after]].map(([name, value]) => `<div><span>${name}</span><strong>${value}</strong><div class="value-track"><i style="width:${Math.abs(value) / max * 100}%"></i></div></div>`).join("")}</div><p class="value-delta" role="status">${d.delta === 0 ? "Unchanged" : "Preview updated"} · ${signed(d.delta)} · ${percent}</p>${d.after < minimum || d.after > maximum ? '<p class="error">Outside the declared numeric range.</p>' : ""}</div>`;
  }
  function textComparison(before, after, { columns: columns2 = 32 } = {}) {
    columns2 = Number.isSafeInteger(columns2) ? Math.max(8, Math.min(80, columns2)) : 32;
    return `<div class="text-comparison"><p class="preview-caption">System-font preview · wraps at ${columns2} characters</p><div class="preview-pair">${[["Original", before], ["Edited", after]].map(([name, text]) => `<div><span>${name}</span><div class="text-window" style="--text-columns:${columns2}ch">${esc(String(text).slice(0, 8192)) || '<span class="subtle">Empty</span>'}</div></div>`).join("")}</div><p class="preview-caption" role="status">${before === after ? "Unchanged preview" : "Preview updated"} · ${Array.from(String(after)).length} characters · game font and window require a declared layout or playtest</p></div>`;
  }
  function textCapacity(record, texts, glyphs) {
    if (!Array.isArray(glyphs) || !Number.isSafeInteger(record.used_bytes)) return { known: false };
    if (texts.length !== record.segments.length || texts.some((t) => typeof t !== "string" || t.length > 131072)) return { known: false, error: "Preview unavailable: text exceeds the supported record limit." };
    const allowed = new Set(glyphs), unmapped = /* @__PURE__ */ new Set();
    let used = record.used_bytes - record.segments.reduce((n, s) => n + s.length, 0);
    for (const text of texts) {
      let count = 0;
      for (const char of text) {
        if (++count > 65536) return { known: false, error: "Preview unavailable: text exceeds 65,536 characters." };
        used++;
        if (!allowed.has(char) && unmapped.size < 16) unmapped.add(char);
      }
    }
    return { known: true, used, capacity: record.capacity, overflow: Math.max(0, used - record.capacity), unmapped: [...unmapped].slice(0, 16) };
  }
  function capacitySummary(value) {
    if (!value.known) return `<p class="${value.error ? "error" : "preview-caption"}" role="status">${esc(value.error || "Byte capacity is checked when you review the changes.")}</p>`;
    return `<div class="capacity-summary ${value.overflow || value.unmapped.length ? "error" : ""}" role="status"><progress max="${value.capacity}" value="${Math.min(value.capacity, value.used)}"></progress><span>${value.used} / ${value.capacity} bytes${value.overflow ? " · " + value.overflow + " bytes over capacity" : value.unmapped.length ? "" : " · fits"}</span>${value.unmapped.length ? `<span>Unmapped characters: ${value.unmapped.map((c) => esc(JSON.stringify(c))).join(", ")}</span>` : ""}</div>`;
  }
  function channelMaximum(mask) {
    if (!Number.isSafeInteger(mask) || mask < 1 || mask > 4294967295) throw Error("No valid declared color channel.");
    while (mask % 2 === 0) mask /= 2;
    if (!Number.isInteger(Math.log2(mask + 1))) throw Error("Color channel mask must be contiguous.");
    return mask;
  }
  function componentRGB(components, channels) {
    return Object.fromEntries(["r", "g", "b"].map((c) => {
      const maximum = channelMaximum(channels[c]), value = components[c];
      if (!Number.isSafeInteger(value) || value < 0 || value > maximum) throw Error("Color is outside its declared storage range.");
      return [c, Math.round(value / maximum * 255)];
    }));
  }
  function quantizeColor(hex3, channels) {
    if (typeof hex3 !== "string" || !/^#[a-f0-9]{6}$/i.test(hex3)) throw Error("Choose a valid RGB color.");
    return Object.fromEntries(["r", "g", "b"].map((c, i) => [c, Math.round(parseInt(hex3.slice(1 + i * 2, 3 + i * 2), 16) / 255 * channelMaximum(channels[c]))]));
  }
  function editedPalette(palette2, changes) {
    if (!palette2) return palette2;
    if (!Array.isArray(changes) || changes.length > 4096) throw Error("Palette preview exceeds its change budget.");
    const selected2 = changes.filter((c) => c.kind === "palette" && c.palette_id === palette2.id), seen = /* @__PURE__ */ new Set();
    const entries = palette2.entries.map((entry) => {
      const matching = selected2.filter((c) => c.index === entry.index && c.bank === entry.bank);
      if (matching.length > 1) throw Error("Duplicate palette changes need review.");
      const change = matching[0];
      if (!change) return { ...entry };
      if (["r", "g", "b"].some((c) => {
        var _a;
        return ((_a = change.before) == null ? void 0 : _a[c]) !== entry.components[c];
      })) throw Error("Palette preview belongs to different original colors.");
      seen.add(change);
      return { ...entry, components: { ...change.after }, rgb: componentRGB(change.after, palette2.channels) };
    });
    if (seen.size !== selected2.length) throw Error("Palette entry is outside the declaration.");
    return { ...palette2, entries };
  }
  function editorPalette(ctx2, palette2) {
    var _a;
    try {
      return editedPalette(palette2, JSON.parse(ctx2.draft("asset-changes", "[]")));
    } catch (error) {
      const node = (_a = globalThis.document) == null ? void 0 : _a.getElementById("palette-preview-status");
      if (node) node.textContent = error.message;
      return palette2;
    }
  }
  var rgbHex = (rgb) => "#" + ["r", "g", "b"].map((c) => rgb[c].toString(16).padStart(2, "0")).join("");
  function paletteComparison(original, edited) {
    const chips = (palette2) => palette2.entries.slice(0, 256).map((e) => `<svg class="preview-swatch" viewBox="0 0 1 1" width="100%" role="img" aria-label="Bank ${e.bank}, color ${e.index}: RGB ${e.rgb.r},${e.rgb.g},${e.rgb.b}"><title>Bank ${e.bank}, color ${e.index}: RGB ${e.rgb.r},${e.rgb.g},${e.rgb.b}</title><rect width="1" height="1" fill="rgb(${e.rgb.r},${e.rgb.g},${e.rgb.b})"/></svg>`).join("");
    const changed2 = original.entries.filter((e, i) => ["r", "g", "b"].some((c) => {
      var _a;
      return e.rgb[c] !== ((_a = edited.entries[i]) == null ? void 0 : _a.rgb[c]);
    })).length;
    return `<div class="palette-comparison"><div class="preview-pair"><div><span>Original</span><div class="preview-swatches">${chips(original)}</div></div><div><span>Edited</span><div class="preview-swatches">${chips(edited)}</div></div></div><p class="preview-caption" role="status">${changed2 ? "Preview updated" : "Unchanged"} · ${changed2} changed colors${original.entries.length > 256 ? " · first 256 shown" : ""}</p></div>`;
  }
  function mountNumberPreviews(root = document) {
    var _a;
    (_a = root.querySelectorAll) == null ? void 0 : _a.call(root, "[data-number-input]").forEach((node) => {
      const input = document.getElementById(node.dataset.numberInput);
      if (!input) return;
      const draw2 = () => {
        node.innerHTML = numberComparison(Number(node.dataset.before), input.value, { minimum: Number(node.dataset.minimum ?? -Infinity), maximum: Number(node.dataset.maximum ?? Infinity), compact: node.dataset.compact === "true" });
      };
      input.addEventListener("input", draw2);
      input.addEventListener("change", draw2);
      draw2();
    });
  }

  // romancer/ui/views/tables.js
  var numericTypes = ["u8", "s8", "u16", "s16", "u24", "s24", "u32", "s32"];
  var starter = [{ name: "Value", offset: 0, type: "u8", endian: "little", pointer_base: null }];
  function integer2(id) {
    const text = read(id).trim(), value = Number(text);
    if (!text || !Number.isSafeInteger(value)) throw new Error("Enter a whole number for " + id + ".");
    return value;
  }
  function stored(ctx2, key3, fallback) {
    try {
      return JSON.parse(ctx2.draft(key3, JSON.stringify(fallback)));
    } catch {
      return fallback;
    }
  }
  function bounds(field2) {
    return { ...numericBounds(field2.type), ...field2.minimum !== void 0 ? { minimum: field2.minimum } : {}, ...field2.maximum !== void 0 ? { maximum: field2.maximum } : {} };
  }
  function recordName(row) {
    return (row == null ? void 0 : row.label) !== void 0 ? row.label + " · ID 0x" + row.record_id.toString(16).toUpperCase().padStart(2, "0") : "Row " + row.index;
  }
  async function render3(ctx2) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    const artifact = state2.artifact;
    if (!artifact) return empty("Import a ROM first", "A table needs an exact source revision.", button("Import ROM", "import", { primary: true }));
    const saved = ((_b = (_a = artifact.descriptors) == null ? void 0 : _a.tables) == null ? void 0 : _b.source_sha256) === artifact.sha256 ? artifact.descriptors.tables.definition : null;
    let model = state2.results["tables.inspect"];
    if ((model == null ? void 0 : model.source_sha256) !== artifact.sha256) model = null;
    if (!model && saved) {
      model = await ctx2.api.call("tables.inspect", { ...ctx2.sourceParams(), definition: saved, page: 0, limit: 50 });
      state2.results["tables.inspect"] = model;
    }
    const columns2 = stored(ctx2, "table-fields", (saved == null ? void 0 : saved.fields) || starter);
    const staged = stored(ctx2, "table-changes", null);
    let changes = staged && model && staged.document_id === model.document_id ? staged.changes : [];
    const catalog = (model == null ? void 0 : model.row_catalog) || [], queryKey = "table-name-query-" + ((model == null ? void 0 : model.document_id) || ""), query = ctx2.draft(queryKey, "");
    const matches = catalog.filter((row) => recordName(row).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
    const resetKey = "table-reset-" + ((model == null ? void 0 : model.document_id) || ""), reset = Number(ctx2.draft(resetKey, "0")) || 0;
    const inputId = (row, index) => "table-cell-" + model.document_id + (reset ? "-v" + reset : "") + "-" + row + "-" + index;
    function resetCells() {
      ctx2.setDraft(resetKey, String(reset + 1));
    }
    function saveChanges(next) {
      changes = next;
      ctx2.setDraft("table-changes", JSON.stringify({ document_id: model.document_id, changes }));
      state2.pending = null;
    }
    function collectVisible() {
      if (!model) return [];
      const result = new Map(changes.map((change) => [change.row + ":" + change.field, change]));
      for (const row of model.rows) for (const [index, cell] of row.cells.entries()) {
        const node = document.getElementById(inputId(row.index, index));
        if (!node) continue;
        const after = integer2(node.id), key3 = row.index + ":" + cell.field;
        if (after === cell.value) result.delete(key3);
        else result.set(key3, { row: row.index, field: cell.field, before: cell.value, after });
      }
      return [...result.values()];
    }
    function definition() {
      const names4 = (model == null ? void 0 : model.definition.label_source) || (saved == null ? void 0 : saved.label_source);
      return { schema_version: 1, name: read("table-name").trim(), offset: integer2("table-offset"), count: integer2("table-count"), stride: integer2("table-stride"), fields: columns2, ...names4 ? { label_source: names4 } : {} };
    }
    ctx2.use({
      "table-add-field": () => {
        const name = read("table-field-name").trim();
        if (!name) throw new Error("Name the field first.");
        const field2 = { name, offset: integer2("table-field-offset"), type: read("table-field-type"), endian: read("table-field-endian"), pointer_base: read("table-field-base").trim() ? integer2("table-field-base") : null };
        ctx2.setDraft("table-fields", JSON.stringify([...columns2, field2]));
        return ctx2.render();
      },
      "table-remove-field": (node) => {
        ctx2.setDraft("table-fields", JSON.stringify(columns2.filter((_, index) => index !== Number(node.dataset.id))));
        return ctx2.render();
      },
      "table-inspect": async () => {
        const result = await ctx2.run("tables.save_definition", { ...ctx2.sourceParams(), definition: definition() }, { render: false });
        state2.results["tables.inspect"] = result.inspection;
        state2.pending = null;
        await ctx2.render();
      },
      "table-page": async (node) => {
        if (!model) return;
        saveChanges(collectVisible());
        await ctx2.run("tables.inspect", { ...ctx2.sourceParams(), definition: model.definition, page: Math.max(0, model.page + Number(node.dataset.id)), limit: 50 });
      },
      "table-search": async () => {
        if (!model) return;
        saveChanges(collectVisible());
        ctx2.setDraft(queryKey, read("table-name-query"));
        await ctx2.render();
      },
      "table-select-record": async () => {
        if (!model) return;
        const index = integer2("table-record-choice");
        if (!catalog.some((row) => row.index === index)) throw Error("Choose a record from the current table.");
        saveChanges(collectVisible());
        await ctx2.run("tables.inspect", { ...ctx2.sourceParams(), definition: model.definition, page: Math.floor(index / model.limit), limit: model.limit });
      },
      "table-review": async () => {
        var _a2;
        if (!model) throw new Error("Load a table definition first.");
        saveChanges(collectVisible());
        const signature = JSON.stringify(changes);
        const plan = await ctx2.run("tables.plan", { ...ctx2.sourceParams(), definition: model.definition, document_id: model.document_id, changes }, { render: false });
        if (((_a2 = state2.results["tables.inspect"]) == null ? void 0 : _a2.document_id) !== model.document_id || JSON.stringify(collectVisible()) !== signature) {
          ctx2.notify("Table values changed during review. Review them again.");
          return;
        }
        state2.pending = { kind: "table", plan_id: plan.plan_id, artifact_id: artifact.artifact_id, document_id: model.document_id, changes: structuredClone(changes) };
        await ctx2.render();
      },
      "table-build": async () => {
        var _a2;
        if (((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "table" || state2.pending.artifact_id !== artifact.artifact_id || state2.pending.document_id !== (model == null ? void 0 : model.document_id)) throw new Error("Review the table changes for this source first.");
        if (JSON.stringify(collectVisible()) !== JSON.stringify(state2.pending.changes)) {
          state2.pending = null;
          throw new Error("Table values changed after review. Review the changes again.");
        }
        const reviewed = state2.pending;
        await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: reviewed.plan_id }, { render: false });
        if (state2.pending !== reviewed || JSON.stringify(collectVisible()) !== JSON.stringify(reviewed.changes)) {
          ctx2.notify("Build created. Your newer table edits are still staged.");
          return;
        }
        state2.pending = null;
        ctx2.setDraft("table-changes", "null");
        resetCells();
        await ctx2.render();
        ctx2.notify("Build created. Choose it in the source/build selector to playtest.");
      },
      "table-batch": async () => {
        var _a2;
        if (!model) throw new Error("Load a table definition first.");
        const current2 = collectVisible();
        const result = await ctx2.run("tables.batch", { ...ctx2.sourceParams(), definition: model.definition, field: read("table-batch-field"), operation: read("table-batch-operation"), value: integer2("table-batch-value"), first: integer2("table-batch-first"), count: integer2("table-batch-count") }, { render: false });
        if (((_a2 = state2.results["tables.inspect"]) == null ? void 0 : _a2.document_id) !== model.document_id || result.document_id !== model.document_id) throw Error("Table definition changed. Repeat the batch preview.");
        const merged = new Map(current2.map((change) => [change.row + ":" + change.field, change]));
        for (const change of result.changes) {
          merged.set(change.row + ":" + change.field, change);
          const index = model.definition.fields.findIndex((field2) => field2.name === change.field);
          ctx2.setDraft(inputId(change.row, index), String(change.after));
        }
        saveChanges([...merged.values()]);
        await ctx2.render();
        ctx2.notify(result.changes.length + " batch changes staged. Review before building.");
      },
      "table-discard": () => {
        resetCells();
        saveChanges([]);
        return ctx2.render();
      },
      "table-target": async (node) => {
        const offset = Number(node.dataset.id);
        state2.resourceJump = offset;
        await ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset, length: Math.min(256, artifact.size - offset) }, { render: false });
        await ctx2.navigate("resources");
      }
    });
    const pending = ((_c = state2.pending) == null ? void 0 : _c.kind) === "table" && state2.pending.artifact_id === artifact.artifact_id;
    return `${heading("", "Data tables", "")}<section class="card"><div class="card-heading"><h3>${esc((model == null ? void 0 : model.definition.name) || "Define a table")}</h3><span>${model ? model.total + " records" : "No table loaded"}</span></div><details class="config" ${model ? "" : "open"}><summary>Table layout</summary><div class="field-row">${field("table-name", "Table name", ctx2.draft("table-name", (saved == null ? void 0 : saved.name) || "Data table"))}${field("table-offset", "First record offset", ctx2.draft("table-offset", (saved == null ? void 0 : saved.offset) ?? "0"))}${field("table-count", "Record count", ctx2.draft("table-count", (saved == null ? void 0 : saved.count) ?? "16"))}${field("table-stride", "Bytes per record", ctx2.draft("table-stride", (saved == null ? void 0 : saved.stride) ?? "1"))}</div><div class="table-wrap"><table><thead><tr><th>Field</th><th>Offset</th><th>Type</th><th>Order</th><th>Pointer base</th><th></th></tr></thead><tbody>${columns2.map((field2, index) => `<tr><td>${esc(field2.name)}</td><td>${field2.offset}</td><td>${esc(field2.type)}</td><td>${esc(field2.endian)}</td><td>${field2.pointer_base ?? "None"}</td><td>${button("Remove", "table-remove-field", { id: String(index) })}</td></tr>`).join("")}</tbody></table></div><details class="config"><summary>Add a field</summary><div class="field-row">${field("table-field-name", "Field name", ctx2.draft("table-field-name", ""))}${field("table-field-offset", "Offset within record", ctx2.draft("table-field-offset", "0"))}${select("table-field-type", "Numeric type", numericTypes.map((type) => [type, type]), ctx2.draft("table-field-type", "u8"))}${select("table-field-endian", "Byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("table-field-endian", "little"))}${field("table-field-base", "Pointer base (optional)", ctx2.draft("table-field-base", ""))}</div><p>For a linear pointer: target file offset = stored value − base.</p>${button("Add field", "table-add-field")}</details>${button("Load table definition", "table-inspect", { primary: !model })}</details></section>${model ? `<section class="card"><div class="card-heading"><h3>Records</h3><span>${changes.length} staged changes</span></div>${catalog.length ? `<div class="field-row">${field("table-name-query", "Search record names or IDs", query)}${button("Find records", "table-search")}</div><div class="field-row">${select("table-record-choice", "Named record", matches.map((row) => [row.index, recordName(row)]), String(((_d = matches[0]) == null ? void 0 : _d.index) ?? ""))}${button("Show selected record", "table-select-record", { disabled: !matches.length, reason: "No matching record names." })}</div><p>${matches.length} matching records. Names come from this source revision; blank and unsupported text are marked.</p>` : ""}<div class="table-wrap"><table class="numeric-table"><thead><tr><th>Row</th>${model.definition.fields.map((field2) => `<th>${esc(field2.name)}${Number.isFinite(bounds(field2).minimum) && Number.isFinite(bounds(field2).maximum) ? `<br><small>Range ${bounds(field2).minimum}–${bounds(field2).maximum}</small>` : ""}</th>`).join("")}</tr></thead><tbody>${model.rows.map((row) => `<tr><td>${esc(recordName(row))}<br>${row.label !== void 0 ? `<small>Row ${row.index}${row.label_status === "unsupported" ? " · Unsupported name bytes" : row.label_status === "blank" ? " · Blank name" : ""}</small><br>` : ""}<code>0x${row.offset.toString(16)}</code></td>${row.cells.map((cell, index) => {
      var _a2, _b2;
      return `<td><label class="field"><span class="sr-only">${esc(cell.field)}, ${esc(recordName(row))}</span><input id="${inputId(row.index, index)}" value="${esc(ctx2.draft(inputId(row.index, index), ((_a2 = changes.find((change) => change.row === row.index && change.field === cell.field)) == null ? void 0 : _a2.after) ?? cell.value))}" inputmode="numeric" aria-label="${esc(cell.field)}, ${esc(recordName(row))}"></label><div data-number-input="${inputId(row.index, index)}" data-before="${cell.value}" data-compact="true" data-minimum="${bounds(model.definition.fields[index]).minimum}" data-maximum="${bounds(model.definition.fields[index]).maximum}">${numberComparison(cell.value, ctx2.draft(inputId(row.index, index), ((_b2 = changes.find((change) => change.row === row.index && change.field === cell.field)) == null ? void 0 : _b2.after) ?? cell.value), { compact: true, ...bounds(model.definition.fields[index]) })}</div>${cell.target_offset !== null ? button("Open target 0x" + cell.target_offset.toString(16), "table-target", { id: String(cell.target_offset) }) : cell.pointer_resolution ? "<span>Unresolved target</span>" : ""}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div><div class="actions">${button("Previous records", "table-page", { id: "-1", disabled: !model.page })}<span>Page ${model.page + 1}</span>${button("Next records", "table-page", { id: "1", disabled: (model.page + 1) * model.limit >= model.total })}${button("Review changes", "table-review", { primary: !pending })}${pending ? button("Create build", "table-build", { primary: true }) : ""}${button("Discard changes", "table-discard")}</div></section>${changes.length ? `<details class="card"><summary>Staged changes by record</summary><ul>${changes.map((change) => `<li>${esc(recordName(catalog[change.row] || { index: change.row }))}: ${esc(change.field)} ${change.before} → ${change.after}</li>`).join("")}</ul></details>` : ""}<details class="card"><summary>Batch change</summary><p>Preview up to1024 source records. Percent changes round halves away from zero. Numeric overflow is refused; declared field limits are also enforced. First row refers to the row number shown with each record.</p><div class="field-row">${select("table-batch-field", "Field", model.definition.fields.map((field2) => [field2.name, field2.name]), ctx2.draft("table-batch-field", model.definition.fields[0].name))}${select("table-batch-operation", "Operation", [["set", "Set value"], ["add", "Add"], ["multiply", "Multiply"], ["percent", "Change by percent"]], ctx2.draft("table-batch-operation", "add"))}${field("table-batch-value", "Value", ctx2.draft("table-batch-value", "1"))}${field("table-batch-first", "First row", ctx2.draft("table-batch-first", "0"))}${field("table-batch-count", "Record count", ctx2.draft("table-batch-count", String(Math.min(10, model.total))))}</div>${button("Preview batch changes", "table-batch")}</details>` : ""}${report(state2.results["tables.plan"], "Table change plan")}${report(state2.results["build.apply"], "Built output")}`;
  }
  function mount() {
    mountNumberPreviews();
  }

  // romancer/ui/views/help.js
  var help_exports = {};
  __export(help_exports, {
    render: () => render4
  });
  async function render4(ctx2) {
    const { state: state2 } = ctx2;
    const result = await ctx2.api.call("help.list", { query: state2.helpQuery || "", topic: state2.helpTopic || "start" });
    ctx2.use({
      "help-search": () => {
        state2.helpQuery = read("help-query").slice(0, 160);
        state2.helpTopic = "";
        return ctx2.render();
      },
      "help-open": (node) => {
        state2.helpTopic = node.dataset.id;
        return ctx2.render();
      }
    });
    const selected2 = result.selected || result.topics[0];
    return `${heading("", "Help", "", '<a class="guide-link" href="/user-guide/index.html" target="_blank" rel="noopener noreferrer">User guide</a>' + button("Tutorials", "tutorial-hub", { primary: true }) + button("Keyboard shortcuts", "shortcut-help"))}<div class="help-layout"><section class="card help-index">${field("help-query", "Search offline help", state2.helpQuery || "")}${button("Search help", "help-search", { primary: true })}<nav aria-label="Help topics">${result.topics.map((row) => button(row.title, "help-open", { id: row.id, class: row.id === (selected2 == null ? void 0 : selected2.id) ? "selected-help" : "" })).join("") || "<p>No matching topics. Try a shorter search.</p>"}</nav></section><article class="card help-article">${selected2 ? `<h2>${esc(selected2.title)}</h2><p>${esc(selected2.summary)}</p><ol>${selected2.steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol><div class="actions">${button("Open resources", "navigate", { id: "resources" })}${button("Playtest", "navigate", { id: "playtest" })}${button("Project settings", "navigate", { id: "settings" })}</div>` : "<h2>Choose a topic</h2><p>Help is included with ROMancer and works offline.</p>"}</article></div>`;
  }

  // romancer/ui/api.js
  var storedToken = null;
  try {
    storedToken = sessionStorage.getItem("romancer-session");
  } catch {
  }
  var token = new URLSearchParams(location.hash.slice(1)).get("token") || storedToken;
  if (token) {
    try {
      sessionStorage.setItem("romancer-session", token);
      if (location.hash.includes("token=")) history.replaceState(null, "", location.pathname);
    } catch {
    }
  }
  function headers(json2 = true) {
    return { "Authorization": "Bearer " + (token || ""), ...json2 ? { "Content-Type": "application/json" } : {} };
  }
  async function request(path, options) {
    const controller = new AbortController();
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new Error("The local service did not respond in time. Reopen ROMancer and try again."));
      }, 3e4);
    });
    try {
      return await Promise.race([(async () => {
        const response = await fetch(path, { ...options, signal: controller.signal, headers: { ...headers(), ...options.headers } });
        let result;
        try {
          result = await response.json();
        } catch {
          throw new Error("The local service did not return a valid result. Relaunch ROMancer.");
        }
        if (!response.ok) throw new Error(result.error || `Local service error ${response.status}`);
        return result;
      })(), deadline]);
    } finally {
      clearTimeout(timer);
    }
  }
  var api = {
    async uploadInput(project_id, file, kind) {
      const limits = { patch: 64, catalog: 16, save: 8, translation: 4, audio: 2 };
      if (!file || !limits[kind]) throw new Error("Choose a supported input file.");
      if (file.size > limits[kind] * 1024 * 1024) throw new Error(`This ${kind} exceeds the ${limits[kind]} MiB limit.`);
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 3e4);
      try {
        const response = await fetch(`/api/upload?project_id=${encodeURIComponent(project_id)}&name=${encodeURIComponent(file.name)}&kind=${encodeURIComponent(kind)}`, { method: "POST", headers: headers(false), body: file, signal: controller.signal });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || "File import failed. Choose the file again.");
        return result;
      } finally {
        clearTimeout(timer);
      }
    },
    async call(operation, parameters = {}) {
      const result = await request("/api/call", { method: "POST", body: JSON.stringify({ operation, parameters }) });
      if (result.ok === false && result.error) throw Object.assign(new Error(typeof result.error === "string" ? result.error : result.error.message || "Operation blocked"), { result });
      return result;
    },
    async job(operation, parameters, onProgress) {
      const submitted = await this.call("jobs.submit", { operation, parameters });
      for (; ; ) {
        const job = await this.call("jobs.get", { job_id: submitted.job_id });
        onProgress == null ? void 0 : onProgress(job);
        if (["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(job.status)) {
          if (["CANCELLED", "INTERRUPTED"].includes(job.status)) throw Object.assign(new Error(job.message), { result: job.result });
          if (!job.result) throw new Error(job.message);
          if (job.result.ok === false && job.result.error) throw Object.assign(new Error(typeof job.result.error === "string" ? job.result.error : job.result.error.message || "Operation blocked"), { result: job.result });
          return job.result;
        }
        await new Promise((r) => setTimeout(r, 350));
      }
    },
    async upload(project_id, file) {
      if (file.size > 64 * 1024 * 1024) throw new Error("Browser imports support up to 64 MiB. Use an absolute path for larger files.");
      const response = await fetch(`/api/upload?project_id=${encodeURIComponent(project_id)}&name=${encodeURIComponent(file.name)}`, { method: "POST", headers: headers(false), body: file });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Import failed");
      return result;
    },
    async download(project_id, export_id, name) {
      const response = await fetch("/api/download", { method: "POST", headers: headers(), body: JSON.stringify({ project_id, export_id }) });
      if (!response.ok) throw new Error("Export could not be downloaded. Refresh the export list and try again.");
      const blob = await response.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2e3);
    }
  };

  // romancer/ui/views/overview.js
  var overview_exports = {};
  __export(overview_exports, {
    mount: () => mount2,
    render: () => render5
  });

  // romancer/ui/source_support.js
  var systems = /* @__PURE__ */ new Set(["nes", "snes", "genesis", "gb", "gbc", "gba"]);
  var names = { nes: "NES", snes: "SNES", genesis: "Genesis", gb: "Game Boy", gbc: "Game Boy Color", gba: "GBA" };
  function sourceSupport(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g;
    const a = ctx2.state.artifact;
    if (!a) return "";
    const allowed = systems.has(a.system_id), d = a.descriptors || {}, scan = (_b = (_a = ctx2.state.romScans) == null ? void 0 : _a[selectionKey(ctx2.state)]) == null ? void 0 : _b.result, profile = ((_c = scan == null ? void 0 : scan.identification) == null ? void 0 : _c.status) === "MATCHED";
    return `<details class="card"><summary>What is known about this source ${badge(allowed ? "Supported system" : "Inspect only", allowed ? "good" : "warm")}</summary><p>System: ${esc(allowed ? names[a.system_id] : "Unresolved or unsupported")} · ${profile ? "Exact game revision verified" : "Game-specific meanings require a verified definition"}</p><p>Saved definitions: ${Object.entries({ Graphics: !!d.assets, Text: !!d.script, Tables: !!d.tables, Levels: !!d.levels, Samples: !!((_e = (_d = d.sound) == null ? void 0 : _d.samples) == null ? void 0 : _e.length), Music: !!((_g = (_f = d.sound) == null ? void 0 : _f.songs) == null ? void 0 : _g.length) }).filter(([, v]) => v).map(([name]) => name).join(" · ") || "None yet"}</p><p>Known means a verified revision or documented system format. Saved declarations are checked when opened. Candidates and unknown data do not establish game behavior.</p><div class="actions">${button("Inspect bytes & health", "navigate", { id: "resources" })}${button("System setup", "navigate", { id: "playtest", disabled: !allowed })}</div></details>`;
  }
  async function resourceRelationships(ctx2) {
    var _a, _b, _c, _d;
    const a = ctx2.state.artifact;
    if (!((_a = a == null ? void 0 : a.descriptors) == null ? void 0 : _a.levels) && !((_b = a == null ? void 0 : a.descriptors) == null ? void 0 : _b.sound)) return "";
    const scope = selectionKey(ctx2.state);
    let result;
    try {
      result = await ctx2.api.call("resources.relationships", ctx2.sourceParams());
    } catch (error) {
      if (selectionKey(ctx2.state) !== scope || ((_c = ctx2.isCurrentRender) == null ? void 0 : _c.call(ctx2)) === false) return "";
      return `<section class="card"><h3>Declared relationships unavailable</h3><p>${esc(error.message)}</p><p>Inspect the bytes below or correct the saved definitions.</p></section>`;
    }
    if (selectionKey(ctx2.state) !== scope || ((_d = ctx2.isCurrentRender) == null ? void 0 : _d.call(ctx2)) === false) return "";
    ctx2.use({ "relationship-open": (node) => {
      if (selectionKey(ctx2.state) !== scope) return;
      const offset = Number(node.dataset.id);
      if (!result.nodes.some((n) => n.offset === offset)) throw Error("Reload declared relationships.");
      ctx2.state.resourceJump = offset;
      return ctx2.navigate("resources");
    } });
    const names4 = new Map(result.nodes.map((n) => [n.id, n.name]));
    return `<details class="card"><summary>Declared resource relationships</summary><p>Source-bound ranges and explicit editor relationships. Game behavior still needs native verification.</p>${result.partial ? '<p class="notice warm">Showing ' + result.exit_connections.listed + " of " + result.exit_connections.declared + " declared exit links. Undeclared relationships remain unknown.</p>" : ""}<div class="table-wrap"><table><thead><tr><th>Resource</th><th>File offset</th><th>Bytes</th></tr></thead><tbody>${result.nodes.map((n) => `<tr><td>${esc(n.name)}</td><td>${button("0x" + n.offset.toString(16), "relationship-open", { id: String(n.offset) })}</td><td>${n.length}</td></tr>`).join("")}</tbody></table></div>${result.edges.map((e) => `<p>${esc(names4.get(e.from) || e.from)} → ${esc(names4.get(e.to) || e.to)} · ${esc(e.relation)}</p>`).join("")}</details>`;
  }

  // romancer/ui/room_editor.js
  function roomValue(v, point) {
    if (!v.object.allowed.some((p) => p[0] === point[0] && p[1] === point[1])) throw Error("Choose a verified floor tile highlighted in the room.");
    if (point[0] === v.original[0] && point[1] === v.original[1]) return "original";
    if (point[0] === v.stool_down[0] && point[1] === v.stool_down[1]) return "stool_down";
    return `at:${point[0]},${point[1]}`;
  }
  function roomTarget(v, value) {
    const match = /^at:(\d+),(\d+)$/.exec(value || "");
    return value === "original" ? v.original : value === "stool_down" ? v.stool_down : match ? [Number(match[1]), Number(match[2])] : v.current;
  }
  function roomPoint(v, rect, point) {
    if (rect.width <= 0 || rect.height <= 0) return null;
    const x = Math.floor((point.x - rect.left) / rect.width * v.size[0]), y = Math.floor((point.y - rect.top) / rect.height * v.size[1]);
    return x >= 0 && y >= 0 && x < v.size[0] && y < v.size[1] ? [v.origin[0] + x, v.origin[1] + y] : null;
  }
  function roomPixels(v, point, { terrain = true, object = true } = {}) {
    const size2 = v.tile_size, width = v.size[0] * size2, height = v.size[1] * size2;
    if (width * height > 1024 * 1024) throw Error("Room preview exceeds its pixel budget.");
    const cells = [...v.base_cells], x = point[0] - v.origin[0], y = point[1] - v.origin[1];
    if (x < 0 || y < 0 || x >= v.size[0] || y >= v.size[1]) throw Error("Object is outside the decoded room.");
    if (object) cells[y * v.size[0] + x] = v.object.tile_id;
    const rgba = new Uint8ClampedArray(width * height * 4);
    cells.forEach((id, cell) => {
      const tile = v.tiles[id];
      if (!tile || tile.length !== size2 * size2) throw Error("A room tile is missing from its verified tileset.");
      tile.forEach((index, pixel) => {
        const color = v.palette[index];
        if (!color) throw Error("Room pixel has no declared color.");
        const rgb = terrain || object && cell === y * v.size[0] + x ? color : [16, 25, 31], px = cell % v.size[0] * size2 + pixel % size2, py = Math.floor(cell / v.size[0]) * size2 + Math.floor(pixel / size2);
        rgba.set([...rgb, 255], (py * width + px) * 4);
      });
    });
    return rgba;
  }
  function roomPreview(v, value) {
    const point = roomTarget(v, value), changed2 = point.some((n, i) => n !== v.current[i]);
    return `<div class="live-game-preview room-object-preview"><h3>Opening bedroom</h3><fieldset class="room-layers"><legend>Layers</legend><label><input id="room-show-terrain" type="checkbox" checked> Terrain</label><label><input id="room-show-object" type="checkbox" checked> Objects</label>${v.collision_values ? '<label><input id="room-show-collision" type="checkbox"> Collision values</label>' : ""}<label><input id="room-show-grid" type="checkbox"> Tile grid</label><label><input id="room-show-targets" type="checkbox" checked> Allowed floor tiles</label></fieldset><div class="preview-pair"><div><span>Original</span><canvas id="room-original" aria-label="Decoded original bedroom map"></canvas></div><div><span>Editing - move here</span><canvas id="room-edit" tabindex="0" role="application" aria-label="Decoded bedroom: drag stool or use arrow keys to move it"></canvas></div></div><p id="room-edit-status" role="status">${changed2 ? "Stool preview updated. Create a build to keep this change." : "No changes yet."}</p><p class="preview-caption">Drag the stool onto a highlighted floor tile. You can also click a floor tile or use the arrow keys.</p><details><summary>Preview details</summary><p>The room background and stool come from this ROM. Characters and dialogue appear in Playtest. Exits and other objects are protected.</p><p>Collision values show stored numbers; their meanings are not inferred. Review changes, then create a build.</p></details></div>`;
  }
  function mountRoomPreview(ctx2, v, value, change) {
    var _a;
    const canvas = document.getElementById("room-edit"), original = document.getElementById("room-original");
    if (!canvas || !original) return;
    const selected2 = roomTarget(v, value), width = v.size[0] * v.tile_size, height = v.size[1] * v.tile_size;
    const source = ctx2.state.gameVisualModel, alive = () => ctx2.state.gameVisualModel === source && canvas.isConnected;
    let point = selected2, pointer = null;
    const layerIds = ["room-show-terrain", "room-show-object", "room-show-collision", "room-show-grid", "room-show-targets"];
    if (ctx2.state.roomLayerScope !== source.scope) {
      ctx2.state.roomLayerScope = source.scope;
      ctx2.state.roomLayers = {};
    }
    for (const id of layerIds) {
      const input = document.getElementById(id);
      if (input && Object.hasOwn(ctx2.state.roomLayers, id)) input.checked = ctx2.state.roomLayers[id];
    }
    const enabled = (id) => {
      var _a2;
      return ((_a2 = document.getElementById(id)) == null ? void 0 : _a2.checked) ?? true;
    };
    const paint = (node, position, targets = false) => {
      var _a2;
      node.width = width;
      node.height = height;
      const c = node.getContext("2d"), image = c.createImageData(width, height);
      image.data.set(roomPixels(v, position, { terrain: enabled("room-show-terrain"), object: enabled("room-show-object") }));
      c.putImageData(image, 0, 0);
      if (v.collision_values && enabled("room-show-collision")) v.collision_values.forEach((value2, index) => {
        const x = index % v.size[0] * v.tile_size, y = Math.floor(index / v.size[0]) * v.tile_size;
        c.fillStyle = value2 === 1 ? "#16775b88" : "#74427288";
        c.fillRect(x, y, v.tile_size, v.tile_size);
        c.fillStyle = "#fff";
        c.font = "6px monospace";
        c.fillText(value2.toString(16).padStart(2, "0"), x + 2, y + 8);
      });
      if (enabled("room-show-grid")) {
        c.strokeStyle = "#ffffff60";
        c.lineWidth = 0.5;
        for (let y = 0; y < v.size[1]; y++) for (let x = 0; x < v.size[0]; x++) c.strokeRect(x * v.tile_size + 0.5, y * v.tile_size + 0.5, v.tile_size - 1, v.tile_size - 1);
      }
      if (targets && ((_a2 = document.getElementById("room-show-targets")) == null ? void 0 : _a2.checked)) {
        c.strokeStyle = "#26b99a";
        c.lineWidth = 1;
        for (const p of v.object.allowed) c.strokeRect((p[0] - v.origin[0]) * v.tile_size + 0.5, (p[1] - v.origin[1]) * v.tile_size + 0.5, v.tile_size - 1, v.tile_size - 1);
      }
      if (targets && enabled("room-show-object")) {
        c.strokeStyle = "#e8b34f";
        c.lineWidth = 2;
        c.strokeRect((position[0] - v.origin[0]) * v.tile_size + 1, (position[1] - v.origin[1]) * v.tile_size + 1, v.tile_size - 2, v.tile_size - 2);
      }
    };
    const status = (text) => {
      const node = document.getElementById("room-edit-status");
      if (node) node.textContent = text;
    };
    const propose = (next) => {
      if (!next) return false;
      if (!enabled("room-show-object")) {
        status("Enable the Objects layer to move the stool.");
        return false;
      }
      try {
        roomValue(v, next);
        point = next;
        paint(canvas, point, true);
        status(`Move stool to (${point.join(", ")}) - release to stage`);
        return true;
      } catch (e) {
        status(e.message);
        return false;
      }
    };
    const pick = (e) => roomPoint(v, canvas.getBoundingClientRect(), { x: e.clientX, y: e.clientY });
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerdown", (e) => {
      if (!alive() || e.button !== 0) return;
      e.preventDefault();
      canvas.focus();
      pointer = e.pointerId;
      canvas.setPointerCapture(pointer);
      propose(pick(e));
    });
    canvas.addEventListener("pointermove", (e) => {
      if (alive() && pointer === e.pointerId) propose(pick(e));
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!alive() || pointer !== e.pointerId) return;
      pointer = null;
      const next = pick(e);
      if (next && propose(next)) {
        change(roomValue(v, point));
      } else {
        point = selected2;
        paint(canvas, point, true);
      }
    });
    canvas.addEventListener("pointercancel", () => {
      if (!alive()) return;
      pointer = null;
      point = selected2;
      paint(canvas, point, true);
      status("Move cancelled.");
    });
    canvas.addEventListener("keydown", (e) => {
      const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
      if (!alive() || !delta || e.ctrlKey || e.altKey || e.metaKey) return;
      e.preventDefault();
      const next = [point[0] + delta[0], point[1] + delta[1]];
      if (propose(next)) change(roomValue(v, next));
    });
    for (const id of layerIds) (_a = document.getElementById(id)) == null ? void 0 : _a.addEventListener("change", (e) => {
      ctx2.state.roomLayers[id] = e.target.checked;
      paint(original, v.current);
      paint(canvas, point, true);
    });
    paint(original, v.current);
    paint(canvas, selected2, true);
  }

  // romancer/ui/game_visuals.js
  var palette = (colors) => ({ entries: colors.map((c, index) => ({ bank: 0, index, rgb: { r: c[0], g: c[1], b: c[2] } })) });
  function gameVisual(model, chosen) {
    var _a, _b, _c;
    if (((_a = model.visual) == null ? void 0 : _a.kind) === "room-map") return roomPreview(model.visual, chosen.room_layout);
    if (((_b = model.visual) == null ? void 0 : _b.kind) === "map-point") {
      const v = model.visual, target = Object.hasOwn(v, chosen.room_layout) && Array.isArray(v[chosen.room_layout]) ? v[chosen.room_layout] : v.current;
      const diagram = (point, label) => `<svg viewBox="0 0 ${v.size[0] * 16} ${v.size[1] * 16}" role="img" aria-label="${label}" style="width:112px;height:128px;background:var(--panel);border:1px solid var(--line)">${Array.from({ length: v.size[0] * v.size[1] }, (_, i) => `<rect x="${i % v.size[0] * 16}" y="${Math.floor(i / v.size[0]) * 16}" width="16" height="16" fill="none" stroke="currentColor" opacity=".15"/>`).join("")}<rect x="${(point[0] - v.origin[0]) * 16 + 2}" y="${(point[1] - v.origin[1]) * 16 + 2}" width="12" height="12" rx="2" fill="var(--accent)"/></svg>`;
      return `<div class="live-game-preview"><h3>Stored map position</h3><p role="status">Stool: (${v.current.join(", ")}) → (${target.join(", ")})</p><div class="preview-pair"><div><span>Original</span>${diagram(v.current, "Original stool position")}</div><div><span>Edited</span>${diagram(target, "Edited stool position")}</div></div><p class="preview-caption">Declared coordinate preview · playtest the actual room.</p></div>`;
    }
    if ((_c = model.visual) == null ? void 0 : _c.palettes) {
      const style = chosen.palette_style;
      return `<div class="live-game-preview"><h3>Color preview</h3>${model.visual.palettes.map((p, i) => `<details ${i === 0 ? "open" : ""}><summary>${esc(p.name)}</summary>${paletteComparison(palette(p.current), palette(Object.hasOwn(p, style) && Array.isArray(p[style]) ? p[style] : p.current))}</details>`).join("")}<p class="preview-caption">Stored palette colors · playtest to see them in the game scene.</p></div>`;
    }
    return model.fields.map((f) => `<div class="live-game-preview"><h3>${f.type === "integer" ? "Stored values" : "Text comparison"}</h3>${f.type === "integer" ? numberComparison(f.value, chosen[f.id], { minimum: f.min, maximum: f.max }) : textComparison(f.value, chosen[f.id] ?? f.value, { columns: 32 })}${f.type === "integer" ? '<p class="preview-caption">Stored values only. The game may calculate the displayed result.</p>' : ""}</div>`).join("");
  }
  function mountGameVisual(ctx2) {
    const owned = ctx2.state.gameVisualModel, node = document.getElementById("game-visual-preview");
    if (!owned || !node) return;
    const current2 = () => owned.scope === selectionKey(ctx2.state) && ctx2.state.gameVisualModel === owned;
    const values = () => Object.fromEntries(owned.model.fields.map((f) => {
      var _a;
      return [f.id, ((_a = document.getElementById("game-" + f.id)) == null ? void 0 : _a.value) ?? f.value];
    }));
    const draw2 = () => {
      var _a, _b, _c;
      if (current2()) {
        const focus = ((_a = document.activeElement) == null ? void 0 : _a.id) === "room-edit";
        node.innerHTML = gameVisual(owned.model, values());
        if (((_b = owned.model.visual) == null ? void 0 : _b.kind) === "room-map") mountRoomPreview(ctx2, owned.model.visual, values().room_layout, (value) => {
          if (!current2()) return;
          const input = document.getElementById("game-room_layout");
          if (input && input.value !== value) {
            input.value = value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
          }
        });
        if (focus) (_c = document.getElementById("room-edit")) == null ? void 0 : _c.focus({ preventScroll: true });
      }
    };
    for (const f of owned.model.fields) {
      const input = document.getElementById("game-" + f.id);
      if (!input) continue;
      const changed2 = () => {
        if (!current2()) return;
        const reviewed = ctx2.state.gameEditPlan;
        if (reviewed && JSON.stringify(Object.fromEntries(owned.model.fields.map((f2) => [f2.id, f2.type === "integer" ? Number(values()[f2.id]) : values()[f2.id]]))) !== JSON.stringify(reviewed.values)) {
          ctx2.state.gameEditPlan = null;
          const review2 = document.getElementById("game-edit-review");
          if (review2) review2.hidden = true;
        }
        draw2();
      };
      input.addEventListener("input", changed2);
      input.addEventListener("change", changed2);
    }
    draw2();
  }

  // romancer/ui/project_checks.js
  function projectChecks(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, id = (_a = state2.project) == null ? void 0 : _a.project_id, result = ((_b = state2.projectValidation) == null ? void 0 : _b.project_id) === id ? state2.projectValidation : null;
    ctx2.use({
      "project-checks": async () => {
        var _a2;
        const report2 = await ctx2.run("project.validate", { project_id: id }, { render: false });
        if (((_a2 = state2.project) == null ? void 0 : _a2.project_id) !== id) return;
        state2.projectValidation = report2;
        await ctx2.render();
      },
      "check-location": async (node) => {
        var _a2;
        if (((_a2 = state2.project) == null ? void 0 : _a2.project_id) !== id) return;
        await ctx2.setArtifact(node.dataset.id);
        state2.resourceJump = Number(node.dataset.name);
        await ctx2.navigate("resources");
      }
    });
    return `<section class="card"><div class="card-heading"><h3>Project checks</h3>${result ? badge(result.errors ? `${result.errors} errors` : result.warnings ? `${result.warnings} warnings` : "Checks passed", result.errors ? "warm" : "good") : ""}</div>${button("Check project", "project-checks", { disabled: !id })}
 ${result ? `<p>${result.checked_artifacts} files checked. Declared formats only; gameplay needs separate tests.</p>${result.issues.length ? `<div class="table-wrap"><table><thead><tr><th>Location</th><th>Check</th><th>Next step</th></tr></thead><tbody>${result.issues.map((r) => `<tr><td>${esc(r.location)}${r.offset !== null && r.offset !== void 0 ? `<br>${r.artifact_id ? button("0x" + r.offset.toString(16), "check-location", { id: r.artifact_id, name: String(r.offset) }) : "0x" + r.offset.toString(16)}` : ""}</td><td>${badge(r.severity, r.severity === "error" ? "warm" : "neutral")} ${esc(r.code.replaceAll("_", " ").toLowerCase())}</td><td>${esc(r.remedy)}</td></tr>`).join("")}</tbody></table></div>` : ""}${result.issues_truncated ? "<p>More issues exist; totals include all detected issues.</p>" : ""}` : '<p class="subtle">Check file identities, resource definitions, dependencies, pointers and compressed allocations.</p>'}</section>`;
  }
  function supportControls(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, selection2 = ((_a = state2.project) == null ? void 0 : _a.project_id) || null, saved = ((_b = state2.supportPreview) == null ? void 0 : _b.selection) === selection2 ? state2.supportPreview.report : null;
    ctx2.use({
      "support-check": async () => {
        var _a2;
        const report2 = await ctx2.run("support.collect", { selection: selection2 }, { render: false, refresh: false });
        if ((((_a2 = state2.project) == null ? void 0 : _a2.project_id) || null) !== selection2) return;
        state2.supportPreview = { selection: selection2, report: report2 };
        await ctx2.render();
      },
      "support-download": () => {
        var _a2, _b2;
        if (((_a2 = state2.supportPreview) == null ? void 0 : _a2.selection) !== (((_b2 = state2.project) == null ? void 0 : _b2.project_id) || null)) throw Error("Run diagnostics for this project first.");
        downloadDocument(state2.supportPreview.report, "ROMancer-support.json");
      }
    });
    return `<section class="card"><h3>Diagnostics & support</h3><p>Run local checks, review the report, then download it to share. No data is sent automatically.</p>${button("Run diagnostics", "support-check")}${saved ? `<div class="table-wrap"><table><tbody>${saved.checks.map((r) => `<tr><td>${esc(r.code.replaceAll("_", " ").toLowerCase())}</td><td>${badge(r.status, r.status === "PASS" ? "good" : "neutral")}</td></tr>`).join("")}</tbody></table></div><details open><summary>Review sanitized report</summary><pre>${esc(JSON.stringify(saved, null, 2))}</pre></details>${button("Download report", "support-download", { primary: true })}` : ""}</section>`;
  }

  // romancer/ui/verified_games.js
  async function gameEdits(ctx2) {
    var _a;
    const { state: state2 } = ctx2;
    if (!state2.artifact) return "";
    const scope = selectionKey(state2), params = { ...ctx2.sourceParams() }, current2 = () => scope === selectionKey(state2) && (!ctx2.isCurrentRender || ctx2.isCurrentRender());
    ctx2.use({ "game-view-bytes": async (node) => {
      if (!current2()) throw Error("The selected file changed.");
      state2.resourceJump = Number(node.dataset.id);
      await ctx2.navigate("resources");
    }, "game-investigate": () => ctx2.navigate("resources"), "game-open-maps": () => ctx2.navigate("levels") });
    let model;
    try {
      model = await ctx2.api.call("games.inspect", params);
    } catch (error) {
      if (!current2()) return "";
      return `<section class="card"><h3>Game edits unavailable</h3><p>${esc(error.message)}</p>${button("Inspect bytes", "game-investigate")}</section>`;
    }
    if (!current2()) return "";
    state2.gameVisualModel = { scope, model };
    if (!model.profile) return `<section class="card game-definition"><div class="card-heading"><h3>Investigate this ROM</h3>${button("Open hex editor", "game-investigate")}</div><p class="subtle">No verified game definition for this revision. Search bytes, compare builds, and bookmark locations in Resources.</p></section>`;
    const pending = ((_a = state2.gameEditPlan) == null ? void 0 : _a.scope) === scope && state2.gameEditPlan.result.profile_id === model.profile.id ? state2.gameEditPlan : null;
    function values() {
      return Object.fromEntries(model.fields.map((f) => {
        const value = read("game-" + f.id);
        if (f.type === "integer") {
          if (!/^\d+$/.test(value) || Number(value) < f.min || Number(value) > f.max) throw Error(`${f.label}: enter ${f.min} to ${f.max}.`);
          return [f.id, Number(value)];
        }
        return [f.id, value];
      }));
    }
    function sameValues(chosen) {
      try {
        return JSON.stringify(values()) === JSON.stringify(chosen);
      } catch {
        return false;
      }
    }
    ctx2.use({
      "game-resource": async (node) => {
        if (!current2()) throw Error("The selected file changed.");
        const result = await ctx2.run("games.configure", { ...params, resource_id: node.dataset.id }, { refresh: false, render: false });
        if (!current2()) return;
        await ctx2.refreshProject();
        state2.results["tables.inspect"] = result.inspection;
        await ctx2.navigate("tables");
      },
      "game-review": async () => {
        if (!current2()) throw Error("The selected file changed.");
        const chosen = values(), previous = state2.gameEditPlan;
        const result = await ctx2.run("games.plan", { ...params, profile_id: model.profile.id, values: chosen }, { refresh: false, render: false });
        if (!current2()) return;
        if (state2.gameEditPlan !== previous || !sameValues(chosen)) {
          ctx2.notify("Values changed during review. Review them again.");
          return;
        }
        state2.gameEditPlan = { scope, values: chosen, result };
        await ctx2.render();
      },
      "game-cancel": () => {
        state2.gameEditPlan = null;
        return ctx2.render();
      },
      "game-apply": async () => {
        const planned = state2.gameEditPlan;
        if (!current2() || (planned == null ? void 0 : planned.scope) !== scope) throw Error("Review changes for the selected ROM first.");
        if (!sameValues(planned.values)) throw Error("Values changed. Review the changes again.");
        const unchanged = () => state2.gameEditPlan === planned && sameValues(planned.values);
        let artifactId = planned.result.existing_build_id;
        if (artifactId) await ctx2.api.call("games.inspect", { ...params, artifact_id: artifactId });
        else {
          const result = await ctx2.run("build.apply", { project_id: params.project_id, plan_id: planned.result.plan_id }, { refresh: false, render: false });
          artifactId = result.artifact_id;
          await ctx2.api.call("builds.annotate", { project_id: params.project_id, artifact_id: artifactId, name: planned.result.build_name, notes: `${model.profile.name}: ${planned.result.preview.map((p) => p.label + " " + p.before + " to " + p.after).join("; ")}. Definition ${model.profile.id}. ${model.profile.reference}` });
        }
        if (!current2()) return;
        await ctx2.refreshProject();
        if (!current2()) return;
        if (!unchanged()) {
          ctx2.notify("Build available in history. Your newer game edits are still staged.");
          await ctx2.render();
          return;
        }
        state2.gameEditPlan = null;
        await ctx2.setArtifact(artifactId);
        ctx2.notify(planned.result.existing_build_id ? "Opened the matching build from history." : "Build created. Playtest it before exporting a patch.");
      }
    });
    const visualValues = Object.fromEntries(model.fields.map((f) => [f.id, ctx2.draft("game-" + f.id, String(f.value))]));
    const inputs = model.fields.map((f) => {
      const value = ctx2.draft("game-" + f.id, String(f.value));
      if (f.type === "choice") return select("game-" + f.id, f.label, [["", f.id === "room_layout" ? "Choose position" : "Choose colors"], ...f.options], value);
      return `<label class="field"><span>${esc(f.label)}</span><input id="game-${esc(f.id)}" type="${f.type === "integer" ? "number" : "text"}" value="${esc(value)}" ${f.type === "integer" ? `min="${f.min}" max="${f.max}"` : `maxlength="${f.max_length}"`}><small>${f.type === "integer" ? `${f.min}–${f.max}` : "Up to 9 letters, digits, spaces or ?"}</small></label>`;
    }).join("");
    const plan = pending == null ? void 0 : pending.result;
    const review2 = plan ? `<div class="game-review" id="game-edit-review"><h3>Review changes</h3>${plan.preview.map((p) => `<p><strong>${esc(p.label)}</strong> ${esc(p.before)} <span aria-label="changes to">→</span> ${esc(p.after)}</p>`).join("")}${plan.additional_changes.map((note) => `<p class="notice warm">${esc(note)}</p>`).join("")}<details><summary>Byte changes${plan.integrity_edit_count ? " and console checksum" : ""}</summary><table><thead><tr><th>Offset</th><th>Before</th><th>After</th></tr></thead><tbody>${plan.edits.map((e) => `<tr><td><code>0x${e.offset.toString(16).toUpperCase()}</code></td><td><code>${hexPreview(e.before)}</code></td><td><code>${hexPreview(e.after)}</code></td></tr>`).join("")}</tbody></table></details><div class="actions">${button(plan.existing_build_id ? "Open existing build" : "Create build", "game-apply", { primary: true, icon: "check" })}${button("Cancel review", "game-cancel")}</div></div>` : "";
    return `<section class="card game-definition"><div class="card-heading"><h3>Game edits</h3>${badge(model.status === "MATCHED" ? "Revision matched" : "Based on matched source", model.status === "MATCHED" ? "good" : "warm")}</div><div class="game-definition-grid"><div>${inputs}<div id="game-visual-preview">${gameVisual(model, visualValues)}</div><div class="actions">${model.fields.length ? button("Review changes", "game-review", { primary: !pending }) : ""}${model.map_workbench ? button("Open game maps", "game-open-maps") : ""}</div>${review2}</div><div><h3>Known locations</h3>${knowledgeReferences(model)}${(model.resources || []).filter((r) => !r.legacy).map((r) => `<div class="notice">${button("Open " + r.name, "game-resource", { id: r.id })}<p>${esc(r.scope)}</p></div>`).join("")}<div class="game-locations">${model.locations.map((l) => `<div><span>${esc(l.label)}<small class="subtle">${esc(l.storage || "")}</small></span>${button("View 0x" + l.offset.toString(16).toUpperCase(), "game-view-bytes", { id: String(l.offset) })}</div>`).join("")}</div><details><summary>Definition and tested scope</summary><p>${esc(model.profile.scope)}</p><p>${model.status === "DERIVED" ? "This build has a matched original in its history. Its gameplay has not been certified." : "The selected original matches the tested SHA-256 revision."}</p><a href="${esc(model.profile.reference)}" target="_blank" rel="noreferrer">Source reference</a></details></div></div></section>`;
  }
  function hexPreview(value) {
    return esc(value.length > 32 ? value.slice(0, 32).toUpperCase() + "… (" + value.length / 2 + " bytes)" : value.toUpperCase());
  }
  async function gameByteNotes(ctx2, data) {
    const scope = selectionKey(ctx2.state), params = { ...ctx2.sourceParams() };
    let model;
    try {
      model = await ctx2.api.call("games.inspect", params);
    } catch {
      return "";
    }
    if (scope !== selectionKey(ctx2.state) || ctx2.isCurrentRender && !ctx2.isCurrentRender()) return "";
    const locations = model.profile ? (model.locations || []).filter((l) => l.offset < data.offset + data.length && l.offset + l.length > data.offset) : [];
    return `<section class="card byte-reference"><div class="card-heading"><h3>Byte reference</h3>${locations.length ? badge(model.status === "MATCHED" ? "Known location" : "Matched source history", model.status === "MATCHED" ? "good" : "warm") : ""}</div>${locations.length ? locations.map((l) => `<h4>${esc(l.label)} · <code>0x${l.offset.toString(16).toUpperCase()}</code></h4><p><strong>${esc(l.storage)}</strong> · ${l.length} ${l.length === 1 ? "byte" : "bytes"}</p><p>${esc(l.meaning)}</p><p><code>${esc(l.example)}</code></p><details><summary>What was verified</summary><p>${esc(l.evidence)}</p><p>Tested on the exact original revision; this selected build still needs its own playtest.</p><a href="${esc(model.profile.reference)}" target="_blank" rel="noreferrer">Source reference</a></details>`).join("") : '<p class="subtle">No verified game meaning recorded for this byte range. Search matches are candidates until tested.</p>'}<details><summary>How to read these bytes</summary><p><code>0x</code> means hexadecimal. One byte ranges from <code>00</code> to <code>FF</code> (0–255); <code>1E</code> is 30.</p><p>Two-byte number 4660 is <code>34 12</code> in little endian or <code>12 34</code> in big endian. Signed 8-bit <code>FF</code> is −1; unsigned it is 255.</p><p>These are file offsets, including any header. CPU addresses and banked memory need an explicit mapping. On-screen values may be calculated or stored in RAM; game text may use a custom encoding.</p></details></section>`;
  }
  function knowledgeReferences(model) {
    const knowledge = model.knowledge;
    if (!knowledge) return "";
    const statuses = { implemented: "Supported workflow", layout_checked: "Reference checked", research_candidate: "Research lead" };
    return `<details class="game-knowledge"><summary>What is known about this game</summary><p>${esc(knowledge.note)}</p>${knowledge.facts.map((fact) => `<div class="notice"><strong>${esc(fact.label)}</strong> ${badge(statuses[fact.status] || fact.status, fact.status === "implemented" ? "good" : "neutral")}<p>${esc(fact.scope)}</p><div>${fact.source_ids.map((id) => knowledge.sources.find((source) => source.id === id)).filter(Boolean).map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer">Source · ${esc(source.commit.slice(0, 8))}</a>`).join(" · ")}</div></div>`).join("")}</details>`;
  }

  // romancer/ui/build_history.js
  function buildHistory(ctx2, timeline) {
    var _a, _b, _c, _d, _e;
    const { state: state2 } = ctx2, project = state2.project.project_id, rows = timeline.artifacts, byId = new Map(rows.map((r) => [r.artifact_id, r])), selected2 = byId.get((_a = state2.artifact) == null ? void 0 : _a.artifact_id), comparison = ((_b = state2.historyComparison) == null ? void 0 : _b.project_id) === project ? state2.historyComparison : null;
    ctx2.use({
      "history-select": (node) => ctx2.setArtifact(node.dataset.id),
      "history-save": async () => {
        var _a2, _b2;
        const id = (_a2 = state2.artifact) == null ? void 0 : _a2.artifact_id;
        await ctx2.run("builds.annotate", { project_id: project, artifact_id: id, name: read("history-name"), notes: read("history-notes") }, { render: false });
        if (((_b2 = state2.project) == null ? void 0 : _b2.project_id) !== project) return;
        await ctx2.refreshProject();
        await ctx2.setArtifact(id);
        ctx2.notify("Build name and notes saved.");
      },
      "history-compare": async () => {
        var _a2;
        const left_id = read("history-left"), right_id = read("history-right");
        const result = await ctx2.run("builds.compare", { project_id: project, left_id, right_id }, { render: false });
        if (((_a2 = state2.project) == null ? void 0 : _a2.project_id) !== project) return;
        state2.historyComparison = result;
        await ctx2.render();
      },
      "history-jump": async (node) => {
        var _a2;
        const r = state2.historyComparison;
        if ((r == null ? void 0 : r.project_id) !== ((_a2 = state2.project) == null ? void 0 : _a2.project_id)) throw Error("Compare the files again.");
        state2.hexComparison = { project_id: project, left_id: r.left_id, right_id: r.right_id, left_sha256: r.left_sha256, right_sha256: r.right_sha256, offset: Number(node.dataset.id) };
        await ctx2.setArtifact(r.right_id);
        state2.resourceJump = Number(node.dataset.id);
        await ctx2.navigate("resources");
      }
    });
    const options = rows.map((r) => [r.artifact_id, r.name]);
    return `<section class="card"><div class="card-heading"><h3>Build history</h3><span>${rows.filter((r) => r.kind === "build").length} build${rows.filter((r) => r.kind === "build").length === 1 ? "" : "s"}</span></div>
 ${rows.filter((r) => r.kind === "build").map((r) => {
      var _a2;
      return `<div class="resource-row"><div class="resource-meta"><strong>${esc(r.name)}</strong> ${badge(r.kind)}${r.artifact_id === (selected2 == null ? void 0 : selected2.artifact_id) ? badge("Selected", "good") : ""}<small>${r.parent_id ? "From " + esc(((_a2 = byId.get(r.parent_id)) == null ? void 0 : _a2.name) || "Missing parent") : "Imported original"} · ${size(r.size)} · ${short(r.sha256)}</small>${r.notes ? `<p>${esc(r.notes)}</p>` : ""}</div>${button("Select", "history-select", { id: r.artifact_id, disabled: r.artifact_id === (selected2 == null ? void 0 : selected2.artifact_id) })}</div>`;
    }).join("")}
 ${(selected2 == null ? void 0 : selected2.kind) === "build" ? `<details><summary>Name and notes for selected build</summary>${field("history-name", "Build name", selected2.name)}${area("history-notes", "Notes", selected2.notes, 3)}${button("Save build details", "history-save")}</details>` : ""}
 ${rows.some((r) => r.kind === "build") ? "" : '<p class="subtle">Your builds appear here after you review and create a change.</p>'}<details><summary>Compare files</summary><div class="field-row">${select("history-left", "Original / earlier file", options, ctx2.draft("history-left", (selected2 == null ? void 0 : selected2.parent_id) || ((_c = rows[0]) == null ? void 0 : _c.artifact_id)))}${select("history-right", "Later file", options, ctx2.draft("history-right", selected2 == null ? void 0 : selected2.artifact_id))}</div>${button("Compare files", "history-compare", { disabled: rows.length < 2 })}
 ${comparison ? `<p>${esc((_d = byId.get(comparison.left_id)) == null ? void 0 : _d.name)} → ${esc((_e = byId.get(comparison.right_id)) == null ? void 0 : _e.name)} · ${comparison.changed_bytes.toLocaleString()} changed byte${comparison.changed_bytes === 1 ? "" : "s"}</p><div class="actions">${comparison.ranges.map((r) => button(`0x${r.offset.toString(16)} · ${r.length} byte${r.length === 1 ? "" : "s"}`, "history-jump", { id: String(r.offset) })).join("")}</div>${comparison.ranges_truncated ? "<p>More ranges exist. The count includes every changed byte.</p>" : ""}` : ""}</details></section>`;
  }

  // romancer/ui/views/overview.js
  var ship = `<svg viewBox="0 0 360 250" fill="none" aria-hidden="true"><rect x="74" y="22" width="210" height="198" rx="14" fill="#203b40" stroke="#6bafa1" stroke-width="2"/><path d="M111 22v38h136V22M106 220v-30h146v30" stroke="#6bafa1" stroke-width="2"/><rect x="102" y="77" width="154" height="90" rx="6" fill="#13282e"/><path d="M124 148V97h31l13 10v12l-13 10h-31m30 0 22 19" stroke="#a3e5cd" stroke-width="8"/><path d="M197 105h32m-32 18h32m-32 18h21" stroke="#678f90" stroke-width="5"/><path d="M121 202h14m12 0h14m12 0h14m12 0h14m12 0h14" stroke="#c6ae77" stroke-width="9"/><path d="M45 80h15m-15 15h15m239 72h17m-17 15h17" stroke="#426b70" stroke-width="3"/></svg>`;
  function resource(a) {
    return `<div class="resource-row"><span class="resource-icon">${icon(a.kind === "build" ? "check" : "resources")}</span><div class="resource-meta"><strong>${esc(a.name)}</strong><small>${esc(a.system)} · ${size(a.size)} · <span class="mono">${short(a.sha256)}</span></small></div>${button("Inspect", "overview-inspect", { id: a.artifact_id, icon: "chevron" })}</div>`;
  }
  async function render5(ctx2) {
    const { state: state2 } = ctx2, p = state2.project;
    ctx2.use({ "overview-inspect": async (node) => {
      await ctx2.setArtifact(node.dataset.id);
      await ctx2.navigate("resources");
    } });
    if (!p) return `<div class="welcome">${heading("", "Overview", "")}<section class="hero"><div class="hero-copy"><h2>Open a project.</h2><p>Edit text and graphics, playtest, and export patches.</p><div class="actions">${button("Import ROM", "import", { primary: true, icon: "plus" })}${[["nes", "NES"], ["snes", "SNES"], ["genesis", "GEN"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]].map(([id, label]) => button(label + " workshop", "demo-system", { id, icon: "assets" })).join("")}</div></div><div class="hero-art">${ship}</div></section><div class="welcome-grid"><section class="card"><h3>Continue a project</h3><div class="project-list">${state2.projects.length ? state2.projects.slice(0, 8).map((p2) => `<div class="resource-row"><span class="resource-icon">${icon("folder")}</span><div class="resource-meta"><strong>${esc(p2.name)}</strong><small>${p2.sources.length} source${p2.sources.length === 1 ? "" : "s"} · ${p2.builds.length} build${p2.builds.length === 1 ? "" : "s"}</small></div>${button("Open", "open-project", { id: p2.project_id })}</div>`).join("") : empty("A fresh workspace", "Your projects will appear here after your first import.")}</div></section><section class="card"><h3>Quick start</h3>${steps()}</section></div></div>`;
    const timeline = await ctx2.api.call("builds.timeline", { project_id: p.project_id });
    const progress = await ctx2.api.call("project.readiness", { project_id: p.project_id });
    const reports = (await ctx2.api.call("reports.list", { project_id: p.project_id })).reports;
    const exports = (await ctx2.api.call("exports.list", { project_id: p.project_id })).exports;
    const gameEditing = await gameEdits(ctx2);
    return `${heading("Workspace overview", "Overview", p.demo ? "An original, redistributable fixture. Explore the real editing and release workflows." : "Your sources, builds, and recorded evidence in one place.", button("Import source", "import", { icon: "plus" }))}${sourceSupport(ctx2)}${gameEditing}${scanControls(ctx2)}<section class="card task-checklist"><h3>Next steps</h3>${p.demo ? badge("Practice ROM") : ""}<div class="actions">${progress.steps.map((step) => button((step.complete ? "✓ " : "") + step.title, "navigate", { id: step.page })).join("")}</div></section><div class="stats">${stat("Sources", p.sources.length, "Owned copies; originals preserved", "resources")}${stat("Builds", p.builds.length, "Content identities stored in history", "check")}${stat("Test records", reports.length, "Measured scope shown per report", "shield")}${stat("Exports", exports.length, "Selected documentation and patches", "release")}</div><section class="card"><div class="card-heading"><h3>Files</h3><span class="subtle">${p.sources.length + p.builds.length} ${p.sources.length + p.builds.length === 1 ? "item" : "items"}</span></div>${[...p.sources, ...p.builds].slice(-6).map(resource).join("") || empty("Import your first source", "Add a game file or a resource extracted from your own project.", button("Import source", "import", { primary: true }))}</section>${buildHistory(ctx2, timeline)}${projectChecks(ctx2)}`;
  }
  function stat(title, value, note, ico) {
    return `<div class="stat"><div class="stat-top"><span>${title}</span>${icon(ico)}</div><strong>${value}</strong></div>`;
  }
  function steps() {
    return [["Choose a source", "Import your ROM or open a workshop."], ["Make a build", "Review your edits and save a separate build."], ["Test and export", "Playtest your build, then export a verified patch."]].map(([title, note], i) => `<div class="workflow-step"><span class="step-number">${i + 1}</span><div><strong>${title}</strong><p>${note}</p></div></div>`).join("");
  }
  function mount2(ctx2) {
    mountGameVisual(ctx2);
  }

  // romancer/ui/views/resources.js
  var resources_exports = {};
  __export(resources_exports, {
    mount: () => mount3,
    render: () => render6
  });

  // romancer/ui/hex_editor.js
  var HexDraft = class {
    constructor(state2, data) {
      this.scope = selectionKey(state2);
      this.original = /* @__PURE__ */ new Map();
      this.changes = /* @__PURE__ */ new Map();
      this.load(data);
      this.selected = data.offset;
    }
    load(data) {
      this.data = data;
      if (!Number.isSafeInteger(this.selected) || this.selected < data.offset || this.selected >= data.offset + data.length) this.selected = data.offset;
      const bytes = data.hex.match(/../g) || [];
      for (const offset of this.original.keys()) if (!this.changes.has(offset)) this.original.delete(offset);
      bytes.forEach((b, i) => this.original.set(data.offset + i, b));
    }
    set(offset, value) {
      if (offset < this.data.offset || offset >= this.data.offset + this.data.length || !this.original.has(offset)) throw Error("Choose a visible byte.");
      if (!/^[\da-f]{2}$/i.test(value)) throw Error("Enter two hex digits per byte.");
      value = value.toLowerCase();
      if (value === this.original.get(offset)) this.changes.delete(offset);
      else this.changes.set(offset, value);
    }
    edits(state2) {
      if (this.scope !== selectionKey(state2)) throw Error("The selection changed. Review bytes for the selected ROM.");
      return [...this.changes].sort(([a], [b]) => a - b).map(([offset, after]) => ({ offset, before: this.original.get(offset), after }));
    }
  };
  var integer3 = (value) => {
    const n = Number(value);
    if (!Number.isSafeInteger(n) || n < 0) throw Error("Enter a nonnegative decimal or 0x hex offset.");
    return n;
  };
  function serializeHexDraft(state2, draft) {
    return JSON.stringify({ artifact_id: state2.artifact.artifact_id, sha256: state2.artifact.sha256, edits: draft.edits(state2).map((e) => [e.offset, e.before, e.after]) });
  }
  function restoreHexDraft(state2, data, stored2) {
    const draft = new HexDraft(state2, data);
    if (!stored2) return draft;
    const value = JSON.parse(stored2);
    if (value.artifact_id !== state2.artifact.artifact_id || value.sha256 !== state2.artifact.sha256) throw Error("Saved byte edits belong to a different source.");
    if (!Array.isArray(value.edits) || value.edits.length > 16e3) throw Error("Saved byte draft exceeds the editing budget.");
    const seen = /* @__PURE__ */ new Set();
    for (const item of value.edits) {
      if (!Array.isArray(item) || item.length !== 3) throw Error("Invalid saved byte edit.");
      const [offset, before, after] = item;
      if (!Number.isSafeInteger(offset) || offset < 0 || offset >= state2.artifact.size || typeof before !== "string" || typeof after !== "string" || !/^[\da-f]{2}$/i.test(before) || !/^[\da-f]{2}$/i.test(after) || seen.has(offset)) throw Error("Invalid saved byte edit.");
      seen.add(offset);
      if (draft.original.has(offset) && draft.original.get(offset) !== before.toLowerCase()) throw Error("Saved original byte no longer matches this source.");
      if (before.toLowerCase() !== after.toLowerCase()) {
        draft.original.set(offset, before.toLowerCase());
        draft.changes.set(offset, after.toLowerCase());
      }
    }
    return draft;
  }
  function hexEditor(ctx2, data) {
    var _a, _b, _c, _d, _e, _f, _g, _h;
    const { state: state2 } = ctx2;
    if (data.artifact_id !== ((_a = state2.artifact) == null ? void 0 : _a.artifact_id) || data.sha256 !== ((_b = state2.artifact) == null ? void 0 : _b.sha256)) throw Error("The selected ROM changed. Load bytes for the current selection.");
    const ticket = selectionKey(state2);
    let draftError = "";
    if (((_c = state2.hexDraft) == null ? void 0 : _c.scope) !== ticket) {
      try {
        state2.hexDraft = restoreHexDraft(state2, data, ctx2.draft("hex-changes", null));
      } catch (error) {
        draftError = error.message;
        state2.hexDraft = null;
      }
    } else state2.hexDraft.load(data);
    if (draftError) {
      ctx2.use({ "hex-discard-invalid": () => {
        ctx2.setDraft("hex-changes", null);
        state2.hexDraft = null;
        return ctx2.render();
      } });
      return `<section class="card"><h3>Saved byte edits need attention</h3><p class="notice warm">${esc(draftError)}</p><p>Your ROM is unchanged. Discard this saved draft to reopen the editor.</p>${button("Discard invalid byte draft", "hex-discard-invalid")}</section>`;
    }
    if (Number.isSafeInteger(state2.resumeHexSelection) && state2.resumeHexSelection >= data.offset && state2.resumeHexSelection < data.offset + data.length) {
      state2.hexDraft.selected = state2.resumeHexSelection;
      delete state2.resumeHexSelection;
    }
    const draft = state2.hexDraft, current2 = () => selectionKey(state2) === ticket;
    const scoped = async (op, p) => {
      const result = await ctx2.run(op, { ...ctx2.sourceParams(), ...p }, { render: false });
      if (!current2()) throw Error("The selected ROM changed. Repeat this action.");
      return result;
    };
    const go = async (offset) => {
      const result = await scoped("resource.inspect", { offset: Math.min(integer3(offset), Math.max(0, state2.artifact.size - 1)), length: 256 });
      state2.results["resource.inspect"] = result;
      draft.selected = result.offset;
      ctx2.setDraft("hex-offset", String(result.offset));
      await ctx2.render();
    };
    ctx2.use({
      "hex-go": () => go(read("hex-offset")),
      "hex-page": (node) => go(Math.max(0, data.offset + Number(node.dataset.id))),
      "hex-jump": (node) => go(node.dataset.id),
      "hex-clear": () => {
        state2.hexDraft = new HexDraft(state2, data);
        ctx2.setDraft("hex-changes", serializeHexDraft(state2, state2.hexDraft));
        state2.hexReview = null;
        return ctx2.render();
      },
      "hex-search": async () => {
        state2.hexSearch = { scope: ticket, result: await scoped("hex.search", { kind: read("hex-search-kind"), query: read("hex-search-query"), start: integer3(read("hex-search-start")), endian: read("hex-endian"), width: Number(read("hex-width")), signed: read("hex-signed") === "true" }) };
        await ctx2.render();
      },
      "hex-search-more": async () => {
        var _a2, _b2;
        const next = (_b2 = (_a2 = state2.hexSearch) == null ? void 0 : _a2.result) == null ? void 0 : _b2.next_start;
        if (next === null || next === void 0) return;
        ctx2.setDraft("hex-search-start", String(next));
        await ctx2.render();
      },
      "hex-explain": async () => {
        state2.hexExplanation = { scope: ticket, result: await scoped("resources.explain", { offset: draft.selected }) };
        return ctx2.render();
      },
      "hex-numbers": async () => {
        state2.hexNumbers = { scope: ticket, result: await scoped("hex.numbers", { offset: draft.selected }) };
        await ctx2.render();
      },
      "hex-bookmarks": async () => {
        state2.hexBookmarks = { scope: ticket, result: await scoped("hex.bookmarks", {}) };
        await ctx2.render();
      },
      "hex-bookmark": async () => {
        state2.hexBookmarks = { scope: ticket, result: await scoped("hex.bookmark", { offset: draft.selected, name: read("hex-bookmark-name"), remove: false }) };
        await ctx2.render();
      },
      "hex-unbookmark": async (node) => {
        state2.hexBookmarks = { scope: ticket, result: await scoped("hex.bookmark", { offset: Number(node.dataset.id), name: "", remove: true }) };
        await ctx2.render();
      },
      "hex-review": async () => {
        if (document.querySelector("#hex-editor input:invalid")) throw Error("Finish the byte with two hex digits first.");
        const edits = draft.edits(state2);
        if (!edits.length) throw Error("Change one or more byte cells first.");
        const signature = JSON.stringify(edits), source = state2.artifact;
        const plan = await scoped(source.system_id ? "systems.plan_edits" : "bytes.plan", { edits });
        if (JSON.stringify(draft.edits(state2)) !== signature) throw Error("Bytes changed during review. Review them again.");
        state2.hexReview = { scope: ticket, signature, plan };
        await ctx2.render();
      },
      "hex-apply": async () => {
        const reviewed2 = state2.hexReview;
        if ((reviewed2 == null ? void 0 : reviewed2.scope) !== ticket || reviewed2.signature !== JSON.stringify(draft.edits(state2))) throw Error("Review the current byte edits first.");
        const built = await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: reviewed2.plan.plan_id }, { render: false });
        if (!current2()) return;
        if (state2.hexReview !== reviewed2 || JSON.stringify(draft.edits(state2)) !== reviewed2.signature) {
          ctx2.notify("Build created. Your newer byte edits are still staged.");
          return;
        }
        state2.hexReview = null;
        ctx2.setDraft("hex-changes", JSON.stringify({ artifact_id: state2.artifact.artifact_id, sha256: state2.artifact.sha256, edits: [] }));
        state2.hexDraft = null;
        await ctx2.refreshProject();
        await ctx2.setArtifact(built.artifact_id);
        ctx2.notify("Separate build created.");
        await ctx2.navigate("overview");
      }
    });
    const bytes = data.hex.match(/../g) || [], search = ((_d = state2.hexSearch) == null ? void 0 : _d.scope) === ticket ? state2.hexSearch.result : null, numbers = ((_e = state2.hexNumbers) == null ? void 0 : _e.scope) === ticket && state2.hexNumbers.result.offset === draft.selected ? state2.hexNumbers.result : null, marks = ((_f = state2.hexBookmarks) == null ? void 0 : _f.scope) === ticket ? state2.hexBookmarks.result : null;
    const reviewed = ((_g = state2.hexReview) == null ? void 0 : _g.scope) === ticket && state2.hexReview.signature === JSON.stringify(draft.edits(state2));
    return `<section class="card" id="hex-editor"><div class="card-heading"><h3>Hex editor</h3>${badge(`${draft.changes.size} staged bytes`)}</div>
 <div class="toolbar">${field("hex-offset", "Offset", ctx2.draft("hex-offset", data.offset))}${button("Go", "hex-go")}${button("Previous page", "hex-page", { id: "-256", disabled: data.offset === 0 })}${button("Next page", "hex-page", { id: "256", disabled: data.offset + data.length >= state2.artifact.size })}</div>
 <div class="hex-scroll"><div class="hex-edit-grid" aria-label="Editable hex bytes">${Array.from({ length: Math.ceil(bytes.length / 16) }, (_, row) => {
      var _a2;
      return `<div class="hex-edit-row"><code>${(data.offset + row * 16).toString(16).padStart(8, "0")}</code><div class="hex-edit-cells">${bytes.slice(row * 16, row * 16 + 16).map((b, i) => {
        const offset = data.offset + row * 16 + i;
        return `<input aria-label="Byte 0x${offset.toString(16)}" data-hex-offset="${offset}" value="${draft.changes.get(offset) || b}" maxlength="2" size="2" spellcheck="false" class="hex-cell ${draft.changes.has(offset) ? "changed" : ""}">`;
      }).join("")}</div><code>${esc(((_a2 = data.text) == null ? void 0 : _a2.slice(row * 16, row * 16 + 16)) || "")}</code></div>`;
    }).join("")}</div></div>
 <p class="subtle">Edit a byte, then review. Your source stays unchanged. Arrow keys move between bytes.</p><div class="actions">${button("Review byte edits", "hex-review", { primary: true, disabled: !draft.changes.size })}${button("Create separate build", "hex-apply", { disabled: !reviewed })}${button("Discard byte edits", "hex-clear", { disabled: !draft.changes.size })}</div>
 ${reviewed ? `<div class="notice">${state2.hexReview.plan.changed_bytes} bytes in the reviewed plan, including supported checksum repairs.</div>` : ""}
 <details><summary>Search bytes, text or numbers</summary><div class="field-row">${select("hex-search-kind", "Search for", [["hex", "Hex pattern (?? wildcard)"], ["text", "UTF-8 text"], ["number", "Integer"]], ctx2.draft("hex-search-kind", "hex"))}${field("hex-search-query", "Pattern or value", ctx2.draft("hex-search-query", ""))}${field("hex-search-start", "Start offset", ctx2.draft("hex-search-start", "0"))}</div><div class="field-row">${select("hex-endian", "Byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("hex-endian", "little"))}${select("hex-width", "Number width", [[1, "8-bit"], [2, "16-bit"], [4, "32-bit"]], ctx2.draft("hex-width", "2"))}${select("hex-signed", "Number sign", [["false", "Unsigned"], ["true", "Signed"]], ctx2.draft("hex-signed", "false"))}</div>${button("Search selected file", "hex-search")}
 ${search ? `<p>${search.offsets.length} matches · ${search.complete ? "Reached end of file" : `Scanned through 0x${search.scanned_to.toString(16)}`}</p><div class="actions">${search.offsets.slice(0, 1e3).map((o) => button("0x" + o.toString(16), "hex-jump", { id: String(o) })).join("")}</div>${search.complete ? "" : button("Set next search position", "hex-search-more")}` : ""}</details>
 <details><summary>Number inspector & bookmarks</summary><p>Selected offset: <code id="hex-selected">0x${draft.selected.toString(16)}</code></p>${button("Explain selected bytes", "hex-explain")}${button("Inspect selected number", "hex-numbers")}<div id="hex-explanation">${((_h = state2.hexExplanation) == null ? void 0 : _h.scope) === ticket && state2.hexExplanation.result.offset === draft.selected ? `<p>${esc(state2.hexExplanation.result.note)}</p>${state2.hexExplanation.result.interpretations.map((row) => `<dl><dt>${esc(row.name)} · declared</dt><dd>File offset 0x${row.offset.toString(16)} · ${row.length} bytes${row.type ? " · " + esc(row.type) + " " + esc(row.endian) + " · value " + esc(row.value) + " · numeric range " + row.minimum + "–" + row.maximum : ""}${row.description ? "<br>" + esc(row.description) : ""}</dd></dl>`).join("")}` : ""}</div><div id="hex-number-result">${numbers ? `<dl>${Object.entries(numbers.values).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` : ""}</div>${field("hex-bookmark-name", "Bookmark name", ctx2.draft("hex-bookmark-name", ""))}<div class="actions">${button("Bookmark selected byte", "hex-bookmark")}${button("Load bookmarks", "hex-bookmarks")}</div>${((marks == null ? void 0 : marks.bookmarks) || []).map((r) => `<div class="actions">${button(`${r.name} · 0x${r.offset.toString(16)}`, "hex-jump", { id: String(r.offset) })}${button("Remove", "hex-unbookmark", { id: String(r.offset) })}</div>`).join("")}</details></section>`;
  }
  async function hexComparison(ctx2, data) {
    const saved = ctx2.state.hexComparison, a = ctx2.state.artifact, p = ctx2.state.project, scope = selectionKey(ctx2.state);
    if (!saved || saved.project_id !== p.project_id || saved.right_id !== a.artifact_id || saved.right_sha256 !== a.sha256) return "";
    const left = p.sources.concat(p.builds).find((r) => r.artifact_id === saved.left_id);
    if (!left || left.sha256 !== saved.left_sha256) return "";
    const maximum = Math.max(left.size, a.size), offset = saved.offset ?? data.offset;
    if (!Number.isSafeInteger(offset) || offset < 0 || offset > maximum) return "";
    const length = Math.max(1, Math.min(256, maximum - offset));
    const readSide = (row) => ctx2.api.call("resource.inspect", { project_id: p.project_id, artifact_id: row.artifact_id, offset: Math.min(offset, row.size), length });
    const [original, selected2] = await Promise.all([readSide(left), readSide(a)]);
    if (selectionKey(ctx2.state) !== scope || ctx2.state.hexComparison !== saved) return "";
    if (original.artifact_id !== left.artifact_id || original.sha256 !== left.sha256 || selected2.artifact_id !== a.artifact_id || selected2.sha256 !== a.sha256) throw Error("The compared source changed. Compare these files again.");
    ctx2.use({ "hex-diff-page": async (node) => {
      if (selectionKey(ctx2.state) !== scope || ctx2.state.hexComparison !== saved) throw Error("The selected comparison changed. Compare these files again.");
      const delta = Number(node.dataset.id);
      if (![-256, 256].includes(delta)) throw Error("Invalid comparison page.");
      saved.offset = Math.max(0, Math.min(Math.max(0, maximum - 1), offset + delta));
      await ctx2.render();
    }, "hex-diff-follow": async () => {
      if (selectionKey(ctx2.state) !== scope || ctx2.state.hexComparison !== saved) throw Error("The selected comparison changed.");
      delete saved.offset;
      await ctx2.render();
    } });
    const x = original.hex.match(/../g) || [], y = selected2.hex.match(/../g) || [], span = Math.max(x.length, y.length);
    const cells = (values, other, index) => Array.from({ length: Math.min(16, span - index) }, (_, j) => {
      const value = values[index + j];
      return value === void 0 ? '<span aria-label="No byte in file">—</span>' : value !== other[index + j] ? `<mark>${value}</mark>` : value;
    }).join(" ");
    return `<details class="card hex-comparison" open><summary>Compare at 0x${offset.toString(16)}</summary><p>${esc(left.name)} → ${esc(a.name)}</p><p>Changed bytes are highlighted. — means this file has no byte at that offset.</p><div class="actions">${button("Previous comparison page", "hex-diff-page", { id: "-256", disabled: offset === 0 })}${button("Next comparison page", "hex-diff-page", { id: "256", disabled: offset + span >= maximum })}${button("Follow hex editor", "hex-diff-follow")}</div><div class="hex-scroll"><table><thead><tr><th>Offset</th><th>Earlier bytes</th><th>Selected bytes</th></tr></thead><tbody>${Array.from({ length: Math.ceil(span / 16) }, (_, i) => `<tr><td><code>${(offset + i * 16).toString(16)}</code></td><td><code>${cells(x, y, i * 16)}</code></td><td><code>${cells(y, x, i * 16)}</code></td></tr>`).join("")}</tbody></table></div></details>`;
  }
  function mountHexEditor(ctx2) {
    const root = document.getElementById("hex-editor");
    if (!root) return;
    const draft = ctx2.state.hexDraft;
    root.querySelectorAll("[data-hex-offset]").forEach((node) => {
      node.addEventListener("focus", () => {
        var _a, _b, _c, _d, _e, _f;
        if (draft.scope !== selectionKey(ctx2.state)) return;
        draft.selected = Number(node.dataset.hexOffset);
        if (((_a = ctx2.state.hexExplanation) == null ? void 0 : _a.result.offset) !== draft.selected) {
          ctx2.state.hexExplanation = null;
          (_c = (_b = root.querySelector("#hex-explanation")) == null ? void 0 : _b.replaceChildren) == null ? void 0 : _c.call(_b);
        }
        if (((_d = ctx2.state.hexNumbers) == null ? void 0 : _d.result.offset) !== draft.selected) {
          ctx2.state.hexNumbers = null;
          (_f = (_e = root.querySelector("#hex-number-result")) == null ? void 0 : _e.replaceChildren) == null ? void 0 : _f.call(_e);
        }
        const label = root.querySelector("#hex-selected");
        if (label) label.textContent = "0x" + draft.selected.toString(16);
        node.select();
      });
      node.addEventListener("input", () => {
        ctx2.state.hexReview = null;
        setUnavailable(root.querySelector('[data-action="hex-apply"]'), true);
        try {
          draft.set(Number(node.dataset.hexOffset), node.value);
          ctx2.setDraft("hex-changes", serializeHexDraft(ctx2.state, draft));
          node.setCustomValidity("");
          node.classList.toggle("changed", draft.changes.has(Number(node.dataset.hexOffset)));
          setUnavailable(root.querySelector('[data-action="hex-review"]'), !draft.changes.size);
          setUnavailable(root.querySelector('[data-action="hex-clear"]'), !draft.changes.size);
        } catch (error) {
          node.setCustomValidity(error.message);
        }
      });
      node.addEventListener("blur", () => {
        if (!node.checkValidity()) {
          node.reportValidity();
          node.value = draft.changes.get(Number(node.dataset.hexOffset)) || draft.original.get(Number(node.dataset.hexOffset));
          node.setCustomValidity("");
        }
      });
      node.addEventListener("keydown", (event) => {
        const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -16, ArrowDown: 16 }[event.key];
        if (delta) {
          const next = root.querySelector(`[data-hex-offset="${Number(node.dataset.hexOffset) + delta}"]`);
          if (next) {
            event.preventDefault();
            next.focus();
          }
        }
      });
    });
  }

  // romancer/ui/revision_controls.js
  function revisionResult(state2) {
    const saved = state2.revisionLookup;
    return (saved == null ? void 0 : saved.scope) === selectionKey(state2) ? saved.result : null;
  }
  async function identifyRevision(ctx2, scope, expected_id) {
    var _a;
    const ticket = selectionKey(ctx2.state), request2 = (ctx2.state.revisionRequest || 0) + 1;
    ctx2.state.revisionRequest = request2;
    const result = await ctx2.run("revision.lookup", { ...((_a = ctx2.sourceParams) == null ? void 0 : _a.call(ctx2)) || { project_id: ctx2.state.project.project_id, artifact_id: ctx2.state.artifact.artifact_id }, scope, expected_id }, { render: false });
    if (ticket !== selectionKey(ctx2.state) || request2 !== ctx2.state.revisionRequest) throw Error("The selection changed. Identify the selected ROM again.");
    ctx2.state.revisionLookup = { scope: ticket, result };
    return result;
  }
  function revisionControls(ctx2) {
    var _a, _b, _c;
    const { state: state2 } = ctx2, project = (_a = state2.project) == null ? void 0 : _a.project_id, result = revisionResult(state2), info = ((_b = state2.revisionInfo) == null ? void 0 : _b.project_id) === project ? state2.revisionInfo : null, list = ((_c = state2.revisionList) == null ? void 0 : _c.project_id) === project ? state2.revisionList : null;
    ctx2.use({
      "revision-info": async () => {
        var _a2;
        const r = await ctx2.run("revision.info", { project_id: project }, { render: false });
        if (((_a2 = state2.project) == null ? void 0 : _a2.project_id) === project) {
          state2.revisionInfo = r;
          await ctx2.render();
        }
      },
      "revision-import": async () => {
        var _a2, _b2, _c2;
        const file = (_a2 = document.getElementById("revision-file")) == null ? void 0 : _a2.files[0];
        if (!file) throw Error("Choose a local catalog first.");
        const scope = read("revision-scope");
        const input = await ctx2.api.uploadInput(project, file, "catalog");
        if (((_b2 = state2.project) == null ? void 0 : _b2.project_id) !== project) throw Error("The project changed. Import into the selected project again.");
        const r = await ctx2.run("revision.import", { project_id: project, input_id: input.input_id, scope }, { render: false });
        if (((_c2 = state2.project) == null ? void 0 : _c2.project_id) === project) {
          state2.revisionInfo = r;
          state2.revisionList = null;
          state2.revisionLookup = null;
          state2.romScans = {};
          ctx2.notify(`${r.count} revision references available.`);
          await ctx2.render();
        }
      },
      "revision-identify": async () => {
        await identifyRevision(ctx2, read("revision-scope"), "");
        await ctx2.render();
      },
      "revision-search": async () => {
        var _a2;
        const r = await ctx2.run("revision.list", { project_id: project, query: read("revision-query") }, { render: false });
        if (((_a2 = state2.project) == null ? void 0 : _a2.project_id) === project) {
          state2.revisionList = r;
          await ctx2.render();
        }
      },
      "revision-compare": async () => {
        var _a2;
        const id = read("revision-expected"), entry = (_a2 = list == null ? void 0 : list.entries) == null ? void 0 : _a2.find((r) => r.id === id);
        if (!entry) throw Error("Search for and choose a reference first.");
        await identifyRevision(ctx2, entry.scope, id);
        await ctx2.render();
      }
    });
    const message = result ? { MATCHED: "Exact revision matched", UNKNOWN: "No catalog match", MISMATCHED: "Selected reference differs", AMBIGUOUS: "Multiple references match" }[result.status] || result.status : "";
    return `<details class="card"><summary>Identify ROM revision${info ? ` · ${info.count} references` : ""}</summary><p>Compare checksums with a catalog you supply. Unknown files remain unidentified.</p>
 ${select("revision-scope", "Checksum scope", [["file", "Whole file"], ["payload", "Cartridge payload (supported layouts)"]], ctx2.draft("revision-scope", "file"))}
 ${fileInput("revision-file", "Local JSON, CSV, TSV or XML DAT catalog", ".json,.csv,.tsv,.dat,.xml")}<div class="actions">${button("Import catalog", "revision-import")}${button("Check catalog size", "revision-info")}${button("Identify selected ROM", "revision-identify", { disabled: !state2.artifact, primary: true })}</div>
 ${result ? `<div class="notice">${badge(message, result.status === "MATCHED" ? "good" : result.status === "MISMATCHED" ? "warm" : "neutral")}<p>${result.matches.map((r) => esc(r.name)).join("<br>")}</p><p>${esc(result.scope === "file" ? "Whole file" : "Cartridge payload")} · CRC32 <code>${esc(result.hashes.crc32)}</code></p>${result.status === "MISMATCHED" ? "<p>Choose the correct revision or check the checksum scope before applying a patch.</p>" : ""}</div>` : ""}
 <details><summary>Compare a specific reference</summary>${field("revision-query", "Reference name", ctx2.draft("revision-query", ""))}${button("Find references", "revision-search")}${list ? `${select("revision-expected", "Expected reference", list.entries.map((r) => [r.id, `${r.name} · ${r.scope}`]), ctx2.draft("revision-expected", ""))}${list.truncated ? "<p>Narrow your search to see more references.</p>" : ""}${button("Compare selected reference", "revision-compare", { disabled: !list.entries.length || !state2.artifact })}` : ""}</details></details>`;
  }

  // romancer/ui/compression_controls.js
  function integer4(id) {
    const text = read(id).trim(), value = Number(text);
    if (!text || !Number.isSafeInteger(value)) throw new Error("Enter a whole number for " + id + ".");
    return value;
  }
  function compressedRoot(state2, artifact = state2.artifact) {
    var _a, _b;
    const rows = new Map([...((_a = state2.project) == null ? void 0 : _a.sources) || [], ...((_b = state2.project) == null ? void 0 : _b.builds) || []].map((row) => [row.artifact_id, row]));
    const seen = /* @__PURE__ */ new Set();
    for (let i = 0; artifact && i < 128; i++) {
      if (artifact.compressed_parent) return artifact;
      if (seen.has(artifact.artifact_id)) return null;
      seen.add(artifact.artifact_id);
      artifact = rows.get(artifact.source_id);
    }
    return null;
  }
  function resourceSystem(state2) {
    var _a, _b, _c;
    return ((_a = state2.artifact) == null ? void 0 : _a.system_id) || ((_b = state2.artifact) == null ? void 0 : _b.system_hint) || ((_c = compressedRoot(state2)) == null ? void 0 : _c.system_hint) || "nes";
  }
  function compressionControls(ctx2) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2, artifact = state2.artifact;
    if (!artifact) return "";
    const root = compressedRoot(state2), metadata = root == null ? void 0 : root.compressed_parent;
    const result = ((_a = state2.results["compression.inspect"]) == null ? void 0 : _a.parent_sha256) === artifact.sha256 ? state2.results["compression.inspect"] : null;
    const extraction = state2.results["compression.extract"];
    const extracted = extraction && ((_b = extraction.inspection) == null ? void 0 : _b.parent_sha256) === artifact.sha256 ? extraction.artifact : null;
    const builds = metadata ? state2.project.builds.filter((row) => {
      var _a2;
      return ((_a2 = compressedRoot(state2, row)) == null ? void 0 : _a2.artifact_id) === root.artifact_id;
    }) : [];
    const parameters = () => ({ ...ctx2.sourceParams(), offset: integer4("compression-offset"), allocation: integer4("compression-allocation"), codec: read("compression-codec") });
    ctx2.use({
      "compression-inspect": () => ctx2.run("compression.inspect", parameters()),
      "compression-extract": () => ctx2.run("compression.extract", parameters()),
      "compression-open": async (node) => {
        await ctx2.setArtifact(node.dataset.id);
        await ctx2.navigate("resources");
      },
      "compression-review": async () => {
        if (!metadata) throw new Error("Select an owned extracted resource first.");
        const edited_id = read("compression-edited");
        if (!edited_id) throw new Error("Create an edited build of the decoded resource first.");
        const plan = await ctx2.run("compression.plan_reinsert", { ...ctx2.projectParams(), parent_id: metadata.parent_id, decoded_id: root.artifact_id, edited_id, offset: metadata.offset, allocation: metadata.allocation, codec: metadata.codec }, { render: false });
        state2.pending = { kind: "compression", artifact_id: artifact.artifact_id, plan_id: plan.plan_id };
        await ctx2.render();
      },
      "compression-build": async () => {
        var _a2;
        if (((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "compression" || state2.pending.artifact_id !== artifact.artifact_id) throw new Error("Review reinsertion for this resource first.");
        const built = await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: state2.pending.plan_id }, { render: false });
        state2.pending = null;
        await ctx2.setArtifact(built.artifact_id);
        ctx2.notify("Parent build created and selected. Open Playtest to check it.");
      }
    });
    if (metadata) return `<section class="card"><div class="card-heading"><h3>Compressed resource</h3>${button("Compression help", "help-topic", { id: "compression" })}</div><p>${esc(metadata.codec)} at0x${metadata.offset.toString(16)} · ${size(metadata.allocation)} allocated.</p><p>Edit this decoded resource and create a build, then review reinsertion into its parent.</p><div class="actions">${button("Edit graphics", "navigate", { id: "assets" })}${button("Edit text", "navigate", { id: "scripts" })}${button("Edit tables", "navigate", { id: "tables" })}</div>${select("compression-edited", "Edited decoded build", builds.map((row) => [row.artifact_id, row.name]), artifact.kind === "build" ? artifact.artifact_id : (_c = builds.at(-1)) == null ? void 0 : _c.artifact_id)}<div class="actions">${button("Review reinsertion", "compression-review", { primary: true, disabled: !builds.length })}${((_d = state2.pending) == null ? void 0 : _d.kind) === "compression" ? button("Create parent build", "compression-build", { primary: true }) : ""}</div>${report(state2.results["compression.plan_reinsert"], "Recompression plan")}</section>`;
    return `<details class="card" ${result || extracted ? "open" : ""}><summary>Compressed resources</summary><p>Confirm the codec and allocated space before extracting. Supported formats: GBA LZ10 and RLE.</p><div class="field-row">${field("compression-offset", "Stream offset", ctx2.draft("compression-offset", "0"))}${field("compression-allocation", "Confirmed allocation in bytes (up to48KiB)", ctx2.draft("compression-allocation", "1024"))}${select("compression-codec", "Codec", [["gba-lz10", "GBA LZ10"], ["gba-rle", "GBA RLE"]], ctx2.draft("compression-codec", "gba-lz10"))}</div><div class="actions">${button("Inspect stream", "compression-inspect")}${button("Extract decoded resource", "compression-extract", { primary: true })}${button("Compression help", "help-topic", { id: "compression" })}</div>${result ? `<p class="notice">${size(result.consumed)} stored → ${size(result.decoded_size)} decoded. Confirmed allocation: ${size(result.allocation)}.</p>` : ""}${extracted ? `<p>Decoded resource added to this project.</p>${button("Open decoded resource", "compression-open", { id: extracted.artifact_id, primary: true })}` : ""}</details>`;
  }

  // romancer/ui/rom_health.js
  function romHealthPanel(ctx2) {
    var _a, _b, _c;
    const { state: state2 } = ctx2, result = state2.results["rom.check"], r = (result == null ? void 0 : result.artifact_id) === ((_a = state2.artifact) == null ? void 0 : _a.artifact_id) && ((_b = result == null ? void 0 : result.source) == null ? void 0 : _b.sha256) === ((_c = state2.artifact) == null ? void 0 : _c.sha256) ? result : null, c = r == null ? void 0 : r.crc_comparison;
    const tone = checkTone;
    return `<section class="card rom-health"><div class="card-heading"><h2>ROM health</h2>${r ? badge(r.status === "ISSUES_FOUND" ? "Issues found" : r.status === "WARNINGS_FOUND" ? "Needs attention" : "Checks finished", r.status === "ISSUES_FOUND" ? "danger" : r.status === "WARNINGS_FOUND" ? "warm" : "neutral") : ""}</div><div class="toolbar">${field("rom-expected-crc", "Expected CRC32 (optional)", ctx2.draft("rom-expected-crc", ""), { placeholder: "Eight hex digits", hint: "Use the reference supplied with your patch or dump." })}${select("rom-crc-scope", "CRC32 comparison covers", [["file", "Whole file"], ["payload", "Cartridge payload"]], ctx2.draft("rom-crc-scope", "file"))}${button("Check ROM", "rom-check", { primary: true, icon: "shield" })}</div>${r ? `<div class="identity"><strong>File CRC32</strong><code>${esc(r.crc32)}</code><span>${esc((c == null ? void 0 : c.scope) === "payload" ? "Reference compares cartridge payload" : "Reference compares whole file")}</span></div><div class="notice ${(c == null ? void 0 : c.status) === "FAIL" ? "danger" : ""}"><strong>${(c == null ? void 0 : c.status) === "FAIL" ? "CRC32 mismatch" : (c == null ? void 0 : c.status) === "PASS" ? "Reference CRC32 matches" : "No reference supplied"}</strong>${(c == null ? void 0 : c.expected) ? ` · Expected <code>${esc(c.expected)}</code> · Measured <code>${esc(c.measured)}</code>` : " · The file fingerprint was measured; no dump match was checked."}</div><div class="table-wrap"><table><thead><tr><th>Check</th><th>Result</th><th>Details</th></tr></thead><tbody>${(r.checks || []).map((check) => `<tr><td>${esc(check.name)}</td><td>${badge(checkLabel(check.status), tone(check.status))}</td><td>${esc(check.detail)}${check.stored !== void 0 ? ` Stored <code>${esc(check.stored)}</code>${check.computed !== void 0 ? `; computed <code>${esc(check.computed)}</code>` : check.expected !== void 0 ? `; expected <code>${esc(check.expected)}</code>` : ""}.` : ""}</td></tr>`).join("")}</tbody></table></div><p class="subtle">These checks do not establish authenticity or successful gameplay.</p><details><summary>Full health report</summary><pre>${esc(JSON.stringify(r, null, 2))}</pre></details>` : '<p class="subtle">Checks cartridge layout and supported internal checksums. A reference is needed to detect a CRC32 mismatch.</p>'}</section>`;
  }

  // romancer/ui/discovery_controls.js
  var systems2 = [["nes", "NES"], ["snes", "SNES"], ["genesis", "GEN"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]];
  function integer5(id) {
    const text = read(id).trim(), value = Number(text);
    if (!text || !Number.isSafeInteger(value)) throw new Error("Enter a whole number for " + id + ".");
    return value;
  }
  function discoveryControls(ctx2) {
    var _a;
    const { state: state2 } = ctx2, artifact = state2.artifact;
    if (!artifact) return "";
    const result = ((_a = state2.results["resources.discover"]) == null ? void 0 : _a.source_sha256) === artifact.sha256 ? state2.results["resources.discover"] : null;
    ctx2.use({
      "discover-scan": async () => {
        const kind = read("discover-kind");
        state2.discoveryPage = 0;
        const kinds = kind === "all" ? ["text", "graphics", "compression"] : [kind];
        const target = kind === "pointers" ? { offset: integer5("discover-target"), width: integer5("discover-width"), endian: read("discover-endian"), base: integer5("discover-base") } : null;
        return ctx2.run("resources.discover", { ...ctx2.sourceParams(), config: { system_id: read("discover-system"), start: integer5("discover-start"), length: integer5("discover-length"), kinds, target } });
      },
      "discover-compressed": async (node) => {
        const row = result == null ? void 0 : result.candidates.find((row2) => row2.candidate_id === node.dataset.id);
        if ((row == null ? void 0 : row.kind) !== "compression") throw new Error("Scan this compressed source again.");
        ctx2.setDraft("compression-offset", String(row.offset));
        ctx2.setDraft("compression-allocation", String(row.length));
        ctx2.setDraft("compression-codec", row.format);
        await ctx2.run("compression.inspect", { ...ctx2.sourceParams(), offset: row.offset, allocation: row.length, codec: row.format });
      },
      "discover-page": (node) => {
        state2.discoveryPage = Math.max(0, (state2.discoveryPage || 0) + Number(node.dataset.id));
        return ctx2.render();
      },
      "discover-inspect": (node) => {
        const row = result == null ? void 0 : result.candidates.find((row2) => row2.candidate_id === node.dataset.id);
        if (!row) throw new Error("Scan this source revision again.");
        return ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset: row.offset, length: Math.min(row.length, 256) });
      },
      "discover-declare": async (node) => {
        const row = result == null ? void 0 : result.candidates.find((row2) => row2.candidate_id === node.dataset.id);
        if (!(row == null ? void 0 : row.config)) throw new Error("This candidate needs a supported resource declaration.");
        const prefix = row.kind === "text" ? "text" : "gfx";
        state2.candidateReview = { artifact_id: artifact.artifact_id, kind: row.kind, reason: row.reason };
        state2.resourcePrefill = { artifact_id: artifact.artifact_id, prefix, config: row.config };
        delete state2.results["script.inspect"];
        delete state2.results["assets.inspect"];
        state2.pending = null;
        state2.paint = null;
        await ctx2.navigate(row.kind === "text" ? "scripts" : "assets");
      }
    });
    const page = state2.discoveryPage || 0, rows = (result == null ? void 0 : result.candidates.slice(page * 20, page * 20 + 20)) || [];
    return `<section class="card"><div class="card-heading"><h3>Find resources</h3>${button("Discovery help", "help-topic", { id: "discovery" })}</div><div class="field-row">${select("discover-system", "System", systems2, ctx2.draft("discover-system", resourceSystem(state2)))}${select("discover-kind", "Look for", [["all", "Text, graphics and known compression"], ["text", "Printable text"], ["graphics", "Graphics candidates"], ["compression", "Known compressed streams"], ["pointers", "Explicit pointer references"]], ctx2.draft("discover-kind", "all"))}${field("discover-start", "Start offset", ctx2.draft("discover-start", "0"))}${field("discover-length", "Bytes to scan (up to16MiB)", ctx2.draft("discover-length", String(Math.min(1024 * 1024, artifact.size))))}</div><details class="config"><summary>Pointer search settings</summary><div class="field-row">${field("discover-target", "Target file offset", ctx2.draft("discover-target", "0"))}${select("discover-width", "Pointer bytes", [["2", "2"], ["3", "3"], ["4", "4"]], ctx2.draft("discover-width", "2"))}${select("discover-endian", "Byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("discover-endian", "little"))}${field("discover-base", "Stored value = file offset + base", ctx2.draft("discover-base", "0"))}</div></details>${button("Scan selected range", "discover-scan", { primary: true, icon: "search" })}${result ? `<p class="notice">${result.candidates.length} candidates in${size(result.scanned_length)}. ${result.partial ? "Partial scan. " : ""}${result.next_offset !== null ? "Next range starts at0x" + result.next_offset.toString(16) + ". " : ""}${result.results_truncated ? "Result limit reached; narrow the range. " : ""}Graphics use sampled blocks. Confirm formats before editing.</p>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Resource</th><th>Preview</th><th>Reason</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.kind)}<br><code>0x${row.offset.toString(16)}</code><br>${esc(row.confidence)}</td><td>${esc(row.preview)}</td><td>${esc(row.reason)}</td><td><div class="actions">${button("Inspect bytes", "discover-inspect", { id: row.candidate_id })}${row.kind === "compression" ? button("Inspect stream", "discover-compressed", { id: row.candidate_id }) : row.config ? button("Review declaration", "discover-declare", { id: row.candidate_id }) : ""}</div></td></tr>`).join("")}</tbody></table></div><div class="actions">${button("Previous candidates", "discover-page", { id: "-1", disabled: page === 0 })}<span>Page ${page + 1}</span>${button("Next candidates", "discover-page", { id: "1", disabled: (page + 1) * 20 >= result.candidates.length })}</div>` : "<p>No candidates in this range. Try a different range or declare a known resource.</p>"}` : ""}</section>`;
  }

  // romancer/ui/views/resources.js
  async function render6(ctx2) {
    var _a, _b, _c;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    const a = state2.artifact, ticket = selectionKey(state2), generation = (state2.resourceRenderGeneration || 0) + 1;
    state2.resourceRenderGeneration = generation;
    const current2 = () => ticket === selectionKey(state2) && generation === state2.resourceRenderGeneration && (!ctx2.isCurrentRender || ctx2.isCurrentRender()), params = a ? { ...ctx2.sourceParams() } : null;
    if (!current2()) return "";
    const jump = state2.resourceJump;
    let data = state2.results["resource.inspect"], catalog, comparison = "", byteNotes = "";
    if (a) {
      if (jump !== void 0 && jump !== null || (data == null ? void 0 : data.artifact_id) !== a.artifact_id || (data == null ? void 0 : data.sha256) !== a.sha256) {
        data = await ctx2.api.call("resource.inspect", { ...params, offset: jump == null ? 0 : Math.min(parseInteger(jump), Math.max(0, a.size - 1)), length: 256 });
        if (!current2()) return "";
      }
      catalog = await ctx2.api.call("catalog.list", { ...params, query: state2.catalogQuery || "", page: state2.catalogPage || 0, limit: 50 });
      if (!current2()) return "";
      comparison = await hexComparison(ctx2, data);
      if (!current2()) return "";
      byteNotes = await gameByteNotes(ctx2, data);
      if (!current2()) return "";
      state2.results["resource.inspect"] = data;
      if (jump !== void 0 && jump !== null) {
        ctx2.setDraft("hex-offset", String(data.offset));
        state2.resourceJump = null;
      }
    }
    const relationships = a ? await resourceRelationships(ctx2) : "";
    if (!current2()) return "";
    let assessment = state2.results["systems.identify"];
    if ((assessment == null ? void 0 : assessment.artifact_id) !== (a == null ? void 0 : a.artifact_id)) assessment = a && ((_b = (_a = a.system_assessment) == null ? void 0 : _a.source) == null ? void 0 : _b.sha256) === a.sha256 ? a.system_assessment : null;
    ctx2.use({
      "rom-check": () => ctx2.run("rom.check", { ...ctx2.sourceParams(), expected_crc32: read("rom-expected-crc").trim(), crc_scope: read("rom-crc-scope") }),
      "catalog-index": () => ctx2.run("catalog.index", ctx2.sourceParams()),
      "catalog-search": () => {
        state2.catalogPage = 0;
        state2.catalogQuery = read("catalog-query");
        return ctx2.render();
      },
      "catalog-page": (node) => {
        state2.catalogPage = Math.max(0, (state2.catalogPage || 0) + Number(node.dataset.id));
        return ctx2.render();
      },
      "catalog-open": (node) => ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset: Number(node.dataset.id), length: Math.min(256, Number(node.dataset.name)) }),
      "definitions-reuse": async () => {
        await ctx2.run("resources.reuse_definitions", ctx2.sourceParams(), { render: false });
        for (const key3 of ["assets.inspect", "script.inspect", "tables.inspect", "levels.inspect", "sound.inspect"]) delete state2.results[key3];
        await ctx2.render();
        ctx2.notify("Resource setup rechecked against this build.");
      },
      "system-identify": () => ctx2.run("systems.identify", ctx2.sourceParams()),
      "system-chr-open": async () => {
        const result = await ctx2.run("systems.nes_chr", { ...ctx2.sourceParams(), first_tile: parseInteger(read("chr-first")), count: parseInteger(read("chr-count")) }, { render: false });
        if (!result.ok) throw new Error(result.error || "CHR page is unavailable.");
        state2.pending = null;
        state2.paint = null;
        delete state2.results["assets.inspect"];
        delete state2.results["assets.plan"];
        for (const key3 of Object.keys(state2.drafts)) if (key3.endsWith(":assets:asset-schema") || key3.endsWith(":assets:asset-changes")) delete state2.drafts[key3];
        await ctx2.navigate("assets");
      },
      "resource-region": (node) => ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset: Number(node.dataset.id), length: 256 }),
      "resource-read": async () => {
        const offset = parseInteger(read("hex-offset"));
        await ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset, length: 256 });
      },
      "hex-next": async () => {
        var _a2;
        const old = ((_a2 = state2.results["resource.inspect"]) == null ? void 0 : _a2.offset) || 0;
        state2.drafts[[state2.project.project_id, a.artifact_id, state2.page, "hex-offset"].join(":")] = String(Math.min(a.size - 1, old + 256));
        await ctx2.run("resource.inspect", { ...ctx2.sourceParams(), offset: Math.min(a.size - 1, old + 256), length: 256 });
      },
      "bytes-plan": async () => {
        const offset = parseInteger(read("edit-offset"));
        const before = read("edit-before").replace(/\s/g, "").toLowerCase(), after = read("edit-after").replace(/\s/g, "").toLowerCase();
        const result = await ctx2.run((assessment == null ? void 0 : assessment.system_id) ? "systems.plan_edits" : "bytes.plan", { ...ctx2.sourceParams(), edits: [{ offset, before, after }] }, { render: false });
        state2.results["bytes.plan"] = result;
        state2.pending = { kind: "bytes", plan_id: result.plan_id, artifact_id: a.artifact_id, project_id: state2.project.project_id };
        await ctx2.render();
      },
      "bytes-apply": async () => {
        if (!state2.pending || state2.pending.artifact_id !== a.artifact_id) throw new Error("Review a fresh plan for the selected source first.");
        const result = await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: state2.pending.plan_id }, { render: false });
        state2.pending = null;
        await ctx2.render();
        ctx2.notify("Separate build created; the source is unchanged.");
      },
      "bytes-discard": () => {
        state2.pending = null;
        delete state2.results["bytes.plan"];
        ctx2.render();
      }
    });
    if (!a) return `${heading("Workspace", "Resources", "")}${empty("Import a source", "Choose a cartridge image.", button("Import source", "import", { primary: true }))}`;
    const pending = ((_c = state2.pending) == null ? void 0 : _c.kind) === "bytes" && state2.pending.artifact_id === a.artifact_id;
    return `${heading("Resource investigator", "Resources", "Inspect the exact selected revision. Generic edits require explicit old bytes and preserve file size.", button("Import source", "import", { icon: "plus" }))}<div class="identity">${badge(a.kind, a.kind === "build" ? "good" : "neutral")}<strong>${esc(a.name)}</strong><span>${esc(a.system)} · ${size(a.size)}</span><code title="${a.sha256}">SHA-256 ${short(a.sha256)}…</code></div>${a.source_id ? `<section class="card"><h3>Continue editing this build</h3>${button("Reuse parent resource setup", "definitions-reuse")}<p class="subtle">Re-read declared offsets against this build.</p></section>` : ""}<div class="investigation-grid">${hexEditor(ctx2, data)}${byteNotes}</div>${comparison}${sourceSupport(ctx2)}${relationships}${scanControls(ctx2)}<details class="card"><summary>ROM health & revision</summary>${romHealthPanel(ctx2)}${revisionControls(ctx2)}${cheatControls(ctx2)}</details><details class="card"><summary>Find resources</summary>${discoveryControls(ctx2)}</details>${compressionControls(ctx2)}<details class="card"><summary>Declared resource catalog</summary>${catalogSection(ctx2, catalog)}</details><details class="card"><summary>System layout</summary>${systemSection(ctx2, assessment)}</details>${report(state2.results["bytes.plan"], "Proposed byte changes")}${report(state2.results["build.apply"], "Build result")}`;
  }
  function parseInteger(value) {
    const n = Number(value);
    if (!Number.isSafeInteger(n) || n < 0) throw new Error("Enter a nonnegative decimal or 0x hexadecimal offset.");
    return n;
  }
  function systemSection(ctx2, assessment) {
    var _a, _b;
    const chr = (_a = assessment == null ? void 0 : assessment.regions) == null ? void 0 : _a.find((r) => r.id === "chr-rom");
    return `<section class="card"><div class="card-heading"><h3>System investigation</h3>${badge((assessment == null ? void 0 : assessment.status) || "NOT INVESTIGATED", (assessment == null ? void 0 : assessment.status) === "IDENTIFIED" ? "good" : "warm")}</div><p class="subtle">Detected system: <strong>${esc((assessment == null ? void 0 : assessment.system_id) || "Unresolved")}</strong>. </p>${button("Identify selected source", "system-identify", { icon: "search" })}${((_b = assessment == null ? void 0 : assessment.regions) == null ? void 0 : _b.length) ? `<div class="table-wrap"><table><thead><tr><th>Region</th><th>Kind</th><th>Offset</th><th>Length</th><th></th></tr></thead><tbody>${assessment.regions.map((r) => `<tr><td>${esc(r.id)}</td><td>${esc(r.kind)}</td><td><code>0x${r.offset.toString(16)}</code></td><td>${size(r.length)}</td><td>${button("Inspect bytes", "resource-region", { id: String(r.offset) })}</td></tr>`).join("")}</tbody></table></div>` : ""}${chr ? `<div class="notice">${Math.floor(chr.length / 16)} CHR tiles. Opening a page clears the current pixel proposal.</div><div class="field-row">${field("chr-first", "First CHR tile", ctx2.draft("chr-first", "0"), { type: "number", min: 0 })}${field("chr-count", "Tiles on page", ctx2.draft("chr-count", Math.min(16, Math.floor(chr.length / 16))), { type: "number", min: 1 })}</div>${button("Open CHR page", "system-chr-open", { primary: true, icon: "assets" })}` : ""}${report(assessment, "System assessment details")}</section>`;
  }
  function catalogSection(ctx2, catalog) {
    return `<section class="card"><div class="card-heading"><h3>Resource catalog</h3><span>${catalog.total} entries</span></div><div class="toolbar">${field("catalog-query", "Find resources", ctx2.state.catalogQuery || "")}${button("Search resources", "catalog-search")}${button("Index declared resources", "catalog-index")}</div>${catalog.resources.length ? `<div class="table-wrap"><table><thead><tr><th>Resource</th><th>Kind</th><th>Offset</th><th>Bytes</th><th></th></tr></thead><tbody>${catalog.resources.map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.kind)}</td><td>0x${r.offset.toString(16)}</td><td>${size(r.length)}</td><td>${button("Inspect", "catalog-open", { id: String(r.offset), name: String(r.length) })}</td></tr>`).join("")}</tbody></table></div><div class="actions">${button("Previous resources", "catalog-page", { id: "-1", disabled: !catalog.page })}<span>Page ${catalog.page + 1}</span>${button("Next resources", "catalog-page", { id: "1", disabled: (catalog.page + 1) * catalog.limit >= catalog.total })}</div>` : '<p class="subtle">Index your declared text and graphics to browse them here.</p>'}</section>`;
  }
  function mount3(ctx2) {
    mountHexEditor(ctx2);
  }

  // romancer/ui/views/scripts.js
  var scripts_exports = {};
  __export(scripts_exports, {
    mount: () => mount4,
    render: () => render7
  });

  // romancer/ui/menu_preview.js
  var integer6 = (value, min, max, label) => {
    if (!Number.isSafeInteger(value) || value < min || value > max) throw Error("Invalid declared " + label + ".");
    return value;
  };
  function setup(ctx2) {
    var _a, _b, _c, _d;
    const schemaFallback = JSON.stringify(((_b = (_a = ctx2.state.artifact) == null ? void 0 : _a.descriptors) == null ? void 0 : _b.script) || ((_d = (_c = ctx2.state.project) == null ? void 0 : _c.descriptors) == null ? void 0 : _d.script) || {}), menuFallback = JSON.stringify({ profile: {}, cases: {}, font_artifact_id: "", font_schema: {} }), read2 = (id) => {
      var _a2;
      return ((_a2 = document.getElementById(id)) == null ? void 0 : _a2.value) ?? ctx2.draft(id, id === "script-schema" ? schemaFallback : menuFallback);
    };
    const schema = read2("script-schema"), config = read2("menu-config");
    if (schema.length > 1024 ** 2 || config.length > 1024 ** 2) throw Error("Menu declaration exceeds its preview budget.");
    return { schema: JSON.parse(schema), config: JSON.parse(config) };
  }
  function names2(ctx2, doc) {
    return doc.records.map((record, index) => ({ record, texts: record.segments.map((segment) => {
      var _a;
      return ((_a = document.getElementById(`script-segment-${index}-${segment.index}`)) == null ? void 0 : _a.value) ?? ctx2.draft(`script-segment-${index}-${segment.index}`, segment.text);
    }) }));
  }
  var textSignature = (ctx2, doc) => JSON.stringify(names2(ctx2, doc).map((row) => [row.record.id, row.texts]));
  function current(ctx2, owned) {
    var _a;
    const { state: state2 } = ctx2, doc = state2.results["script.inspect"];
    if (!owned || state2.menuVisual !== owned || owned.scope !== selectionKey(state2) || owned.document_id !== (doc == null ? void 0 : doc.document_id) || doc.source_sha256 !== ((_a = state2.artifact) == null ? void 0 : _a.sha256) || state2.page && state2.page !== "scripts") return false;
    try {
      return JSON.stringify(setup(ctx2)) === owned.signature;
    } catch {
      return false;
    }
  }
  function fontData(metrics) {
    var _a, _b;
    if (!Array.isArray(metrics.glyphs) || !metrics.glyphs.length || metrics.glyphs.length > 256) throw Error("Measured font glyphs are unavailable.");
    const result = /* @__PURE__ */ new Map();
    let budget = 0;
    for (const glyph of metrics.glyphs) {
      const bitmap = glyph.bitmap || {}, width = integer6(bitmap.width, 1, 32, "glyph width"), height = integer6(bitmap.height, 1, 32, "glyph height"), stride = integer6(bitmap.row_stride, 1, 4, "glyph row stride");
      if (stride !== Math.ceil(width / 8) || typeof bitmap.raw_hex !== "string" || bitmap.raw_hex.length !== stride * height * 2 || !/^[a-f0-9]+$/i.test(bitmap.raw_hex) || result.has(glyph.id)) throw Error("Measured glyph bitmap data is unavailable or ambiguous.");
      const raw = Uint8Array.from(bitmap.raw_hex.match(/../g), (value) => parseInt(value, 16)), mask = (1 << (8 - width % 8) % 8) - 1;
      for (let y = 0; y < height; y++) if (raw[(y + 1) * stride - 1] & mask) throw Error("Measured glyph has unsupported padding bits.");
      integer6((_a = glyph.bearing) == null ? void 0 : _a.x, -64, 64, "glyph bearing");
      integer6((_b = glyph.bearing) == null ? void 0 : _b.y, -64, 64, "glyph bearing");
      integer6(glyph.advance_pixels, 0, 128, "glyph advance");
      budget += raw.length;
      if (budget > 65536) throw Error("Measured font bitmap budget exceeded.");
      result.set(glyph.id, { ...glyph, width, height, stride, raw });
    }
    return result;
  }
  function mappingFor(preview, font) {
    if (!Array.isArray(preview.glyph_map) || preview.glyph_map.length > 256) throw Error("Declared menu glyph mapping is unavailable.");
    const result = /* @__PURE__ */ new Map();
    for (const row of preview.glyph_map) {
      if (typeof row.scalar !== "string" || Array.from(row.scalar).length !== 1 || result.has(row.scalar) || !font.has(row.glyph_id)) throw Error("Declared menu mapping names an unavailable glyph.");
      result.set(row.scalar, row.glyph_id);
    }
    return result;
  }
  function validate(preview, metrics, doc, config) {
    var _a, _b, _c, _d, _e, _f;
    if (preview.error) throw Error(preview.error.message || preview.error);
    if (!metrics.ok || metrics.status !== "MEASURED") throw Error(((_a = metrics.error) == null ? void 0 : _a.message) || "Declared font measurements are unavailable.");
    if (((_b = config.font_schema) == null ? void 0 : _b.codec) !== "mono-row-msb-v1") throw Error("This font storage format has no declared bitmap preview.");
    if (preview.source_sha256 !== doc.source_sha256 || preview.document_id !== doc.document_id || preview.schema_sha256 !== doc.schema_sha256 || ((_c = preview.script) == null ? void 0 : _c.document_id) !== doc.document_id) throw Error("Menu layout belongs to different source text.");
    if (preview.font_sha256 !== metrics.source_sha256 || metrics.source_sha256 !== ((_d = config.font_schema.source) == null ? void 0 : _d.sha256) || preview.font_schema_sha256 !== metrics.font_schema_sha256 || preview.metrics_id !== metrics.metrics_id) throw Error("Menu placements and font measurements have different identities.");
    const viewport = (_e = preview.profile) == null ? void 0 : _e.viewport, width = integer6(viewport == null ? void 0 : viewport.width, 1, 1024, "viewport width"), height = integer6(viewport == null ? void 0 : viewport.height, 1, 1024, "viewport height");
    integer6(preview.profile.line_height_px, 1, 64, "line height");
    if (!Array.isArray(preview.cases) || !preview.cases.length || preview.cases.length > 32 || width * height * preview.cases.length > 8 * 1024 ** 2) throw Error("Declared cases exceed the menu canvas budget.");
    let cells = 0, placements = 0;
    for (const row of preview.cases) {
      if (!Array.isArray(row.cells)) throw Error("Declared menu case cells are unavailable.");
      cells += row.cells.length;
      for (const cell of row.cells) placements += ((_f = cell.placements) == null ? void 0 : _f.length) || 0;
    }
    if (cells > 1024 || placements > 2048) throw Error("Declared menu placement budget exceeded.");
    const font = fontData(metrics);
    return { font, mapping: mappingFor(preview, font), width, height };
  }
  async function loadMenuPreview(ctx2, doc) {
    var _a;
    if (!(doc == null ? void 0 : doc.ok) || ((_a = ctx2.state.results["script.inspect"]) == null ? void 0 : _a.document_id) !== doc.document_id) throw Error("Inspect declared source text before previewing its menu.");
    const selected2 = setup(ctx2), { config, schema } = selected2, { state: state2 } = ctx2, generation = (state2.menuPreviewGeneration || 0) + 1;
    state2.menuPreviewGeneration = generation;
    const owned = { scope: selectionKey(state2), document_id: doc.document_id, signature: JSON.stringify(selected2), text_signature: textSignature(ctx2, doc), generation, status: "loading" };
    state2.menuVisual = owned;
    delete state2.results["menu.preview"];
    await ctx2.render();
    const requestCurrent = () => current(ctx2, owned) && owned.text_signature === textSignature(ctx2, doc) && state2.menuPreviewGeneration === generation;
    try {
      if (!requestCurrent()) return;
      const [preview, metrics] = await Promise.all([
        ctx2.api.call("menu.preview", { ...ctx2.sourceParams(), schema, profile: config.profile, cases: config.cases, font_artifact_id: config.font_artifact_id, font_schema: config.font_schema }),
        ctx2.api.call("font.measure", { project_id: state2.project.project_id, artifact_id: config.font_artifact_id, schema: config.font_schema })
      ]);
      if (!requestCurrent()) {
        if (state2.menuVisual === owned) state2.menuVisual = null;
        return;
      }
      const prepared = validate(preview, metrics, doc, config);
      Object.assign(owned, { status: "ready", preview, metrics, prepared });
      state2.results["menu.preview"] = preview;
    } catch (error) {
      if (!requestCurrent()) return;
      Object.assign(owned, { status: "error", message: error.message });
    }
    if (current(ctx2, owned)) await ctx2.render();
  }
  function placementsFor(cell, edited, drafts, prepared) {
    var _a, _b, _c;
    if (!Array.isArray(cell.placements)) throw Error(((_b = (_a = cell.diagnostics) == null ? void 0 : _a[0]) == null ? void 0 : _b.message) || "Declared cell glyph placements are unavailable.");
    if (!edited || cell.kind !== "name") return { placements: cell.placements, advance: cell.advance_px };
    const row = drafts.get(cell.record_id), record = row == null ? void 0 : row.record;
    if (!record || ((_c = record.read_only_reasons) == null ? void 0 : _c.length) || record.segments.length !== 1 || record.tokens.some((token2) => !["text", "terminator", "padding"].includes(token2.kind))) throw Error("Name preview requires one complete control-free text segment.");
    const text = row.texts[0], scalars = Array.from(text);
    if (scalars.length > 128) throw Error("Name preview exceeds 128 display characters.");
    if (text === cell.text) return { placements: cell.placements, advance: cell.advance_px };
    const run2 = scalars.map((scalar) => {
      const id = prepared.mapping.get(scalar), glyph = prepared.font.get(id);
      if (!glyph) throw Error("No declared glyph for " + JSON.stringify(scalar) + ".");
      return glyph;
    });
    const advance = run2.reduce((sum, glyph) => sum + glyph.advance_pixels, 0), bounds2 = cell.box_bounds;
    let x = cell.align === "right" ? bounds2[2] - advance : bounds2[0];
    return { advance, placements: run2.map((glyph) => {
      const value = { glyph_id: glyph.id, x, y: bounds2[1] };
      x += glyph.advance_pixels;
      return value;
    }) };
  }
  function rasterCase(owned, row, drafts, edited) {
    const { width, height, font } = owned.prepared, pixels = new Uint8ClampedArray(width * height * 4), warnings = /* @__PURE__ */ new Set();
    for (let i = 0; i < pixels.length; i += 4) pixels.set([16, 33, 39, 255], i);
    for (const cell of row.cells) {
      const bounds2 = cell.box_bounds;
      if (!Array.isArray(bounds2) || bounds2.length !== 4) throw Error("Declared cell bounds are unavailable.");
      for (const value of bounds2) integer6(value, -131072, 131072, "cell bounds");
      const { placements, advance } = placementsFor(cell, edited, drafts, owned.prepared);
      if (Number.isSafeInteger(advance) && advance > bounds2[2] - bounds2[0]) warnings.add("Text advance exceeds a declared box.");
      if (owned.preview.profile.line_height_px > bounds2[3] - bounds2[1]) warnings.add("Declared line height exceeds its box.");
      for (const placement of placements) {
        const glyph = font.get(placement.glyph_id);
        if (!glyph) throw Error("A placed glyph is missing from the measured font.");
        const left = integer6(placement.x, -131072, 131072, "glyph position") + glyph.bearing.x, top = integer6(placement.y, -131072, 131072, "glyph position") + glyph.bearing.y;
        for (let y = 0; y < glyph.height; y++) for (let x = 0; x < glyph.width; x++) if (glyph.raw[y * glyph.stride + (x >> 3)] & 128 >> x % 8) {
          const px = left + x, py = top + y;
          if (px < bounds2[0] || px >= bounds2[2] || py < bounds2[1] || py >= bounds2[3]) warnings.add("Glyph ink exceeds a declared box.");
          if (px < 0 || py < 0 || px >= width || py >= height) {
            warnings.add("Glyph ink exceeds the declared viewport.");
            continue;
          }
          pixels.set([230, 241, 235, 255], (py * width + px) * 4);
        }
      }
    }
    return { width, height, pixels, warnings: [...warnings] };
  }
  function menuPreviewReport(ctx2) {
    const owned = ctx2.state.menuVisual;
    return current(ctx2, owned) && owned.status === "ready" ? owned.preview : null;
  }
  function menuPreviewPanel(ctx2) {
    const owned = ctx2.state.menuVisual;
    if (!current(ctx2, owned)) return "";
    if (owned.status === "loading") return '<section class="card"><p class="preview-caption" role="status">Measuring declared menu glyphs and layout…</p></section>';
    if (owned.status === "error") return `<section class="card"><p class="error" role="status">Menu preview unavailable: ${esc(owned.message)}</p></section>`;
    const { width, height } = owned.prepared, canvas = (kind, i) => `<canvas id="menu-${kind}-${i}" width="${width}" height="${height}" aria-label="${kind === "original" ? "Original" : "Editing"} declared menu case ${i + 1}" style="display:block;width:${Math.min(768, width * 3)}px;max-width:100%;height:auto;image-rendering:pixelated"></canvas>`;
    return `<section class="card" id="menu-visual-preview"><h3>Declared font &amp; layout preview</h3><p class="preview-caption">Monochrome declared glyphs and boxes; not a captured game scene. Native font use and rendering remain unverified.</p><p>Edit a name above to update its declared menu cases. Control codes stay preserved.</p>${owned.preview.cases.map((row, i) => `<section><h4>Case ${esc(row.id)}${row.selected_entry == null ? "" : " · selected " + esc(row.selected_entry)}</h4><div class="preview-pair"><div><span>Original</span>${canvas("original", i)}</div><div><span>Editing</span>${canvas("edited", i)}</div></div><p id="menu-case-status-${i}" class="preview-caption" role="status" aria-live="polite"></p></section>`).join("")}</section>`;
  }
  function mountMenuPreview(ctx2, doc) {
    var _a;
    const owned = ctx2.state.menuVisual, root = document.getElementById("menu-visual-preview");
    if (!root || !current(ctx2, owned) || owned.status !== "ready") return;
    const draw2 = () => {
      if (!current(ctx2, owned)) {
        root.innerHTML = '<p class="error" role="status">Menu preview unavailable: source or declarations changed. Preview menu again.</p>';
        return;
      }
      const drafts = new Map(names2(ctx2, doc).map((row) => [row.record.id, row]));
      for (const [i, row] of owned.preview.cases.entries()) {
        let before = null, after = null;
        const errors = [];
        for (const [kind, edited] of [["original", false], ["edited", true]]) {
          const canvas = document.getElementById(`menu-${kind}-${i}`);
          if (!canvas) continue;
          try {
            const image = rasterCase(owned, row, drafts, edited), c = canvas.getContext("2d"), data = c.createImageData(image.width, image.height);
            canvas.width = image.width;
            canvas.height = image.height;
            data.data.set(image.pixels);
            c.putImageData(data, 0, 0);
            canvas.hidden = false;
            if (edited) after = image;
            else before = image;
          } catch (error) {
            canvas.hidden = true;
            canvas.width = 1;
            canvas.height = 1;
            errors.push((edited ? "Editing" : "Original") + " preview unavailable: " + error.message);
          }
        }
        const status = document.getElementById("menu-case-status-" + i);
        if (status) {
          let changed2 = 0;
          if (before && after) {
            for (let n = 0; n < before.pixels.length; n += 4) if ([0, 1, 2].some((c) => before.pixels[n + c] !== after.pixels[n + c])) changed2++;
          }
          status.textContent = errors.length ? errors.join(" ") : (changed2 ? "Preview updated · " + changed2 + " declared pixels differ · not built." : "Unchanged declared menu preview.") + " " + [.../* @__PURE__ */ new Set([...(before == null ? void 0 : before.warnings) || [], ...(after == null ? void 0 : after.warnings) || []])].join(" ");
          status.className = errors.length ? "error" : "preview-caption";
        }
      }
    };
    for (const [index, record] of doc.records.entries()) for (const segment of record.segments) {
      const node = document.getElementById(`script-segment-${index}-${segment.index}`);
      node == null ? void 0 : node.addEventListener("input", draw2);
      node == null ? void 0 : node.addEventListener("change", draw2);
    }
    for (const id of ["menu-config", "script-schema"]) (_a = document.getElementById(id)) == null ? void 0 : _a.addEventListener("input", () => {
      if (!current(ctx2, owned)) {
        draw2();
        if (ctx2.state.menuVisual === owned) ctx2.state.menuVisual = null;
      }
    });
    draw2();
  }

  // romancer/ui/translation_controls.js
  function translationPreview(state2, model) {
    const saved = state2.translationSheet;
    return (saved == null ? void 0 : saved.scope) === selectionKey(state2) && saved.preview.document_id === (model == null ? void 0 : model.document_id) && saved.preview.schema_sha256 === (model == null ? void 0 : model.schema_sha256) ? saved.preview : null;
  }
  function translationControls(ctx2, model) {
    const { state: state2 } = ctx2, ticket = selectionKey(state2), preview = translationPreview(state2, model), enabled = (model == null ? void 0 : model.ok) && model.write_supported;
    const schema = () => json("script-schema"), current2 = () => selectionKey(state2) === ticket;
    ctx2.use({
      "translation-export": async () => {
        const format = read("translation-format"), params = ctx2.sourceParams(), result = await ctx2.run("translation.export", { ...params, schema: schema(), format }, { render: false });
        if (current2()) await ctx2.api.download(params.project_id, result.export.export_id, "translation." + format);
      },
      "translation-preview": async () => {
        const file = document.getElementById("translation-file").files[0];
        if (!file) throw Error("Choose the edited CSV or TSV sheet.");
        const selectedSchema = schema(), signature = JSON.stringify(selectedSchema), format = read("translation-format"), params = ctx2.sourceParams(), request2 = (state2.translationRequest || 0) + 1;
        state2.translationRequest = request2;
        const input = await ctx2.api.uploadInput(params.project_id, file, "translation");
        if (!current2() || state2.translationRequest !== request2) throw Error("Selection changed. Preview this sheet again.");
        const result = await ctx2.run("translation.preview", { ...params, schema: selectedSchema, input_id: input.input_id, format }, { render: false });
        if (!current2() || state2.translationRequest !== request2 || JSON.stringify(schema()) !== signature) throw Error("Source, file or text setup changed. Preview again.");
        state2.translationSheet = { scope: ticket, preview: result, schema: selectedSchema };
        await ctx2.render();
      },
      "translation-review": async () => {
        const saved = state2.translationSheet, result = translationPreview(state2, model);
        if (!(result == null ? void 0 : result.valid) || !result.changed_segments) throw Error("Preview a valid sheet with changes first.");
        if (JSON.stringify(schema()) !== JSON.stringify(saved.schema)) throw Error("Text setup changed. Preview the sheet again.");
        const request2 = state2.translationRequest, plan = await ctx2.run("script.plan", { ...ctx2.sourceParams(), schema: saved.schema, edits: result.edits }, { render: false });
        if (!current2() || request2 !== state2.translationRequest) return;
        saved.plan = plan;
        await ctx2.render();
      },
      "translation-apply": async () => {
        const saved = state2.translationSheet, result = translationPreview(state2, model);
        if (!(saved == null ? void 0 : saved.plan) || !(result == null ? void 0 : result.valid) || JSON.stringify(schema()) !== JSON.stringify(saved.schema)) throw Error("Review a fresh translation plan first.");
        const built = await ctx2.run("structured.apply", { ...ctx2.projectParams(), plan_id: saved.plan.workbench_plan_id }, { render: false });
        if (!current2()) return;
        state2.translationSheet = null;
        await ctx2.refreshProject();
        await ctx2.setArtifact(built.artifact_id);
        ctx2.notify("Translated build created. Original controls and source preserved.");
        await ctx2.navigate("overview");
      }
    });
    return `<details class="card" id="translation-tools"><summary>Translation spreadsheet</summary><p>Export, edit only the translation column, then import to check every change.</p>${select("translation-format", "Sheet format", [["csv", "CSV"], ["tsv", "TSV"]], ctx2.draft("translation-format", "csv"))}${button("Download text sheet", "translation-export", { disabled: !enabled })}${fileInput("translation-file", "Edited sheet", ".csv,.tsv")}${button("Check imported translations", "translation-preview", { disabled: !enabled })}
 ${!enabled ? "<p>Declare and inspect editable text first.</p>" : ""}${preview ? `<div class="notice">${badge(preview.status.replaceAll("_", " ").toLowerCase(), preview.valid ? "good" : "warm")} · ${preview.changed_segments} changed segments</div>
 ${preview.issues.map((r) => `<p class="error">${esc(r.record_id || "Sheet")}: ${esc(r.message)}</p>`).join("")}
 <div class="table-wrap"><table><thead><tr><th>Record</th><th>Original</th><th>Translation</th><th>Bytes / capacity</th></tr></thead><tbody>${preview.previews.map((r) => `<tr><td>${esc(r.record_id)}</td><td>${r.before.map(esc).join(" | ")}</td><td>${r.after.map(esc).join(" | ")}${r.text_truncated ? "…" : ""}</td><td>${r.used_bytes} / ${r.capacity}</td></tr>`).join("")}</tbody></table></div>
 <div class="actions">${button("Review translation plan", "translation-review", { disabled: !preview.valid || !preview.changed_segments, primary: true })}${button("Create translated build", "translation-apply", { disabled: !state2.translationSheet.plan })}</div>${state2.translationSheet.plan ? "<p>Plan reviewed. Creating the build preserves the original file.</p>" : ""}` : ""}</details>`;
  }
  function mountTranslation(ctx2) {
    var _a;
    const root = document.getElementById("translation-tools");
    if (!root) return;
    for (const id of ["translation-file", "translation-format", "script-schema"]) (_a = document.getElementById(id)) == null ? void 0 : _a.addEventListener("change", () => {
      ctx2.state.translationRequest = (ctx2.state.translationRequest || 0) + 1;
      ctx2.state.translationSheet = null;
      root.querySelectorAll('[data-action="translation-apply"],[data-action="translation-review"]').forEach((n) => n.disabled = true);
    });
  }

  // romancer/ui/declarations.js
  var systems3 = [["nes", "NES"], ["snes", "SNES"], ["genesis", "Genesis"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]];
  var integer7 = (id) => {
    const text = read(id).trim(), value = Number(text);
    if (!text || !Number.isSafeInteger(value)) throw new Error("Enter a whole number for " + id + ".");
    return value;
  };
  var optional = (id) => read(id).trim() ? integer7(id) : null;
  function system(ctx2, prefix) {
    return select(prefix + "-system", "System", systems3, ctx2.draft(prefix + "-system", resourceSystem(ctx2.state)));
  }
  function number(ctx2, id, title, value) {
    return field(id, title, ctx2.draft(id, value));
  }
  async function declared(ctx2, kind, config) {
    const result = await ctx2.run("resources.declare_" + kind, { ...ctx2.sourceParams(), config }, { render: false });
    ctx2.state.candidateReview = null;
    ctx2.state.openDeclaration = null;
    ctx2.state.results[kind + ".inspect"] = result.inspection;
    ctx2.setDraft(kind === "script" ? "script-schema" : "asset-schema", JSON.stringify(result.schema, null, 2));
    if (kind === "assets") {
      ctx2.state.paint = null;
      ctx2.setDraft("paint-buffer", "");
      ctx2.setDraft("asset-changes", "[]");
    }
    await ctx2.render();
  }
  function textDeclaration(ctx2) {
    prefill(ctx2, "text");
    ctx2.use({ "declare-text": () => {
      const controls = read("text-controls").split("\n").filter((s) => s.trim()).map((line) => {
        const [id, opcode, args, role] = line.split(",").map((s) => s.trim());
        return { id, opcode: parseInt(opcode, 16), argument_length: Number(args), position_independent: true, layout_role: role };
      });
      return declared(ctx2, "script", { system_id: read("text-system"), offset: integer7("text-offset"), capacity: integer7("text-capacity"), count: integer7("text-count"), stride: integer7("text-stride"), pointer_offset: optional("text-pointer"), pointer_width: integer7("text-pointer-width"), pointer_endian: read("text-endian"), pointer_base: integer7("text-base"), terminator: integer7("text-terminator"), padding: integer7("text-padding"), encoding: read("text-encoding"), table: read("text-table"), controls });
    } });
    return `<details class="config" ${ctx2.state.openDeclaration === "text" ? "open" : ""}><summary>Declare text slots</summary>${system(ctx2, "text")}<div class="field-row">${number(ctx2, "text-offset", "First text offset", "0")}${number(ctx2, "text-capacity", "Bytes per slot", "64")}${number(ctx2, "text-count", "Slot count", "1")}${number(ctx2, "text-stride", "Slot stride", "64")}${number(ctx2, "text-pointer", "Pointer table offset (optional)", "")}${number(ctx2, "text-pointer-width", "Pointer bytes", "2")}${number(ctx2, "text-base", "Pointer base", "0")}${select("text-endian", "Pointer byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("text-endian", "little"))}${number(ctx2, "text-terminator", "Terminator byte", "0")}${number(ctx2, "text-padding", "Padding byte", "255")}</div>${select("text-encoding", "Encoding", [["ascii", "ASCII"], ["table", "Custom single-byte table"]], ctx2.draft("text-encoding", "ascii"))}${area("text-table", "Custom table (HH=character)", ctx2.draft("text-table", ""), 3)}${area("text-controls", "Controls (name, hex opcode, argument bytes, line/page/pause/opaque)", ctx2.draft("text-controls", ""), 2)}${button("Load text declaration", "declare-text")}</details>`;
  }
  function graphicsDeclaration(ctx2) {
    prefill(ctx2, "gfx");
    ctx2.use({ "declare-graphics": () => {
      const config = { system_id: read("gfx-system"), offset: integer7("gfx-offset"), count: integer7("gfx-count"), codec: read("gfx-codec"), width: integer7("gfx-width"), height: integer7("gfx-height"), palette_offset: optional("gfx-palette"), palette_banks: integer7("gfx-banks"), palette_format: read("gfx-palette-format"), map_offset: optional("gfx-map"), map_width: integer7("gfx-map-width"), map_height: integer7("gfx-map-height"), font_chars: read("gfx-chars"), advance_offset: optional("gfx-advance"), advance_pixels: integer7("gfx-advance-pixels") };
      return declared(ctx2, "assets", config);
    } });
    return `<details class="config" ${ctx2.state.openDeclaration === "gfx" ? "open" : ""}><summary>Declare graphics or font</summary>${system(ctx2, "gfx")}${select("gfx-codec", "Storage layout", [["", "System tile template"], ["mono-row-msb-v1", "Mono font rows"], ["tile8-planar2-msb-v1", "NES 2bpp separate planes"], ["tile8-paired2-msb-v1", "Game Boy 2bpp paired planes"], ["tile8-paired4-msb-v1", "4bpp paired planes"], ["tile8-packed4-high-v1", "4bpp high nibble first"], ["tile8-packed4-low-v1", "4bpp low nibble first"]], ctx2.draft("gfx-codec", ""))}<div class="field-row">${number(ctx2, "gfx-offset", "Bitmap offset", "0")}${number(ctx2, "gfx-count", "Tile or glyph count", "1")}${number(ctx2, "gfx-width", "Cell width", "8")}${number(ctx2, "gfx-height", "Cell height", "8")}${number(ctx2, "gfx-palette", "Palette offset (optional)", "")}${number(ctx2, "gfx-banks", "Palette banks", "1")}${select("gfx-palette-format", "Palette layout", [["rgb555-le", "RGB555 little endian"], ["rgb555-be", "RGB555 big endian"], ["genesis", "Genesis RGB333"]], ctx2.draft("gfx-palette-format", ctx2.state.artifact.system_id === "genesis" ? "genesis" : "rgb555-le"))}${number(ctx2, "gfx-map", "Tilemap offset (optional)", "")}${number(ctx2, "gfx-map-width", "Map columns", "1")}${number(ctx2, "gfx-map-height", "Map rows", "1")}</div>${field("gfx-chars", "Font characters in cell order (optional)", ctx2.draft("gfx-chars", ""))}<div class="field-row">${number(ctx2, "gfx-advance", "Stored advance table offset (optional)", "")}${number(ctx2, "gfx-advance-pixels", "Fixed advance in pixels", "8")}</div>${button("Load graphics declaration", "declare-graphics")}</details>`;
  }
  function layoutDeclaration(ctx2) {
    var _a;
    const rows = [...ctx2.state.project.sources, ...ctx2.state.project.builds].filter((r) => {
      var _a2;
      return (_a2 = r.descriptors) == null ? void 0 : _a2.font;
    });
    ctx2.use({ "configure-menu": async () => {
      const result = await ctx2.run("resources.menu_form", { ...ctx2.sourceParams(), font_artifact_id: read("layout-font"), width: integer7("layout-width"), height: integer7("layout-height"), line_height: integer7("layout-line-height") }, { render: false });
      ctx2.setDraft("menu-config", JSON.stringify({ font_artifact_id: result.font_artifact_id, font_schema: result.font_schema, profile: result.profile, cases: result.cases, request: {} }, null, 2));
      await ctx2.render();
    }, "configure-layout": async () => {
      const result = await ctx2.run("resources.layout_form", { ...ctx2.sourceParams(), font_artifact_id: read("layout-font"), width: integer7("layout-width"), height: integer7("layout-height"), line_height: integer7("layout-line-height") }, { render: false });
      ctx2.setDraft("layout-config", JSON.stringify({ font_artifact_id: result.font_artifact_id, font_schema: result.font_schema, policy: result.policy, request: result.request }, null, 2));
      await ctx2.render();
    } });
    return `<details class="config"><summary>Configure text layout</summary>${select("layout-font", "Declared font", rows.map((r) => [r.artifact_id, r.name]), ctx2.draft("layout-font", (_a = rows[0]) == null ? void 0 : _a.artifact_id))}<div class="field-row">${number(ctx2, "layout-width", "Box width in pixels", "240")}${number(ctx2, "layout-height", "Box height in pixels", "64")}${number(ctx2, "layout-line-height", "Line height", "8")}</div><div class="actions">${button("Use layout settings", "configure-layout", { disabled: !rows.length })}${button("Create menu preview setup", "configure-menu", { disabled: !rows.length })}</div></details>`;
  }
  function prefill(ctx2, prefix) {
    var _a;
    const candidate = ctx2.state.resourcePrefill;
    if (!candidate || candidate.artifact_id !== ((_a = ctx2.state.artifact) == null ? void 0 : _a.artifact_id) || candidate.prefix !== prefix) return;
    const map = prefix === "text" ? { system_id: "system", offset: "offset", capacity: "capacity", count: "count", stride: "stride", pointer_offset: "pointer", encoding: "encoding", terminator: "terminator", padding: "padding" } : { system_id: "system", offset: "offset", count: "count", codec: "codec" };
    ctx2.state.resourcePrefill = null;
    ctx2.state.openDeclaration = prefix;
    for (const [key3, suffix] of Object.entries(map)) if (key3 in candidate.config) ctx2.setDraft(prefix + "-" + suffix, candidate.config[key3] === null ? "" : String(candidate.config[key3]));
  }

  // romancer/ui/views/scripts.js
  async function render7(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    if (!state2.artifact) return empty("Import a resource", "Select a source with a declared fixed-slot script schema.");
    const fallback = ((_a = state2.candidateReview) == null ? void 0 : _a.artifact_id) === state2.artifact.artifact_id ? {} : ((_b = state2.artifact.descriptors) == null ? void 0 : _b.script) || ((_c = state2.project.descriptors) == null ? void 0 : _c.script) || {};
    const schemaText = ctx2.draft("script-schema", JSON.stringify(fallback, null, 2));
    let document2 = ((_d = state2.candidateReview) == null ? void 0 : _d.artifact_id) === state2.artifact.artifact_id ? null : state2.results["script.inspect"];
    if ((document2 == null ? void 0 : document2.source_sha256) !== state2.artifact.sha256) document2 = null;
    if (!document2 && ((_f = (_e = fallback.profile) == null ? void 0 : _e.accepted_sha256) == null ? void 0 : _f.includes(state2.artifact.sha256))) {
      document2 = await ctx2.api.call("script.inspect", { ...ctx2.sourceParams(), schema: fallback });
      state2.results["script.inspect"] = document2;
    }
    ctx2.use({
      "script-page": (node) => {
        state2.scriptPage = Math.max(0, (state2.scriptPage || 0) + Number(node.dataset.id));
        return ctx2.render();
      },
      "script-search": () => {
        state2.scriptPage = 0;
        state2.scriptFilter = read("script-search").toLowerCase();
        ctx2.render();
      },
      "script-replace": () => {
        const find = read("script-find"), replace = read("script-replace");
        if (!find) throw new Error("Enter text to find.");
        document2.records.forEach((row, i) => row.segments.forEach((segment) => {
          const id = `script-segment-${i}-${segment.index}`, node = window.document.getElementById(id), value = node ? node.value : ctx2.draft(id, segment.text);
          if (value.includes(find)) ctx2.setDraft(id, value.split(find).join(replace));
        }));
        state2.pending = null;
        ctx2.render();
      },
      "script-inspect": () => ctx2.run("script.inspect", { ...ctx2.sourceParams(), schema: json("script-schema") }),
      "script-plan": async () => {
        var _a2;
        if (!(document2 == null ? void 0 : document2.ok)) throw Error("Inspect the selected script schema first.");
        const collect = () => {
          const changes2 = [];
          document2.records.forEach((row, i) => row.segments.forEach((segment) => {
            const id = `script-segment-${i}-${segment.index}`, node = window.document.getElementById(id), value = node ? node.value : ctx2.draft(id, segment.text);
            if (value !== segment.text) changes2.push({ record_id: row.id, segment: segment.index, text: value });
          }));
          return changes2;
        };
        const changes = collect();
        if (!changes.length) throw Error("Change a text segment before reviewing.");
        const schema = json("script-schema"), signature = JSON.stringify({ schema, changes }), edits = { schema_version: 1, document_id: document2.document_id, source_sha256: document2.source_sha256, schema_sha256: document2.schema_sha256, changes };
        const result = await ctx2.run("script.plan", { ...ctx2.sourceParams(), schema, edits }, { render: false });
        if (((_a2 = state2.results["script.inspect"]) == null ? void 0 : _a2.document_id) !== document2.document_id || JSON.stringify({ schema: json("script-schema"), changes: collect() }) !== signature) {
          ctx2.notify("Text changed during review. Review it again.");
          return;
        }
        state2.pending = { kind: "script", plan_id: result.workbench_plan_id, artifact_id: state2.artifact.artifact_id, document_id: document2.document_id, signature };
        await ctx2.render();
      },
      "script-apply": async () => {
        var _a2, _b2;
        if (((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "script" || state2.pending.artifact_id !== state2.artifact.artifact_id || state2.pending.document_id !== (document2 == null ? void 0 : document2.document_id) || ((_b2 = state2.results["script.inspect"]) == null ? void 0 : _b2.document_id) !== (document2 == null ? void 0 : document2.document_id)) throw Error("Review the current text changes first.");
        const reviewed = state2.pending;
        await ctx2.run("structured.apply", { ...ctx2.projectParams(), plan_id: reviewed.plan_id }, { render: false });
        if (state2.pending !== reviewed) {
          ctx2.notify("Dialogue build created. Your newer text edits are still staged.");
          return;
        }
        state2.pending = null;
        await ctx2.render();
        ctx2.notify("Dialogue build created. Controls and original bytes were checked.");
      },
      "script-discard": () => {
        state2.pending = null;
        for (const key3 of Object.keys(state2.drafts)) if (key3.includes("script-segment-")) delete state2.drafts[key3];
        delete state2.results["script.plan"];
        ctx2.render();
      },
      "script-export": async () => {
        if (!(document2 == null ? void 0 : document2.ok)) throw new Error("Inspect a script before exporting it.");
        const result = await ctx2.run("docs.script_from_resource", { ...ctx2.sourceParams(), schema: json("script-schema"), format: "html" });
        await ctx2.api.download(state2.project.project_id, result.export.export_id, "script.html");
      },
      "font-measure": () => {
        const config = json("layout-config");
        return ctx2.run("font.measure", { ...ctx2.projectParams(), artifact_id: config.font_artifact_id, schema: config.font_schema });
      },
      "layout-check": () => {
        const config = json("layout-config");
        return ctx2.run("layout.check", { ...ctx2.sourceParams(), schema: json("script-schema"), font_artifact_id: config.font_artifact_id, font_schema: config.font_schema, policy: config.policy });
      },
      "layout-plan": () => {
        const config = json("layout-config");
        return ctx2.run("layout.plan", { ...ctx2.sourceParams(), schema: json("script-schema"), font_artifact_id: config.font_artifact_id, font_schema: config.font_schema, policy: config.policy, request: config.request });
      },
      "menu-inspect": () => {
        const config = json("menu-config");
        return ctx2.run("menu.inspect", { ...ctx2.sourceParams(), schema: json("script-schema"), profile: config.profile });
      },
      "menu-compare": () => {
        const config = json("menu-config");
        return ctx2.run("menu.compare", { ...ctx2.sourceParams(), schema: json("script-schema"), profile: config.profile, cases: config.cases, font_artifact_id: config.font_artifact_id, font_schema: config.font_schema, request: config.request });
      },
      "menu-preview": () => loadMenuPreview(ctx2, document2)
    });
    if (((_g = state2.candidateReview) == null ? void 0 : _g.artifact_id) === state2.artifact.artifact_id) return `${heading("", "Confirm text candidate", "")}<section class="card"><p>${esc(state2.candidateReview.reason)}</p><p>Confirm the format and allocation, then load the declaration.</p>${textDeclaration(ctx2)}${button("Cancel candidate", "candidate-cancel")}</section>`;
    const pending = ((_h = state2.pending) == null ? void 0 : _h.kind) === "script" && state2.pending.artifact_id === state2.artifact.artifact_id;
    return `${heading("Dialogue studio", "Text & layout", "Edit declared text segments while preserving control codes, pointers, and fixed allocations.", button("Export script", "script-export", { icon: "download", disabled: !(document2 == null ? void 0 : document2.ok) }))}<div class="identity"><strong>${esc(state2.artifact.name)}</strong><code>${short(state2.artifact.sha256)}</code>${badge((document2 == null ? void 0 : document2.write_supported) ? "EDITABLE FIXED SLOTS" : "SCHEMA REQUIRED", (document2 == null ? void 0 : document2.write_supported) ? "good" : "warm")}</div>${translationControls(ctx2, document2)}<div class="grid-two"><section class="card"><div class="card-heading"><h3>Text records</h3><span class="subtle">${((_i = document2 == null ? void 0 : document2.records) == null ? void 0 : _i.length) || 0} declared records</span></div>${field("script-search", "Search text", state2.scriptFilter || "")}${button("Search", "script-search")}<details class="config"><summary>Replace text</summary>${field("script-find", "Find", ctx2.draft("script-find", ""))}${field("script-replace", "Replace with", ctx2.draft("script-replace", ""))}${button("Stage replacements", "script-replace")}</details>${(document2 == null ? void 0 : document2.ok) ? document2.records.map((row, i) => ({ row, i })).filter(({ row }) => !state2.scriptFilter || row.segments.some((s) => s.text.toLowerCase().includes(state2.scriptFilter))).slice((state2.scriptPage || 0) * 20, (state2.scriptPage || 0) * 20 + 20).map(({ row, i }) => {
      var _a2, _b2;
      return `<article class="script-line"><div class="line-meta"><strong>${esc(((_a2 = row.annotations) == null ? void 0 : _a2.label) || row.id)}</strong><span>${row.used_bytes ?? "?"} / ${row.capacity} bytes · offset ${row.offset}</span></div><p class="preview-caption">System-font comparison · game font requires a declared layout or playtest</p>${row.segments.map((segment) => `<div class="preview-pair script-comparison"><div><span>Original segment ${segment.index + 1}</span><div class="text-window">${esc(segment.text)}</div></div><div>${area(`script-segment-${i}-${segment.index}`, "Edited segment " + (segment.index + 1), ctx2.draft(`script-segment-${i}-${segment.index}`, segment.text), 3)}</div></div>`).join("")}<div id="script-capacity-${i}">${capacitySummary(textCapacity(row, row.segments.map((segment) => ctx2.draft(`script-segment-${i}-${segment.index}`, segment.text)), document2.encoding_glyphs))}</div>${row.tokens.some((t) => t.kind === "control") ? `<div class="notice">Preserved controls: ${row.tokens.filter((t) => t.kind === "control").map((t) => esc(t.control_id)).join(", ")}</div>` : ""}${((_b2 = row.read_only_reasons) == null ? void 0 : _b2.map((r) => `<p class="error small">${esc(r)}</p>`).join("")) || ""}</article>`;
    }).join("") : empty("Load a revision-bound script schema", "Unknown encodings remain read only. The original demonstration includes an editable schema.")}<div class="actions">${button("Previous records", "script-page", { id: "-1", disabled: !(state2.scriptPage > 0) })}${button("Next records", "script-page", { id: "1", disabled: !document2 || ((state2.scriptPage || 0) + 1) * 20 >= document2.records.filter((row) => !state2.scriptFilter || row.segments.some((s) => s.text.toLowerCase().includes(state2.scriptFilter))).length })}</div><div class="actions">${button("Review text changes", "script-plan", { primary: !pending, icon: "arrow", disabled: !(document2 == null ? void 0 : document2.write_supported) })}${pending ? button("Create dialogue build", "script-apply", { primary: true, icon: "check" }) + button("Discard changes", "script-discard") : ""}</div></section><div>${menuPreviewPanel(ctx2)}<section class="card"><h3>Text setup</h3>${textDeclaration(ctx2)}${layoutDeclaration(ctx2)}${jsonEditor("script-schema", "Advanced script schema", schemaText, false)}${button("Inspect script", "script-inspect", { icon: "scripts" })}${jsonEditor("layout-config", "Advanced layout configuration", ctx2.draft("layout-config", JSON.stringify({ font_artifact_id: "", font_schema: {}, policy: {}, request: {} }, null, 2)))}<div class="actions">${button("Measure font", "font-measure")}${button("Check layout", "layout-check")}${button("Plan layout", "layout-plan")}</div>${jsonEditor("menu-config", "Menu display configuration", ctx2.draft("menu-config", JSON.stringify({ profile: {}, cases: {}, font_artifact_id: "", font_schema: {} }, null, 2)))}<div class="actions">${button("Inspect menu", "menu-inspect")}${button("Preview menu", "menu-preview")}${button("Compare native menu captures", "menu-compare")}</div></section></div></div>${report(state2.results["script.plan"], "Proposed dialogue changes")}${report(state2.results["structured.apply"], "Structured build")}${report(state2.results["font.measure"], "Measured font")}${report(state2.results["layout.check"], "Layout check")}${report(state2.results["layout.plan"], "Layout proposal")}${report(state2.results["menu.inspect"], "Declared menu")}${report(menuPreviewReport(ctx2), "Declared menu report")}${report(state2.results["menu.compare"], "Native menu comparison")}`;
  }
  function mount4(ctx2) {
    mountTranslation(ctx2);
    const doc = ctx2.state.results["script.inspect"];
    if (!(doc == null ? void 0 : doc.ok)) return;
    mountMenuPreview(ctx2, doc);
    const scope = selectionKey(ctx2.state);
    for (const [i, row] of doc.records.entries()) {
      const target = document.getElementById("script-capacity-" + i);
      if (!target) continue;
      const nodes = row.segments.map((segment) => document.getElementById(`script-segment-${i}-${segment.index}`));
      const draw2 = () => {
        var _a;
        if (selectionKey(ctx2.state) !== scope || ((_a = ctx2.state.results["script.inspect"]) == null ? void 0 : _a.document_id) !== doc.document_id) return;
        const values = nodes.map((node, j) => (node == null ? void 0 : node.value) ?? row.segments[j].text);
        target.innerHTML = '<p class="preview-caption" role="status">' + (values.some((text, j) => text !== row.segments[j].text) ? "Preview updated · text staged" : "Unchanged text preview") + "</p>" + capacitySummary(textCapacity(row, values, doc.encoding_glyphs));
      };
      for (const node of nodes) node == null ? void 0 : node.addEventListener("input", draw2);
      draw2();
    }
  }

  // romancer/ui/views/assets.js
  var assets_exports = {};
  __export(assets_exports, {
    literalColorCount: () => literalColorCount,
    literalRGB: () => literalRGB,
    mount: () => mount5,
    render: () => render8
  });

  // romancer/ui/palette_editor.js
  function paletteEditor(ctx2, palette2) {
    if (!palette2) return "";
    let after = palette2, error = "";
    try {
      after = editedPalette(palette2, JSON.parse(ctx2.draft("asset-changes", "[]")));
    } catch (e) {
      error = e.message;
    }
    let index = Number(ctx2.draft("palette-index", "1"));
    if (!Number.isInteger(index) || index < 0 || index >= palette2.entries.length) index = 0;
    const entry = after.entries[index];
    return `<section class="card"><h3>Palette colors</h3><div id="palette-comparison">${paletteComparison(palette2, after)}</div><div class="palette-picker-row">${select("palette-index", "Palette entry", palette2.entries.map((e, i) => [i, "Bank " + e.bank + " · color " + e.index]), index)}<label class="field"><span>Choose color · entry ${index}</span><input id="palette-picker" type="color" value="${rgbHex(entry.rgb)}" aria-label="Choose palette color"></label></div><p id="palette-preview-status" class="${error ? "error" : "preview-caption"}" role="status" aria-live="polite">${esc(error || "Color picker changes are staged. Review and build to save them.")}</p><details><summary>Color storage values</summary><div class="field-row">${["r", "g", "b"].map((c, i) => field("palette-" + c, ["Red", "Green", "Blue"][i] + " (0–" + channelMaximum(palette2.channels[c]) + ")", ctx2.draft("palette-" + c, entry.components[c]), { type: "number", min: 0 })).join("")}</div>${button("Stage storage values", "asset-palette-change")}</details></section>`;
  }
  function mountPaletteEditor(ctx2, doc, palette2, redraw) {
    const picker = document.getElementById("palette-picker");
    if (!picker || !palette2) return;
    const selector = document.getElementById("palette-index"), selectedIndex = Number(selector == null ? void 0 : selector.value);
    const scope = selectionKey(ctx2.state), current2 = () => {
      var _a;
      return scope === selectionKey(ctx2.state) && ((_a = ctx2.state.results["assets.inspect"]) == null ? void 0 : _a.document_id) === doc.document_id && document.getElementById("palette-picker") === picker;
    };
    const stage3 = () => {
      if (!current2()) return;
      try {
        const index = Number(selector == null ? void 0 : selector.value), entry = palette2.entries[index];
        if (!Number.isInteger(index) || !entry || index !== selectedIndex) throw Error("Reload the selected palette entry before editing its color.");
        const components = quantizeColor(picker.value, palette2.channels), changes = JSON.parse(ctx2.draft("asset-changes", "[]"));
        editedPalette(palette2, changes);
        const next = changes.filter((c) => !(c.kind === "palette" && c.palette_id === palette2.id && c.index === entry.index && c.bank === entry.bank));
        if (["r", "g", "b"].some((c) => components[c] !== entry.components[c])) next.push({ kind: "palette", palette_id: palette2.id, index: entry.index, bank: entry.bank, before: { ...entry.components }, after: components });
        const after = editedPalette(palette2, next), encoded = JSON.stringify(next, null, 2);
        ctx2.setDraft("asset-changes", encoded);
        const raw = document.getElementById("asset-changes");
        if (raw) raw.value = encoded;
        for (const c of ["r", "g", "b"]) {
          ctx2.setDraft("palette-" + c, String(components[c]));
          const field2 = document.getElementById("palette-" + c);
          if (field2) field2.value = String(components[c]);
        }
        ctx2.state.pending = null;
        ctx2.state.assetAcknowledgements = [];
        ctx2.state.assetEditRevision = (ctx2.state.assetEditRevision || 0) + 1;
        const comparison = document.getElementById("palette-comparison");
        if (comparison) comparison.innerHTML = paletteComparison(palette2, after);
        redraw();
        const status = document.getElementById("palette-preview-status");
        if (status) status.textContent = "Preview updated · color staged. Review and build to save it.";
        return true;
      } catch (error) {
        const status = document.getElementById("palette-preview-status");
        if (status) status.textContent = "Preview unavailable: " + error.message;
        return false;
      }
    };
    picker.addEventListener("input", stage3);
    picker.addEventListener("change", () => {
      if (stage3() && current2()) ctx2.notify("Palette preview updated. Changes are staged.");
    });
    selector == null ? void 0 : selector.addEventListener("change", async () => {
      if (!current2()) return;
      try {
        const entry = editedPalette(palette2, JSON.parse(ctx2.draft("asset-changes", "[]"))).entries[Number(selector.value)];
        if (!entry) return;
        ctx2.setDraft("palette-index", selector.value);
        for (const c of ["r", "g", "b"]) ctx2.setDraft("palette-" + c, String(entry.components[c]));
        await ctx2.render();
      } catch (error) {
        const status = document.getElementById("palette-preview-status");
        if (status) status.textContent = "Preview unavailable: " + error.message;
      }
    });
  }

  // romancer/ui/pixel_history.js
  var PixelHistory = class {
    constructor(scope, pixels, limit = 64) {
      this.scope = scope;
      this.current = [...pixels];
      this.limit = limit;
      this.past = [];
      this.future = [];
      this.start = null;
    }
    get canUndo() {
      return this.past.length > 0;
    }
    get canRedo() {
      return this.future.length > 0;
    }
    begin(pixels) {
      if (JSON.stringify(pixels) !== JSON.stringify(this.current)) {
        this.past = [];
        this.future = [];
        this.current = [...pixels];
      }
      this.start = [...pixels];
    }
    commit(pixels) {
      const before = this.start || this.current;
      this.start = null;
      if (JSON.stringify(before) === JSON.stringify(pixels)) return;
      this.past.push([...before]);
      if (this.past.length > this.limit) this.past.shift();
      this.current = [...pixels];
      this.future = [];
    }
    undo() {
      if (this.canUndo) {
        this.future.push([...this.current]);
        this.current = this.past.pop();
      }
      return [...this.current];
    }
    redo() {
      if (this.canRedo) {
        this.past.push([...this.current]);
        this.current = this.future.pop();
      }
      return [...this.current];
    }
  };
  function historyFor(ctx2, doc, bitmap, index, pixels) {
    const scope = selectionKey(ctx2.state) + ":" + doc.document_id;
    if (ctx2.state.pixelHistoryScope !== scope || !(ctx2.state.pixelHistories instanceof Map)) {
      ctx2.state.pixelHistories = /* @__PURE__ */ new Map();
      ctx2.state.pixelHistoryScope = scope;
    }
    const key3 = bitmap + ":" + index;
    let history3 = ctx2.state.pixelHistories.get(key3);
    if (!history3) history3 = new PixelHistory(scope + ":" + key3, pixels);
    ctx2.state.pixelHistories.delete(key3);
    ctx2.state.pixelHistories.set(key3, history3);
    while (ctx2.state.pixelHistories.size > 32) ctx2.state.pixelHistories.delete(ctx2.state.pixelHistories.keys().next().value);
    return history3;
  }
  function recordPixels(ctx2, doc, bitmap, index, before, after) {
    const history3 = historyFor(ctx2, doc, bitmap, index, before);
    history3.begin(before);
    history3.commit(after);
    return history3;
  }
  function pixelBuffer(ctx2, doc, bitmap, index) {
    var _a;
    const paint = ctx2.state.paint;
    if ((paint == null ? void 0 : paint.document_id) === doc.document_id && paint.bitmap_id === bitmap.id && paint.cell_index === index) return paint.pixels;
    let changes = [];
    try {
      changes = JSON.parse(ctx2.draft("asset-changes", "[]"));
    } catch {
    }
    return ((_a = changes.find((c) => c.kind === "cell" && c.bitmap_id === bitmap.id && c.cell_index === index)) == null ? void 0 : _a.after_pixels) || bitmap.cells[index].pixels;
  }
  function setPixelBuffer(ctx2, doc, bitmap, index, pixels, persist = true) {
    ctx2.state.paint = { document_id: doc.document_id, bitmap_id: bitmap.id, cell_index: index, pixels: [...pixels] };
    ctx2.state.assetAcknowledgements = [];
    ctx2.state.pending = null;
    if (persist) ctx2.setDraft("paint-buffer", JSON.stringify(ctx2.state.paint));
  }
  function mountPixelStrokes(ctx2, doc, bitmap, redraw) {
    const canvas = document.getElementById("paint-canvas");
    if (!canvas) return;
    canvas.style.touchAction = "none";
    let pointer = null, history3 = null, start = null;
    const index = () => {
      var _a;
      return ((_a = ctx2.state.paint) == null ? void 0 : _a.cell_index) ?? 0;
    };
    const paint = (event) => {
      const rect = canvas.getBoundingClientRect(), x = Math.floor((event.clientX - rect.left) / rect.width * bitmap.width), y = Math.floor((event.clientY - rect.top) / rect.height * bitmap.height);
      if (x < 0 || y < 0 || x >= bitmap.width || y >= bitmap.height) return;
      const color = Number(document.getElementById("paint-color").value), bits = { "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4, "tile8-packed4-low-v1": 4 }[bitmap.codec];
      if (!Number.isInteger(color) || color < 0 || color >= 2 ** bits) throw Error("Choose a valid color index.");
      const pixels = [...pixelBuffer(ctx2, doc, bitmap, index())];
      pixels[y * bitmap.width + x] = color;
      ctx2.state.pixelCursor = { x, y };
      setPixelBuffer(ctx2, doc, bitmap, index(), pixels, false);
      redraw();
    };
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      canvas.focus();
      pointer = event.pointerId;
      canvas.setPointerCapture(pointer);
      ctx2.state.pending = null;
      ctx2.state.assetEditRevision = (ctx2.state.assetEditRevision || 0) + 1;
      start = [...pixelBuffer(ctx2, doc, bitmap, index())];
      history3 = historyFor(ctx2, doc, bitmap.id, index(), start);
      history3.begin(start);
      try {
        paint(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointermove", (event) => {
      if (pointer !== event.pointerId) return;
      try {
        paint(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    const finish = async (event) => {
      if (pointer !== event.pointerId) return;
      pointer = null;
      history3.commit(pixelBuffer(ctx2, doc, bitmap, index()));
      setPixelBuffer(ctx2, doc, bitmap, index(), pixelBuffer(ctx2, doc, bitmap, index()));
      await ctx2.render();
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);
  }

  // romancer/ui/pixel_tools.js
  function checkedPixels(pixels, width, height, colorCount) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 32 || height > 32 || !Array.isArray(pixels) || pixels.length !== width * height) throw new Error("Tile dimensions do not match the pixel buffer.");
    if (!Number.isInteger(colorCount) || colorCount < 2 || colorCount > 256 || pixels.some((value) => !Number.isInteger(value) || value < 0 || value >= colorCount)) throw new Error("A pixel index is outside the destination palette.");
    return [...pixels];
  }
  function transformPixels(pixels, width, height, operation, color = 0, colorCount = 256) {
    const source = checkedPixels(pixels, width, height, colorCount), output = [...source];
    if (!["fill", "clear", "flip-x", "flip-y", "rotate-cw", "rotate-ccw"].includes(operation)) throw new Error("Choose a supported tile transform.");
    if (operation === "fill") {
      if (!Number.isInteger(color) || color < 0 || color >= colorCount) throw new Error("Choose a color index inside the palette.");
      return output.fill(color);
    }
    if (operation === "clear") return output.fill(0);
    if (operation.startsWith("rotate") && width !== height) throw new Error("90 degree rotation requires a square tile.");
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const index = operation === "flip-x" ? y * width + (width - 1 - x) : operation === "flip-y" ? (height - 1 - y) * width + x : operation === "rotate-cw" ? (height - 1 - x) * width + y : x * width + (width - 1 - y);
      output[y * width + x] = source[index];
    }
    return output;
  }
  function copyTile(pixels, width, height, colorCount) {
    return { format: "romancer-tile-v1", width, height, pixels: checkedPixels(pixels, width, height, colorCount) };
  }
  function pasteTile(clipboard, width, height, colorCount) {
    if (!clipboard || typeof clipboard !== "object" || Object.keys(clipboard).sort().join(",") !== "format,height,pixels,width" || clipboard.format !== "romancer-tile-v1") throw new Error("Copy a tile inside ROMancer first.");
    if (clipboard.width !== width || clipboard.height !== height) throw new Error("Clipboard tile dimensions differ from this cell.");
    return checkedPixels(clipboard.pixels, width, height, colorCount);
  }
  function mergeCellChanges(changes, incoming) {
    if (!Array.isArray(changes) || !Array.isArray(incoming) || changes.length > 1024 || incoming.length > 1024) throw new Error("Review at most1024 asset changes at a time.");
    const keys2 = /* @__PURE__ */ new Set();
    for (const change of incoming) {
      if (change.kind !== "cell" || typeof change.bitmap_id !== "string" || !Number.isSafeInteger(change.cell_index) || change.cell_index < 0 || !Array.isArray(change.before_pixels) || !Array.isArray(change.after_pixels) || change.before_pixels.length !== change.after_pixels.length || change.before_pixels.length > 1024) throw new Error("Invalid staged tile change.");
      keys2.add(change.bitmap_id + ":" + change.cell_index);
    }
    const merged = [...changes.filter((change) => change.kind !== "cell" || !keys2.has(change.bitmap_id + ":" + change.cell_index)), ...incoming.filter((change) => JSON.stringify(change.before_pixels) !== JSON.stringify(change.after_pixels))];
    if (merged.length > 1024) throw new Error("Review at most1024 asset changes at a time.");
    return JSON.parse(JSON.stringify(merged));
  }

  // romancer/ui/tilemap_editor.js
  function canvasCell(rect, x, y, width, height) {
    if (rect.width <= 0 || rect.height <= 0 || x < rect.left || y < rect.top || x >= rect.left + rect.width || y >= rect.top + rect.height) return null;
    return Math.floor((y - rect.top) / rect.height * height) * width + Math.floor((x - rect.left) / rect.width * width);
  }
  function paintMapCell(doc, map, changes, index, brush) {
    if (Object.keys(brush).sort().join(",") !== "flip_x,flip_y,palette_bank,tile_index") throw Error("Provide tile, palette and both flip values.");
    const bitmap = doc.bitmaps.find((r) => r.id === map.bitmap_id), palette2 = doc.palettes.find((r) => r.id === map.palette_id), entry = map.entries[index];
    if (!entry) throw Error("Choose a declared map cell.");
    for (const [key3, value] of Object.entries(brush)) {
      if (!["tile_index", "palette_bank", "flip_x", "flip_y"].includes(key3) || !Number.isInteger(value) || value < 0) throw Error("Invalid map brush value.");
      const field2 = map.fields[key3];
      if (field2.kind === "constant" && value !== field2.value) throw Error(key3 + " is constant in this declaration.");
      if (field2.kind === "bits") {
        const shift = Math.log2(field2.mask & -field2.mask), max = field2.mask >>> shift;
        if (value > max) throw Error(key3 + " exceeds its declared storage field.");
      }
    }
    if (brush.tile_index >= bitmap.count) throw Error("Choose an existing tile.");
    if (brush.palette_bank >= palette2.banks) throw Error("Choose an existing palette bank.");
    if (brush.flip_x > 1 || brush.flip_y > 1) throw Error("Flips must be on or off.");
    const result = changes.filter((c) => !(c.kind === "map" && c.tilemap_id === map.id && c.entry_index === index));
    if (JSON.stringify(brush) !== JSON.stringify(entry.values)) result.push({ kind: "map", tilemap_id: map.id, entry_index: index, before: { ...entry.values }, after: { ...brush } });
    if (result.length > 1024) throw Error("Review at most 1024 asset changes per build.");
    return result;
  }
  function colorFor(palette2, bank, index, changes) {
    const entry = palette2.entries[bank * palette2.colors_per_bank + index], change = changes.find((c) => c.kind === "palette" && c.palette_id === palette2.id && c.bank === bank && c.index === index);
    if (!change) return entry.rgb;
    const rgb = {};
    for (const name of ["r", "g", "b"]) {
      const mask = palette2.channels[name], maximum = mask >> Math.log2(mask & -mask);
      rgb[name] = Math.round(change.after[name] * 255 / maximum);
    }
    return rgb;
  }
  function mapPixels(doc, map, changes) {
    var _a, _b;
    const tiles = doc.bitmaps.find((b) => b.id === map.bitmap_id), palette2 = doc.palettes.find((p) => p.id === map.palette_id), width = map.width * tiles.width, height = map.height * tiles.height;
    if (width > 32768 || height > 32768 || width * height > 262144) throw Error("Declared map preview exceeds the canvas budget.");
    const image = new Uint8ClampedArray(width * height * 4);
    for (const entry of map.entries) {
      const v = ((_a = changes.find((c) => c.kind === "map" && c.tilemap_id === map.id && c.entry_index === entry.index)) == null ? void 0 : _a.after) || entry.values, pixels = ((_b = changes.find((c) => c.kind === "cell" && c.bitmap_id === tiles.id && c.cell_index === v.tile_index)) == null ? void 0 : _b.after_pixels) || tiles.cells[v.tile_index].pixels;
      for (let y = 0; y < tiles.height; y++) for (let x = 0; x < tiles.width; x++) {
        const px = v.flip_x ? tiles.width - 1 - x : x, py = v.flip_y ? tiles.height - 1 - y : y, c = colorFor(palette2, v.palette_bank, pixels[py * tiles.width + px], changes), offset = ((Math.floor(entry.index / map.width) * tiles.height + y) * width + entry.index % map.width * tiles.width + x) * 4;
        image.set([c.r, c.g, c.b, 255], offset);
      }
    }
    return image;
  }
  function flipSelect(ctx2, map, key3, label) {
    const field2 = map.fields[key3], id = "map-" + key3.replaceAll("_", "-");
    return field2.kind === "constant" ? `<p>${esc(label)}: ${field2.value ? "On" : "Off"} (fixed)<input id="${id}" type="hidden" value="${field2.value}"></p>` : select(id, label, [["0", "Off"], ["1", "On"]], ctx2.draft(id, "0"));
  }
  function tilemapControls(ctx2, doc, map) {
    var _a;
    if (!map) return "";
    const tiles = doc.bitmaps.find((r) => r.id === map.bitmap_id), palette2 = doc.palettes.find((r) => r.id === map.palette_id), page = Math.min(Math.floor((tiles.count - 1) / 64), ctx2.state.mapTilePage || 0);
    ctx2.use({ "map-pick-tile": (node) => {
      ctx2.setDraft("map-tile", node.dataset.id);
      return ctx2.render();
    }, "map-tiles-page": (node) => {
      ctx2.state.mapTilePage = Math.max(0, page + Number(node.dataset.id));
      return ctx2.render();
    }, "map-use-pixel-tile": () => {
      var _a2;
      if (((_a2 = ctx2.state.paint) == null ? void 0 : _a2.bitmap_id) !== tiles.id) throw Error("Select a tile from this map’s bitmap first.");
      ctx2.setDraft("map-tile", String(ctx2.state.paint.cell_index));
      return ctx2.render();
    } });
    return `<section class="card" id="tilemap-editor"><h3>Tilemap · ${esc(map.id)}</h3><div class="actions">${doc.tilemaps.length > 1 ? doc.tilemaps.map((r) => button(r.id, "asset-map-group", { id: r.id })).join("") : ""}</div><p>Pick a tile, then paint map cells. Review asset changes to create a build.</p>
 <div class="hex-scroll"><canvas id="map-preview" tabindex="0" aria-label="Tilemap editor: arrows move, Space paints the selected tile"></canvas></div><p id="map-position">Cell 0</p><p id="map-preview-status" class="preview-caption" role="status" aria-live="polite"></p>
 <div class="field-row">${field("map-tile", "Brush tile index", ctx2.draft("map-tile", String(map.fields.tile_index.kind === "constant" ? map.fields.tile_index.value : 0)), { readonly: map.fields.tile_index.kind === "constant" })}${field("map-bank", "Palette bank", ctx2.draft("map-bank", String(map.fields.palette_bank.kind === "constant" ? map.fields.palette_bank.value : 0)), { readonly: map.fields.palette_bank.kind === "constant" })}${flipSelect(ctx2, map, "flip_x", "Horizontal flip")}${flipSelect(ctx2, map, "flip_y", "Vertical flip")}</div>
 <div class="pixel-grid map-tile-picker">${tiles.cells.slice(page * 64, page * 64 + 64).map((c) => `<div class="pixel-card"><canvas width="${tiles.width}" height="${tiles.height}" data-map-tile="${c.index}" aria-label="Brush tile ${c.index}"></canvas>${button(String(c.index), "map-pick-tile", { id: String(c.index), disabled: map.fields.tile_index.kind === "constant" && c.index !== map.fields.tile_index.value })}</div>`).join("")}</div><div class="actions">${button("Previous tiles", "map-tiles-page", { id: "-1", disabled: !page })}${button("Next tiles", "map-tiles-page", { id: "1", disabled: (page + 1) * 64 >= tiles.count })}${button("Use selected pixel tile", "map-use-pixel-tile", { disabled: ((_a = ctx2.state.paint) == null ? void 0 : _a.bitmap_id) !== tiles.id })}</div><details><summary>Single-cell controls</summary>${field("map-entry", "Cell index", ctx2.draft("map-entry", "0"))}${button("Load map entry", "asset-open-map-entry")}${button("Stage map change", "asset-map-change")}</details></section>`;
  }
  function mountTilemap(ctx2, doc, map, changes) {
    const canvas = document.getElementById("map-preview");
    if (!map || !canvas) return;
    const tiles = doc.bitmaps.find((b) => b.id === map.bitmap_id), palette2 = doc.palettes.find((p) => p.id === map.palette_id);
    let current2 = changes, selected2 = 0, pointer = null;
    const draw2 = () => {
      canvas.width = map.width * tiles.width;
      canvas.height = map.height * tiles.height;
      canvas.style.imageRendering = "pixelated";
      canvas.style.width = Math.min(1024, canvas.width * 3) + "px";
      canvas.style.touchAction = "none";
      const context = canvas.getContext("2d"), image = context.createImageData(canvas.width, canvas.height);
      image.data.set(mapPixels(doc, map, current2));
      context.putImageData(image, 0, 0);
    };
    const persist = (save = true) => {
      var _a;
      if (save) ctx2.setDraft("asset-changes", JSON.stringify(current2, null, 2));
      const node = document.getElementById("asset-changes");
      if (node) node.value = JSON.stringify(current2, null, 2);
      ctx2.state.pending = null;
      ctx2.state.assetAcknowledgements = [];
      (_a = document.querySelector('[data-action="asset-apply"]')) == null ? void 0 : _a.setAttribute("disabled", "");
    };
    const paint = (index, save = true) => {
      const brush = { tile_index: Number(read("map-tile")), palette_bank: Number(read("map-bank")), flip_x: map.fields.flip_x.kind === "constant" ? map.fields.flip_x.value : Number(read("map-flip-x")), flip_y: map.fields.flip_y.kind === "constant" ? map.fields.flip_y.value : Number(read("map-flip-y")) };
      current2 = paintMapCell(doc, map, current2, index, brush);
      selected2 = index;
      persist(save);
      draw2();
      previewStatus();
      const label = document.getElementById("map-position");
      if (label) label.textContent = "Cell " + selected2 + " · " + current2.filter((c) => c.kind === "map" && c.tilemap_id === map.id).length + " staged cells";
    };
    const eventPaint = (event) => {
      const index = canvasCell(canvas.getBoundingClientRect(), event.clientX, event.clientY, map.width, map.height);
      if (index !== null) paint(index, false);
    };
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      canvas.focus();
      pointer = event.pointerId;
      canvas.setPointerCapture(pointer);
      try {
        eventPaint(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointermove", (event) => {
      if (event.pointerId !== pointer) return;
      try {
        eventPaint(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    const finish = () => {
      if (pointer !== null) {
        pointer = null;
        persist();
      }
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);
    canvas.addEventListener("keydown", (event) => {
      const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -map.width, ArrowDown: map.width }[event.key];
      if (delta) {
        event.preventDefault();
        selected2 = Math.max(0, Math.min(map.entries.length - 1, selected2 + delta));
        document.getElementById("map-position").textContent = "Cell " + selected2;
      }
      if ([" ", "Enter"].includes(event.key)) {
        event.preventDefault();
        try {
          paint(selected2);
        } catch (error) {
          ctx2.notify(error.message, true);
        }
      }
    });
    const brushes = () => document.querySelectorAll("[data-map-tile]").forEach((node) => {
      var _a;
      const index = Number(node.dataset.mapTile), pixels = ((_a = current2.find((c) => c.kind === "cell" && c.bitmap_id === tiles.id && c.cell_index === index)) == null ? void 0 : _a.after_pixels) || tiles.cells[index].pixels, context = node.getContext("2d"), image = context.createImageData(tiles.width, tiles.height);
      pixels.forEach((v, i) => {
        const c = colorFor(palette2, 0, v, current2);
        image.data.set([c.r, c.g, c.b, 255], i * 4);
      });
      context.putImageData(image, 0, 0);
    });
    const previewStatus = () => {
      const label = document.getElementById("map-preview-status");
      if (label) label.textContent = current2.length ? "Preview updated · " + current2.length + " staged graphics changes · not built" : "Unchanged map preview";
    };
    canvas.addEventListener("map-refresh", () => {
      var _a, _b;
      if (pointer !== null || document.getElementById("map-preview") !== canvas || ((_b = (_a = ctx2.state.results) == null ? void 0 : _a["assets.inspect"]) == null ? void 0 : _b.document_id) !== doc.document_id) return;
      try {
        current2 = JSON.parse(ctx2.draft("asset-changes", "[]"));
        const paint2 = ctx2.state.paint;
        if ((paint2 == null ? void 0 : paint2.document_id) === doc.document_id) {
          const bitmap = doc.bitmaps.find((b) => b.id === paint2.bitmap_id);
          if (bitmap) current2 = mergeCellChanges(current2, [{ kind: "cell", bitmap_id: bitmap.id, cell_index: paint2.cell_index, before_pixels: bitmap.cells[paint2.cell_index].pixels, after_pixels: paint2.pixels }]);
        }
        draw2();
        brushes();
        previewStatus();
      } catch (error) {
        const label = document.getElementById("map-preview-status");
        if (label) label.textContent = "Preview unavailable: " + error.message;
      }
    });
    draw2();
    brushes();
    previewStatus();
  }

  // romancer/ui/asset_controls.js
  function stage(ctx2, change) {
    const changes = json("asset-changes"), key3 = (c) => [c.kind, c.bitmap_id, c.cell_index, c.palette_id, c.bank, c.index, c.tilemap_id, c.entry_index, c.font_id, c.glyph_id].join(":");
    const filtered = changes.filter((c) => key3(c) !== key3(change));
    filtered.push(change);
    ctx2.setDraft("asset-changes", JSON.stringify(filtered, null, 2));
    ctx2.state.assetAcknowledgements = [];
    ctx2.state.pending = null;
    return ctx2.render();
  }
  function stageCurrentPaint(ctx2, doc) {
    const changes = json("asset-changes"), paint = ctx2.state.paint;
    if (!paint || paint.document_id !== doc.document_id) return changes;
    const bitmap = doc.bitmaps.find((row) => row.id === paint.bitmap_id), cell = bitmap == null ? void 0 : bitmap.cells[paint.cell_index];
    if (!cell) return changes;
    const merged = mergeCellChanges(changes, [{ kind: "cell", bitmap_id: bitmap.id, cell_index: paint.cell_index, before_pixels: cell.pixels, after_pixels: paint.pixels }]);
    if (JSON.stringify(merged) !== JSON.stringify(changes)) ctx2.setDraft("asset-changes", JSON.stringify(merged, null, 2));
    return merged;
  }
  function activateCell(ctx2, doc, bitmapId, index) {
    const changes = stageCurrentPaint(ctx2, doc), bitmap = doc.bitmaps.find((row) => row.id === bitmapId), cell = bitmap == null ? void 0 : bitmap.cells[index];
    if (!cell) throw new Error("Choose a declared tile.");
    const existing = changes.find((row) => row.kind === "cell" && row.bitmap_id === bitmapId && row.cell_index === index);
    ctx2.state.assetBitmapId = bitmapId;
    ctx2.state.assetPage = Math.floor(index / 64);
    ctx2.state.paint = { document_id: doc.document_id, bitmap_id: bitmapId, cell_index: index, pixels: [...(existing == null ? void 0 : existing.after_pixels) || cell.pixels] };
    ctx2.state.assetAcknowledgements = [];
    ctx2.state.pending = null;
    ctx2.setDraft("paint-buffer", JSON.stringify(ctx2.state.paint));
  }
  function assetTools(ctx2, doc, bitmap, palette2) {
    var _a, _b, _c, _d, _e, _f;
    if (!(doc == null ? void 0 : doc.ok) || !bitmap) return "";
    const { state: state2 } = ctx2, map = doc.tilemaps.find((row) => row.id === state2.assetMapId) || doc.tilemaps[0], font = doc.fonts.find((row) => row.id === state2.assetFontId) || doc.fonts[0];
    const count = Math.min(2 ** { "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4, "tile8-packed4-low-v1": 4 }[bitmap.codec], (palette2 == null ? void 0 : palette2.colors_per_bank) || 256);
    const pixels = () => {
      var _a2;
      return pixelBuffer(ctx2, doc, bitmap, ((_a2 = state2.paint) == null ? void 0 : _a2.cell_index) ?? 0);
    };
    const history3 = historyFor(ctx2, doc, bitmap.id, ((_a = state2.paint) == null ? void 0 : _a.cell_index) ?? 0, pixels());
    const commit = (after) => {
      var _a2;
      state2.historyEditor = "paint-canvas";
      const index = ((_a2 = state2.paint) == null ? void 0 : _a2.cell_index) ?? 0;
      recordPixels(ctx2, doc, bitmap.id, index, pixels(), after);
      setPixelBuffer(ctx2, doc, bitmap, index, after);
      return ctx2.render();
    };
    const usage = state2.results["resources.references"], showUses = (usage == null ? void 0 : usage.document_id) === doc.document_id && usage.bitmap_id === bitmap.id && usage.cell_index === (((_b = state2.paint) == null ? void 0 : _b.cell_index) ?? 0);
    const glyph = font == null ? void 0 : font.glyphs.find((row) => {
      var _a2;
      return row.id === ctx2.draft("font-glyph", (_a2 = font.glyphs[0]) == null ? void 0 : _a2.id);
    });
    ctx2.use({
      "pixel-undo": () => {
        var _a2;
        setPixelBuffer(ctx2, doc, bitmap, ((_a2 = state2.paint) == null ? void 0 : _a2.cell_index) ?? 0, history3.undo());
        return ctx2.render();
      },
      "pixel-redo": () => {
        var _a2;
        setPixelBuffer(ctx2, doc, bitmap, ((_a2 = state2.paint) == null ? void 0 : _a2.cell_index) ?? 0, history3.redo());
        return ctx2.render();
      },
      "asset-transform": (node) => commit(transformPixels(pixels(), bitmap.width, bitmap.height, node.dataset.id, Number(read("paint-color")), count)),
      "asset-copy": () => {
        state2.tileClipboard = copyTile(pixels(), bitmap.width, bitmap.height, count);
        ctx2.notify("Tile indices copied.");
        return ctx2.render();
      },
      "asset-paste": () => commit(pasteTile(state2.tileClipboard, bitmap.width, bitmap.height, count)),
      "asset-export-image": async () => {
        const result = await ctx2.run("resources.export_image", { ...ctx2.sourceParams(), schema: json("asset-schema"), bitmap_id: bitmap.id, columns: Number(read("image-columns")), bank: Number(read("image-bank")) }, { render: false });
        await ctx2.api.download(state2.project.project_id, result.export.export_id, "tiles.png");
        await ctx2.render();
      },
      "asset-uses": () => {
        var _a2;
        return ctx2.run("resources.references", { ...ctx2.sourceParams(), schema: json("asset-schema"), bitmap_id: bitmap.id, cell_index: ((_a2 = state2.paint) == null ? void 0 : _a2.cell_index) ?? 0 });
      },
      "asset-use-open": (node) => {
        const row = usage.uses[Number(node.dataset.id)];
        if (row.kind === "tilemap") {
          state2.assetMapId = row.id;
          ctx2.setDraft("map-entry", String(row.entry_index));
        } else {
          state2.assetFontId = row.id;
          ctx2.setDraft("font-glyph", row.glyph_id);
        }
        return ctx2.render();
      },
      "asset-map-group": (node) => {
        state2.assetMapId = node.dataset.id;
        ctx2.setDraft("map-entry", "0");
        return ctx2.render();
      },
      "asset-font-group": (node) => {
        state2.assetFontId = node.dataset.id;
        return ctx2.render();
      },
      "asset-open-map-entry": () => {
        const row = map == null ? void 0 : map.entries[Number(read("map-entry"))];
        if (!row) throw new Error("Choose a declared map entry.");
        for (const [id, value] of Object.entries({ "map-tile": row.values.tile_index, "map-bank": row.values.palette_bank, "map-flip-x": row.values.flip_x, "map-flip-y": row.values.flip_y })) ctx2.setDraft(id, String(value));
        return ctx2.render();
      },
      "asset-open-glyph": () => {
        const glyph2 = font == null ? void 0 : font.glyphs.find((row) => row.id === read("font-glyph"));
        if (!glyph2) throw new Error("Choose a glyph.");
        activateCell(ctx2, doc, glyph2.bitmap_id, glyph2.cell_index);
        ctx2.setDraft("font-advance", String(glyph2.advance_pixels));
        return ctx2.render();
      },
      "asset-zoom": (node) => {
        state2.tileZoom = Number(node.dataset.id);
        ctx2.render();
      },
      "asset-group": (node) => {
        stageCurrentPaint(ctx2, doc);
        state2.assetBitmapId = node.dataset.id;
        state2.assetPage = 0;
        state2.paint = null;
        ctx2.setDraft("paint-buffer", "");
        state2.pixelCursor = { x: 0, y: 0 };
        return ctx2.render();
      },
      "asset-page": (node) => {
        state2.assetPage = Math.max(0, (state2.assetPage || 0) + Number(node.dataset.id));
        ctx2.render();
      },
      "asset-map-change": () => {
        if (!map) throw new Error("Declare a tilemap first.");
        const index = Number(read("map-entry")), entry = map.entries[index];
        if (!entry) throw new Error("Choose a map entry.");
        return stage(ctx2, { kind: "map", tilemap_id: map.id, entry_index: index, before: entry.values, after: { tile_index: Number(read("map-tile")), palette_bank: Number(read("map-bank")), flip_x: Number(read("map-flip-x")), flip_y: Number(read("map-flip-y")) } });
      },
      "asset-font-change": () => {
        const glyph2 = font == null ? void 0 : font.glyphs.find((g) => g.id === read("font-glyph"));
        if (!glyph2) throw new Error("Choose a glyph.");
        return stage(ctx2, { kind: "advance", font_id: font.id, glyph_id: glyph2.id, before: glyph2.advance_pixels, after: Number(read("font-advance")) });
      },
      "asset-image-map": async () => {
        var _a2;
        const ticket = selectionKey(state2), file = document.getElementById("image-file").files[0];
        if (!file || file.size > 512 * 1024) throw new Error("Choose a PNG up to512KiB.");
        const bytes = new Uint8Array(await file.arrayBuffer());
        let text = "";
        for (const byte of bytes) text += String.fromCharCode(byte);
        if (ticket !== selectionKey(state2)) throw Error("Source changed. Import again.");
        const result = await ctx2.run("resources.image_map_selection", { ...ctx2.sourceParams(), schema: json("asset-schema"), bitmap_id: bitmap.id, bank: Number(read("image-bank")), png_base64: btoa(text), columns: Number(read("image-columns")), mode: read("image-mode") }, { render: false });
        if (ticket !== selectionKey(state2)) throw Error("Source changed. Import again.");
        for (const cell of bitmap.cells) {
          const before = pixelBuffer(ctx2, doc, bitmap, cell.index), after = ((_a2 = result.changes.find((c) => c.cell_index === cell.index)) == null ? void 0 : _a2.after_pixels) || cell.pixels;
          recordPixels(ctx2, doc, bitmap.id, cell.index, before, after);
        }
        const unrelated = json("asset-changes").filter((change) => change.kind !== "cell" || change.bitmap_id !== bitmap.id);
        const merged = mergeCellChanges(unrelated, result.changes);
        state2.results["resources.image_map"] = result;
        state2.paint = null;
        ctx2.setDraft("paint-buffer", "");
        ctx2.setDraft("asset-changes", JSON.stringify(merged, null, 2));
        state2.assetAcknowledgements = [];
        state2.pending = null;
        await ctx2.render();
      }
    });
    return `<section class="card asset-tools"><div class="card-heading"><h3>Editor tools</h3></div><div class="asset-tool-options"><div class="actions" aria-label="Bitmap group">${doc.bitmaps.map((b) => button(b.id, "asset-group", { id: b.id })).join("")}</div><div class="actions" aria-label="Tile zoom"><span class="subtle">Zoom</span>${[16, 24, 32, 48].map((n) => button(n + "×", "asset-zoom", { id: String(n) })).join("")}</div></div><div class="actions asset-transform-tools">${button("Undo pixels", "pixel-undo", { disabled: !history3.canUndo })}${button("Redo pixels", "pixel-redo", { disabled: !history3.canRedo })}${[["fill", "Fill tile"], ["clear", "Clear"], ["flip-x", "Flip horizontally"], ["flip-y", "Flip vertically"], ["rotate-cw", "Rotate right"], ["rotate-ccw", "Rotate left"]].map(([id, label]) => button(label, "asset-transform", { id })).join("")}${button("Copy tile", "asset-copy")}${button("Paste tile", "asset-paste", { disabled: !state2.tileClipboard })}${button("Find declared uses", "asset-uses")}</div><div class="asset-tool-status"><span class="subtle">Arrows move · Space paints</span><span id="pixel-position" class="mono">Pixel ${((_c = state2.pixelCursor) == null ? void 0 : _c.x) || 0}, ${((_d = state2.pixelCursor) == null ? void 0 : _d.y) || 0}</span></div></section>
${showUses ? `<section class="card"><h3>Declared uses</h3>${usage.uses.length ? usage.uses.map((row, i) => `<div class="actions"><span>${esc(row.id)} · ${row.kind === "tilemap" ? "entry " + row.entry_index : "glyph " + esc(row.glyph_id)}</span>${button("Open", "asset-use-open", { id: String(i) })}</div>`).join("") : "<p>No uses in this declaration.</p>"}<p class="subtle">Undeclared uses remain unknown.</p></section>` : ""}
${tilemapControls(ctx2, doc, map)}
${font ? `<section class="card"><h3>Font metrics · ${esc(font.id)}</h3><div class="actions">${doc.fonts.length > 1 ? doc.fonts.map((row) => button(row.id, "asset-font-group", { id: row.id })).join("") : ""}</div>${select("font-glyph", "Glyph", font.glyphs.map((g) => [g.id, g.id + " · " + g.advance_pixels + " px"]), ctx2.draft("font-glyph", (_e = font.glyphs[0]) == null ? void 0 : _e.id))}${field("font-advance", "Advance in pixels", ctx2.draft("font-advance", ((_f = font.glyphs[0]) == null ? void 0 : _f.advance_pixels) || 8))}${button("Open glyph", "asset-open-glyph")}${button("Stage advance change", "asset-font-change", { disabled: (glyph == null ? void 0 : glyph.advance.kind) !== "u8" })}</section>` : ""}
<details class="card"><summary>Import or export PNG</summary><label class="field"><span>Opaque PNG, up to512KiB</span><input id="image-file" type="file" accept="image/png"></label>${field("image-columns", "Tiles per row", ctx2.draft("image-columns", "1"))}${select("image-mode", "Color mapping", [["exact", "Exact palette colors"], ["nearest", "Nearest color — review conversion"]], ctx2.draft("image-mode", "exact"))}${field("image-bank", "Palette bank", ctx2.draft("image-bank", "0"), { type: "number", min: 0 })}${button("Preview mapped changes", "asset-image-map")}${button("Export stored PNG", "asset-export-image")}<p class="subtle">Create a build to include pending edits in an exported PNG.</p>${report(state2.results["resources.image_map"], "Image mapping")}</details>`;
  }
  function mountTools(ctx2, doc, bitmap, redraw) {
    if (!bitmap) return;
    const canvas = document.getElementById("paint-canvas");
    if (canvas) {
      canvas.style.width = bitmap.width * (ctx2.state.tileZoom || 24) + "px";
      canvas.style.height = "auto";
      canvas.setAttribute("role", "application");
      canvas.setAttribute("aria-label", "Pixel editor: arrows move; Space paints selected index");
      canvas.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Enter"].includes(event.key)) return;
        event.preventDefault();
        const state2 = ctx2.state, cursor = state2.pixelCursor || { x: 0, y: 0 };
        if (event.key === "ArrowLeft") cursor.x = Math.max(0, cursor.x - 1);
        if (event.key === "ArrowRight") cursor.x = Math.min(bitmap.width - 1, cursor.x + 1);
        if (event.key === "ArrowUp") cursor.y = Math.max(0, cursor.y - 1);
        if (event.key === "ArrowDown") cursor.y = Math.min(bitmap.height - 1, cursor.y + 1);
        state2.pixelCursor = cursor;
        if ([" ", "Enter"].includes(event.key)) {
          const color = Number(read("paint-color")), bits = { "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4, "tile8-packed4-low-v1": 4 }[bitmap.codec];
          if (!Number.isInteger(color) || color < 0 || color >= 2 ** bits) {
            ctx2.notify("Choose a valid palette index.", true);
            return;
          }
          if (!state2.paint) state2.paint = { document_id: doc.document_id, bitmap_id: bitmap.id, cell_index: 0, pixels: [...pixelBuffer(ctx2, doc, bitmap, 0)] };
          const before = [...state2.paint.pixels];
          state2.paint.pixels[cursor.y * bitmap.width + cursor.x] = color;
          recordPixels(ctx2, doc, bitmap.id, state2.paint.cell_index, before, state2.paint.pixels);
          const activeHistory = historyFor(ctx2, doc, bitmap.id, state2.paint.cell_index, state2.paint.pixels), undo = document.querySelector('[data-action="pixel-undo"]'), redo = document.querySelector('[data-action="pixel-redo"]');
          if (undo) undo.disabled = !activeHistory.canUndo;
          if (redo) redo.disabled = !activeHistory.canRedo;
          state2.assetAcknowledgements = [];
          state2.pending = null;
          ctx2.setDraft("paint-buffer", JSON.stringify(state2.paint));
          redraw();
        }
        const label = document.getElementById("pixel-position");
        if (label) label.textContent = "Pixel " + cursor.x + ", " + cursor.y;
      });
    }
    mountPixelStrokes(ctx2, doc, bitmap, redraw);
    const map = doc.tilemaps.find((row) => row.id === ctx2.state.assetMapId) || doc.tilemaps[0];
    let changes = json("asset-changes");
    const paint = ctx2.state.paint;
    if ((paint == null ? void 0 : paint.document_id) === doc.document_id) {
      const b = doc.bitmaps.find((r) => r.id === paint.bitmap_id);
      changes = mergeCellChanges(changes, [{ kind: "cell", bitmap_id: b.id, cell_index: paint.cell_index, before_pixels: b.cells[paint.cell_index].pixels, after_pixels: paint.pixels }]);
    }
    mountTilemap(ctx2, doc, map, changes);
  }

  // romancer/ui/sprite_assembly.js
  function makeAssembly(bitmap, { first = 0, columns: columns2, rows, order = "rows", indices = null, flips = null, colors = null, provenance = "declared_layout" }) {
    if (![first, columns2, rows].every(Number.isSafeInteger) || first < 0 || columns2 < 1 || rows < 1 || columns2 > 8 || rows > 8 || !["rows", "columns"].includes(order)) throw Error("Choose a grid of up to 8 × 8 declared tiles.");
    const custom = indices !== null;
    if (custom && (!Array.isArray(indices) || indices.length !== columns2 * rows || !indices.some((v) => v !== null) || indices.some((v) => v !== null && (!Number.isSafeInteger(v) || v < 0 || v >= bitmap.count)))) throw Error("Every mapped tile must be inside the declared tile collection.");
    if (!custom && first + columns2 * rows > bitmap.count) throw Error("Choose a grid inside the declared tile collection.");
    const tiles = custom ? [...indices] : Array.from({ length: columns2 * rows }, (_, i) => first + (order === "rows" ? i : i % columns2 * rows + Math.floor(i / columns2)));
    flips = flips ?? tiles.map(() => 0);
    if (!Array.isArray(flips) || flips.length !== tiles.length || flips.some((v) => !Number.isSafeInteger(v) || v < 0 || v > 3)) throw Error("Tile flips must be0,1(horizontal),2(vertical) or3.");
    if (colors !== null && (!Array.isArray(colors) || colors.length !== tiles.length || colors.some((group) => group !== null && (typeof group !== "object" || Array.isArray(group) || Object.entries(group).some(([k, c]) => !/^\d{1,2}$/.test(k) || Number(k) > 15 || !Array.isArray(c) || c.length !== 3 || c.some((v) => !Number.isInteger(v) || v < 0 || v > 255)))))) throw Error("Observed tile colors are invalid.");
    return { first, columns: columns2, rows, order, tiles, indices: custom ? [...indices] : null, flips: [...flips], colors, provenance: provenance === "pixel_candidate" ? "pixel_candidate" : "declared_layout" };
  }
  function storedPixel(bitmap, layout, part, x, y) {
    var _a;
    const flip = ((_a = layout.flips) == null ? void 0 : _a[part]) || 0;
    return (flip & 2 ? bitmap.height - 1 - y : y) * bitmap.width + (flip & 1 ? bitmap.width - 1 - x : x);
  }
  function assemblePixels(bitmap, layout, buffer) {
    const width = layout.columns * bitmap.width, height = layout.rows * bitmap.height, pixels = Array(width * height).fill(0);
    layout.tiles.forEach((index, i) => {
      if (index === null) return;
      const tile = buffer(index);
      if (!tile || tile.length !== bitmap.width * bitmap.height) throw Error("Tile dimensions differ.");
      for (let y = 0; y < bitmap.height; y++) for (let x = 0; x < bitmap.width; x++) pixels[(Math.floor(i / layout.columns) * bitmap.height + y) * width + i % layout.columns * bitmap.width + x] = tile[storedPixel(bitmap, layout, i, x, y)];
    });
    return { width, height, pixels };
  }
  function assemblyChanges(bitmap, layout, pixels) {
    const width = layout.columns * bitmap.width, height = layout.rows * bitmap.height;
    if (!Array.isArray(pixels) || pixels.length !== width * height) throw Error("Sprite dimensions differ.");
    const changed2 = /* @__PURE__ */ new Map();
    layout.tiles.forEach((index, i) => {
      if (index === null) return;
      const after = Array(bitmap.width * bitmap.height);
      for (let y = 0; y < bitmap.height; y++) for (let x = 0; x < bitmap.width; x++) after[storedPixel(bitmap, layout, i, x, y)] = pixels[(Math.floor(i / layout.columns) * bitmap.height + y) * width + i % layout.columns * bitmap.width + x];
      if (changed2.has(index) && JSON.stringify(changed2.get(index)) !== JSON.stringify(after)) throw Error("Shared tile copies disagree. Paint the shared tile together.");
      changed2.set(index, after);
    });
    return [...changed2].map(([index, after]) => ({ kind: "cell", bitmap_id: bitmap.id, cell_index: index, before_pixels: bitmap.cells[index].pixels, after_pixels: after })).filter((e) => JSON.stringify(e.before_pixels) !== JSON.stringify(e.after_pixels));
  }
  function paintAssemblyPixel(bitmap, layout, pixels, x, y, color) {
    const width = layout.columns * bitmap.width, part = Math.floor(y / bitmap.height) * layout.columns + Math.floor(x / bitmap.width), index = layout.tiles[part];
    if (index === null || index === void 0) throw Error("This part has no mapped source tile.");
    const stored2 = storedPixel(bitmap, layout, part, x % bitmap.width, y % bitmap.height);
    layout.tiles.forEach((tile, i) => {
      if (tile !== index) return;
      for (let yy = 0; yy < bitmap.height; yy++) for (let xx = 0; xx < bitmap.width; xx++) if (storedPixel(bitmap, layout, i, xx, yy) === stored2) pixels[(Math.floor(i / layout.columns) * bitmap.height + yy) * width + i % layout.columns * bitmap.width + xx] = color;
    });
  }
  function mapSettings(text) {
    if (!text.trim()) return { indices: null, flips: null };
    const parts = text.trim().split(/[\s,\/]+/);
    return { indices: parts.map((token2) => token2 === "." ? null : Number(token2.replace(/[hv]/g, ""))), flips: parts.map((token2) => (token2.includes("h") ? 1 : 0) | (token2.includes("v") ? 2 : 0)) };
  }
  function layoutFor(ctx2, doc, bitmap) {
    try {
      const saved = JSON.parse(ctx2.draft("sprite-layout", "null"));
      if ((saved == null ? void 0 : saved.document_id) === doc.document_id && saved.bitmap_id === bitmap.id) return makeAssembly(bitmap, saved);
    } catch {
    }
    return null;
  }
  function imageFor(ctx2, doc, bitmap, layout) {
    return assemblePixels(bitmap, layout, (index) => pixelBuffer(ctx2, doc, bitmap, index));
  }
  function history2(ctx2, doc, bitmap, layout, image) {
    var _a;
    const scope = selectionKey(ctx2.state) + doc.document_id + bitmap.id + JSON.stringify(layout);
    if (((_a = ctx2.state.spriteHistory) == null ? void 0 : _a.scope) !== scope || JSON.stringify(ctx2.state.spriteHistory.current) !== JSON.stringify(image.pixels)) ctx2.state.spriteHistory = new PixelHistory(scope, image.pixels, 32);
    return ctx2.state.spriteHistory;
  }
  function stage2(ctx2, doc, bitmap, layout, pixels) {
    const previous = stageCurrentPaint(ctx2, doc), tiles = new Set(layout.tiles);
    const unrelated = previous.filter((c) => c.kind !== "cell" || c.bitmap_id !== bitmap.id || !tiles.has(c.cell_index));
    ctx2.setDraft("asset-changes", JSON.stringify(mergeCellChanges(unrelated, assemblyChanges(bitmap, layout, pixels)), null, 2));
    ctx2.state.paint = null;
    ctx2.setDraft("paint-buffer", "");
    ctx2.state.pending = null;
    ctx2.state.assetAcknowledgements = [];
  }
  function spriteAssembly(ctx2, doc, bitmap) {
    if (!(doc == null ? void 0 : doc.ok) || !bitmap) return "";
    const scope = selectionKey(ctx2.state), current2 = () => selectionKey(ctx2.state) === scope, layout = layoutFor(ctx2, doc, bitmap), image = layout && imageFor(ctx2, doc, bitmap, layout), undo = image && history2(ctx2, doc, bitmap, layout, image);
    const checkHistory = () => {
      if (JSON.stringify(imageFor(ctx2, doc, bitmap, layout).pixels) !== JSON.stringify(undo.current)) throw Error("Tiles changed in another editor. Start a fresh sprite stroke before undo or redo.");
    };
    ctx2.use({
      "sprite-assemble": () => {
        if (!current2()) return;
        const settings = { first: Number(read("sprite-first")), columns: Number(read("sprite-columns")), rows: Number(read("sprite-rows")), order: read("sprite-order"), ...mapSettings(read("sprite-map")) };
        makeAssembly(bitmap, settings);
        ctx2.setDraft("sprite-layout", JSON.stringify({ document_id: doc.document_id, bitmap_id: bitmap.id, ...settings }));
        ctx2.state.spriteHistory = null;
        return ctx2.render();
      },
      "sprite-undo": () => {
        if (!current2() || !undo) return;
        checkHistory();
        stage2(ctx2, doc, bitmap, layout, undo.undo());
        return ctx2.render();
      },
      "sprite-redo": () => {
        if (!current2() || !undo) return;
        checkHistory();
        stage2(ctx2, doc, bitmap, layout, undo.redo());
        return ctx2.render();
      },
      "sprite-export": () => {
        if (!current2()) return;
        const canvas = document.getElementById("sprite-canvas");
        if (!canvas) throw Error("Assemble a sprite first.");
        canvas.dispatchEvent(new Event("sprite-refresh"));
        const link = document.createElement("a");
        link.href = canvas.toDataURL("image/png");
        link.download = "sprite-preview.png";
        link.click();
      }
    });
    return `<section class="card sprite-assembly"><div class="card-heading"><h3>Sprite assembly</h3>${layout ? button("Save preview PNG", "sprite-export") : ""}</div><p class="subtle">Arrange declared tiles, then paint the whole image. Shared tiles update everywhere in this editing layout.</p><div class="field-row">${field("sprite-first", "First tile", ctx2.draft("sprite-first", (layout == null ? void 0 : layout.first) ?? 0), { type: "number", min: 0 })}${field("sprite-columns", "Tiles across", ctx2.draft("sprite-columns", (layout == null ? void 0 : layout.columns) ?? Math.min(2, bitmap.count)), { type: "number", min: 1, max: 8 })}${field("sprite-rows", "Tiles down", ctx2.draft("sprite-rows", (layout == null ? void 0 : layout.rows) ?? Math.min(2, Math.floor(bitmap.count / 2) || 1)), { type: "number", min: 1, max: 8 })}${select("sprite-order", "Tile order", [["rows", "Across, then down"], ["columns", "Down, then across"]], ctx2.draft("sprite-order", (layout == null ? void 0 : layout.order) || "rows"))}</div><details><summary>Custom tile placement</summary>${field("sprite-map", "Tile map", ctx2.draft("sprite-map", (layout == null ? void 0 : layout.indices) ? layout.indices.map((v, i) => v === null ? "." : String(v) + (layout.flips[i] & 1 ? "h" : "") + (layout.flips[i] & 2 ? "v" : "")).join(", ") : ""))}<p>One tile per grid position; use h/v for flips and . for an unmapped part.</p></details>${button("Assemble tiles", "sprite-assemble", { primary: !layout })}${image ? `${layout.provenance === "pixel_candidate" ? '<p class="notice warm">Gameplay pixel candidates. Source use still needs native verification.</p>' : ""}${layout.colors ? '<p class="subtle">Gameplay colors are a preview; palette bytes are unchanged.</p>' : ""}<div class="toolbar">${field("sprite-color", "Brush color index", ctx2.draft("sprite-color", "1"), { type: "number", min: 0 })}</div><div class="preview-pair sprite-comparison"><div><span>Original</span><div class="sprite-preview"><canvas id="sprite-original" aria-label="Original assembled sprite"></canvas></div></div><div><span>Editing · paint here</span><div class="sprite-preview"><canvas id="sprite-canvas" width="${image.width}" height="${image.height}" tabindex="0" role="application" aria-label="Assembled sprite editor: arrows move, Space paints"></canvas></div></div></div><p id="sprite-difference-count" class="preview-caption" role="status" aria-live="polite"></p><div class="actions">${button("Undo sprite stroke", "sprite-undo", { disabled: !undo.canUndo })}${button("Redo sprite stroke", "sprite-redo", { disabled: !undo.canRedo })}<span class="subtle">${image.width} × ${image.height} pixels · ${layout.tiles.length} tiles</span></div><p class="subtle">Drag across tile boundaries; review all changed tiles together with Review asset changes.</p><details><summary>Tile placement</summary><p>${layout.tiles.map((index, i) => esc(`(${i % layout.columns}, ${Math.floor(i / layout.columns)}) → tile ${index}`)).join(" · ")}</p><p>This source-bound layout is explicit. OAM, animation frames and game-specific metasprite tables still need their own declared mapping.</p></details>` : ""}</section>`;
  }
  function mountSprite(ctx2, doc, bitmap, palette2) {
    const canvas = document.getElementById("sprite-canvas"), layout = layoutFor(ctx2, doc, bitmap);
    if (!canvas || !layout) return;
    const scope = selectionKey(ctx2.state), current2 = () => selectionKey(ctx2.state) === scope;
    const image = imageFor(ctx2, doc, bitmap, layout), undo = history2(ctx2, doc, bitmap, layout, image);
    let pixels = [...image.pixels], pointer = null, cursor = { x: 0, y: 0 };
    const bits = { "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4, "tile8-packed4-low-v1": 4 }[bitmap.codec], count = Math.min(2 ** bits, (palette2 == null ? void 0 : palette2.colors_per_bank) || 256);
    const beforeCanvas = document.getElementById("sprite-original"), original = assemblePixels(bitmap, layout, (index) => bitmap.cells[index].pixels);
    const rgba = (values, colors) => {
      const data = new Uint8ClampedArray(values.length * 4);
      values.forEach((value, i) => {
        var _a, _b, _c;
        const part = Math.floor(Math.floor(i / image.width) / bitmap.height) * layout.columns + Math.floor(i % image.width / bitmap.width), observed = (_b = (_a = layout.colors) == null ? void 0 : _a[part]) == null ? void 0 : _b[value], color = (_c = colors == null ? void 0 : colors.entries.find((e) => e.index === value && e.bank === 0)) == null ? void 0 : _c.rgb, shade = Math.round(18 + value / Math.max(1, count - 1) * 216);
        data.set([(color == null ? void 0 : color.r) ?? (observed == null ? void 0 : observed[0]) ?? shade, (color == null ? void 0 : color.g) ?? (observed == null ? void 0 : observed[1]) ?? shade, (color == null ? void 0 : color.b) ?? (observed == null ? void 0 : observed[2]) ?? shade, 255], i * 4);
      });
      return data;
    };
    const originalPixels = rgba(original.pixels, palette2);
    if (beforeCanvas) {
      beforeCanvas.width = image.width;
      beforeCanvas.height = image.height;
      beforeCanvas.style.width = Math.min(320, image.width * 8) + "px";
      const c = beforeCanvas.getContext("2d"), frame = c.createImageData(image.width, image.height);
      frame.data.set(originalPixels);
      c.putImageData(frame, 0, 0);
    }
    const draw2 = () => {
      const context = canvas.getContext("2d"), frame = context.createImageData(image.width, image.height);
      frame.data.set(rgba(pixels, editorPalette(ctx2, palette2)));
      context.putImageData(frame, 0, 0);
      let changed2 = 0;
      for (let i = 0; i < frame.data.length; i += 4) if ([0, 1, 2].some((c) => frame.data[i + c] !== originalPixels[i + c])) changed2++;
      const n = document.getElementById("sprite-difference-count");
      if (n) n.textContent = changed2 ? "Preview updated · " + changed2 + " pixels differ · not built" : "Unchanged sprite preview";
    };
    const paint = (x, y) => {
      const color = Number(read("sprite-color"));
      if (!Number.isInteger(color) || color < 0 || color >= count) throw Error("Choose a palette index inside the declared color count.");
      paintAssemblyPixel(bitmap, layout, pixels, x, y, color);
      draw2();
    };
    const at = (event) => {
      const rect = canvas.getBoundingClientRect(), x = Math.floor((event.clientX - rect.left) / rect.width * image.width), y = Math.floor((event.clientY - rect.top) / rect.height * image.height);
      if (x >= 0 && y >= 0 && x < image.width && y < image.height) {
        cursor = { x, y };
        paint(x, y);
      }
    };
    const begin = () => {
      pixels = [...imageFor(ctx2, doc, bitmap, layout).pixels];
      undo.begin(pixels);
    };
    canvas.style.touchAction = "none";
    canvas.style.width = Math.min(320, image.width * 8) + "px";
    draw2();
    canvas.addEventListener("sprite-refresh", () => {
      if (current2() && pointer === null) {
        pixels = [...imageFor(ctx2, doc, bitmap, layout).pixels];
        draw2();
      }
    });
    canvas.addEventListener("pointerdown", (event) => {
      if (!current2() || event.button !== 0) return;
      event.preventDefault();
      canvas.focus();
      pointer = event.pointerId;
      canvas.setPointerCapture(pointer);
      ctx2.state.pending = null;
      ctx2.state.assetEditRevision = (ctx2.state.assetEditRevision || 0) + 1;
      begin();
      try {
        at(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointermove", (event) => {
      if (current2() && pointer === event.pointerId) try {
        at(event);
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointerup", async (event) => {
      if (!current2() || pointer !== event.pointerId) return;
      pointer = null;
      undo.commit(pixels);
      stage2(ctx2, doc, bitmap, layout, pixels);
      await ctx2.render();
    });
    canvas.addEventListener("pointercancel", () => {
      pointer = null;
      pixels = [...undo.current];
      draw2();
    });
    canvas.addEventListener("keydown", async (event) => {
      if (!current2() || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(event.key)) return;
      event.preventDefault();
      cursor.x = Math.max(0, Math.min(image.width - 1, cursor.x + (event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0)));
      cursor.y = Math.max(0, Math.min(image.height - 1, cursor.y + (event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0)));
      if (event.key === " ") try {
        begin();
        paint(cursor.x, cursor.y);
        undo.commit(pixels);
        stage2(ctx2, doc, bitmap, layout, pixels);
        await ctx2.render();
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    });
  }

  // romancer/ui/animation_studio.js
  var AnimationClock = class {
    constructor(timers = { set: (fn, ms) => setTimeout(fn, ms), clear: (id) => clearTimeout(id) }) {
      this.timers = timers;
      this.handle = null;
      this.generation = 0;
    }
    stop() {
      this.generation++;
      if (this.handle !== null) this.timers.clear(this.handle);
      this.handle = null;
    }
    start(frames, show, first = 0) {
      this.stop();
      if (!frames.length) return;
      const generation = this.generation;
      let index = first % frames.length;
      const tick = () => {
        this.handle = null;
        if (generation !== this.generation) return;
        show(index);
        if (generation !== this.generation) return;
        const delay = frames[index].duration;
        index = (index + 1) % frames.length;
        this.handle = this.timers.set(tick, delay);
      };
      tick();
    }
  };
  function readAnimation(doc, bitmap, encoded) {
    if (typeof encoded !== "string" || encoded.length > 256 * 1024) throw Error("Animation layout exceeds its budget.");
    const saved = JSON.parse(encoded);
    if ((saved == null ? void 0 : saved.document_id) !== doc.document_id || saved.bitmap_id !== bitmap.id) return [];
    if (!Array.isArray(saved.frames) || saved.frames.length > 32) throw Error("Use up to32 declared frames.");
    return saved.frames.map((f) => {
      if (!Number.isSafeInteger(f.duration) || f.duration < 40 || f.duration > 2e3) throw Error("Frame duration must be40–2000ms.");
      return { ...makeAssembly(bitmap, f), duration: f.duration };
    });
  }
  function animationStudio(ctx2, doc, bitmap) {
    if (!(doc == null ? void 0 : doc.ok) || !bitmap) return "";
    const { state: state2 } = ctx2, scope = selectionKey(state2), current2 = () => {
      var _a;
      return selectionKey(state2) === scope && ((_a = state2.results["assets.inspect"]) == null ? void 0 : _a.document_id) === doc.document_id;
    };
    let frames = [], error = "";
    try {
      frames = readAnimation(doc, bitmap, ctx2.draft("animation-frames", "null"));
    } catch (e) {
      error = e.message;
    }
    const save = (next) => {
      var _a;
      state2.animationPlaying = false;
      (_a = state2.animationClock) == null ? void 0 : _a.stop();
      ctx2.setDraft("animation-frames", JSON.stringify({ document_id: doc.document_id, bitmap_id: bitmap.id, frames: next }));
      return ctx2.render();
    };
    const selected2 = Math.max(0, Math.min(frames.length - 1, state2.animationIndex || 0));
    ctx2.use({
      "animation-add": () => {
        if (!current2()) return;
        const layout = JSON.parse(ctx2.draft("sprite-layout", "null"));
        if ((layout == null ? void 0 : layout.document_id) !== doc.document_id || layout.bitmap_id !== bitmap.id) throw Error("Assemble a sprite frame first.");
        if (frames.length >= 32) throw Error("Use up to32 frames.");
        const duration = Number(read("animation-duration")), next = [...frames, { ...makeAssembly(bitmap, layout), duration }];
        readAnimation(doc, bitmap, JSON.stringify({ document_id: doc.document_id, bitmap_id: bitmap.id, frames: next }));
        return save(next);
      },
      "animation-select": (node) => {
        state2.animationPlaying = false;
        state2.animationIndex = Number(node.dataset.id);
        return ctx2.render();
      },
      "animation-remove": () => save(frames.filter((_, i) => i !== selected2)),
      "animation-clear": () => save([]),
      "animation-play": () => {
        state2.animationPlaying = !state2.animationPlaying;
        return ctx2.render();
      },
      "animation-edit": () => {
        if (!current2() || !frames[selected2]) return;
        state2.animationPlaying = false;
        ctx2.setDraft("sprite-layout", JSON.stringify({ document_id: doc.document_id, bitmap_id: bitmap.id, ...frames[selected2] }));
        return ctx2.render();
      }
    });
    const shared = /* @__PURE__ */ new Map();
    frames.forEach((f, index) => new Set(f.tiles.filter((t) => t !== null)).forEach((t) => shared.set(t, /* @__PURE__ */ new Set([...shared.get(t) || [], index]))));
    const reused = [...shared].filter(([, uses]) => uses.size > 1);
    return `<details class="card"><summary>Animation frames</summary><p>Arrange each frame in Sprite assembly, then add it here. These explicit layouts do not identify the game's animation script.</p>${error ? `<p class="notice warm">${esc(error)}</p>${button("Discard invalid animation", "animation-clear")}` : ""}<div class="actions">${field("animation-duration", "Frame duration (ms)", ctx2.draft("animation-duration", "120"))}${button("Add assembled frame", "animation-add")}</div>${frames.length ? `<div class="actions">${frames.map((_, i) => button("Frame " + (i + 1), "animation-select", { id: String(i), primary: i === selected2 })).join("")}</div><div class="sprite-preview"><canvas id="animation-canvas" aria-label="Declared animation frame preview"></canvas></div><p id="animation-position">Frame ${selected2 + 1} of ${frames.length}</p><div class="actions">${button(state2.animationPlaying ? "Pause animation" : "Play animation", "animation-play", { primary: true })}${button("Edit selected frame", "animation-edit")}${button("Remove selected frame", "animation-remove")}</div><p>${reused.length} tiles are shared between frames; editing them changes every frame that uses them.</p>` : ""}</details>`;
  }
  function mountAnimation(ctx2, doc, bitmap, palette2) {
    const canvas = document.getElementById("animation-canvas");
    if (!canvas) return;
    const scope = selectionKey(ctx2.state), frames = readAnimation(doc, bitmap, ctx2.draft("animation-frames", "null"));
    const clock = ctx2.state.animationClock = new AnimationClock();
    const draw2 = (index) => {
      if (selectionKey(ctx2.state) !== scope || ctx2.state.page !== "assets") {
        clock.stop();
        return;
      }
      if (!frames[index]) return;
      const colors = editorPalette(ctx2, palette2), bits = { "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4, "tile8-packed4-low-v1": 4 }[bitmap.codec], count = Math.min(2 ** bits, (palette2 == null ? void 0 : palette2.colors_per_bank) || 256);
      const image = assemblePixels(bitmap, frames[index], (tile) => pixelBuffer(ctx2, doc, bitmap, tile));
      canvas.width = image.width;
      canvas.height = image.height;
      const c = canvas.getContext("2d"), pixels = c.createImageData(image.width, image.height);
      image.pixels.forEach((value, i) => {
        var _a, _b, _c;
        const part = Math.floor(Math.floor(i / image.width) / bitmap.height) * frames[index].columns + Math.floor(i % image.width / bitmap.width), observed = (_b = (_a = frames[index].colors) == null ? void 0 : _a[part]) == null ? void 0 : _b[value], color = (_c = colors == null ? void 0 : colors.entries.find((e) => e.index === value && e.bank === 0)) == null ? void 0 : _c.rgb, shade = Math.round(18 + value / Math.max(1, count - 1) * 216);
        pixels.data.set([(color == null ? void 0 : color.r) ?? (observed == null ? void 0 : observed[0]) ?? shade, (color == null ? void 0 : color.g) ?? (observed == null ? void 0 : observed[1]) ?? shade, (color == null ? void 0 : color.b) ?? (observed == null ? void 0 : observed[2]) ?? shade, 255], i * 4);
      });
      c.putImageData(pixels, 0, 0);
      canvas.style.width = Math.min(512, image.width * 4) + "px";
      canvas.style.maxWidth = "100%";
      canvas.style.imageRendering = "pixelated";
      ctx2.state.animationIndex = index;
      const label = document.getElementById("animation-position");
      if (label) label.textContent = `Frame ${index + 1} of ${frames.length}`;
    };
    canvas.addEventListener("animation-refresh", () => draw2(Math.min(frames.length - 1, ctx2.state.animationIndex || 0)));
    const first = Math.min(frames.length - 1, ctx2.state.animationIndex || 0);
    if (ctx2.state.animationPlaying) clock.start(frames, draw2, first);
    else draw2(first);
  }

  // romancer/ui/views/assets.js
  var codecBits = { "tile8-packed4-low-v1": 4, "mono-row-msb-v1": 1, "tile8-paired2-msb-v1": 2, "tile8-planar2-msb-v1": 2, "tile8-paired4-msb-v1": 4, "tile8-packed4-high-v1": 4 };
  function literalColorCount(bitmap, palette2) {
    const bits = codecBits[bitmap.codec];
    return bits ? Math.min(2 ** bits, (palette2 == null ? void 0 : palette2.colors_per_bank) || 2 ** bits) : 0;
  }
  function literalRGB(bitmap, value) {
    const count = literalColorCount(bitmap);
    const shade = Math.round(18 + value / Math.max(1, count - 1) * 216);
    return { r: shade, g: shade, b: shade };
  }
  async function render8(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n, _o;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    if (!state2.artifact) return empty("Import an asset resource", "A declared uncompressed codec and source revision are required.");
    const fallback = ((_a = state2.candidateReview) == null ? void 0 : _a.artifact_id) === state2.artifact.artifact_id ? {} : ((_b = state2.artifact.descriptors) == null ? void 0 : _b.assets) || ((_c = state2.project.descriptors) == null ? void 0 : _c.assets) || {};
    let document2 = ((_d = state2.candidateReview) == null ? void 0 : _d.artifact_id) === state2.artifact.artifact_id ? null : state2.results["assets.inspect"];
    if ((document2 == null ? void 0 : document2.source_sha256) !== state2.artifact.sha256) document2 = null;
    if (!document2 && ((_e = fallback.source) == null ? void 0 : _e.sha256) === state2.artifact.sha256) {
      document2 = await ctx2.api.call("assets.inspect", { ...ctx2.sourceParams(), schema: fallback });
      state2.results["assets.inspect"] = document2;
    }
    const key3 = document2 == null ? void 0 : document2.document_id;
    if (((_f = state2.paint) == null ? void 0 : _f.document_id) !== key3) state2.paint = null;
    if ((document2 == null ? void 0 : document2.ok) && !state2.paint) {
      try {
        const saved = JSON.parse(ctx2.draft("paint-buffer", "null")), savedBitmap = document2.bitmaps.find((b) => b.id === (saved == null ? void 0 : saved.bitmap_id));
        if ((saved == null ? void 0 : saved.document_id) === key3 && (savedBitmap == null ? void 0 : savedBitmap.cells[saved.cell_index]) && Array.isArray(saved.pixels) && saved.pixels.length === savedBitmap.width * savedBitmap.height) {
          state2.paint = saved;
          state2.assetBitmapId = saved.bitmap_id;
        }
      } catch {
      }
    }
    const bitmap = ((_g = document2 == null ? void 0 : document2.bitmaps) == null ? void 0 : _g.find((b) => b.id === state2.assetBitmapId)) || ((_h = document2 == null ? void 0 : document2.bitmaps) == null ? void 0 : _h[0]), palette2 = (_i = document2 == null ? void 0 : document2.palettes) == null ? void 0 : _i.find((p) => p.id === (bitmap == null ? void 0 : bitmap.palette_id));
    state2.assetPage = Math.min(Math.max(0, Number.isSafeInteger(state2.assetPage) ? state2.assetPage : 0), Math.max(0, Math.ceil(((bitmap == null ? void 0 : bitmap.count) || 0) / 64) - 1));
    const selected2 = ((_j = state2.paint) == null ? void 0 : _j.cell_index) ?? 0;
    const request2 = () => {
      if (!(document2 == null ? void 0 : document2.ok)) throw new Error("Inspect a valid asset descriptor first.");
      const changes = mergeCellChanges(json("asset-changes"), state2.paint ? [{ kind: "cell", bitmap_id: bitmap.id, cell_index: selected2, before_pixels: bitmap.cells[selected2].pixels, after_pixels: state2.paint.pixels }] : []);
      return { schema_version: 1, document_id: document2.document_id, changes, acknowledged_consumers: state2.assetAcknowledgements || [] };
    };
    ctx2.use({
      "asset-inspect": async () => {
        state2.assetAcknowledgements = [];
        state2.paint = null;
        await ctx2.run("assets.inspect", { ...ctx2.sourceParams(), schema: json("asset-schema") });
      },
      "asset-select-cell": (node) => {
        activateCell(ctx2, document2, bitmap.id, Number(node.dataset.id));
        return ctx2.render();
      },
      "asset-paint": (node, event) => {
        if (!bitmap) throw new Error("Select a decoded tile first.");
        const rect = node.getBoundingClientRect(), x = Math.floor((event.clientX - rect.left) / rect.width * bitmap.width), y = Math.floor((event.clientY - rect.top) / rect.height * bitmap.height);
        const color = Number(read("paint-color"));
        if (!Number.isInteger(color) || color < 0 || color >= literalColorCount(bitmap, palette2)) throw new Error("Select a palette index within the declared color count.");
        if (!state2.paint) state2.paint = { document_id: key3, bitmap_id: bitmap.id, cell_index: selected2, pixels: [...bitmap.cells[selected2].pixels] };
        state2.paint.pixels[y * bitmap.width + x] = color;
        state2.assetAcknowledgements = [];
        state2.pending = null;
        ctx2.setDraft("paint-buffer", JSON.stringify(state2.paint));
        drawPaint(ctx2, document2);
      },
      "asset-plan": async () => {
        var _a2;
        const signature = JSON.stringify({ schema: json("asset-schema"), edits: request2() }), generation = state2.assetEditRevision || 0;
        const result = await ctx2.run("assets.plan", { ...ctx2.sourceParams(), ...JSON.parse(signature) }, { render: false });
        if (((_a2 = state2.results["assets.inspect"]) == null ? void 0 : _a2.document_id) !== key3 || (state2.assetEditRevision || 0) !== generation || JSON.stringify({ schema: json("asset-schema"), edits: request2() }) !== signature) {
          ctx2.notify("Graphics changed during review. Review them again.");
          return;
        }
        state2.pending = { kind: "assets", plan_id: result.workbench_plan_id, artifact_id: state2.artifact.artifact_id, document_id: key3, signature };
        await ctx2.render();
      },
      "asset-acknowledge": async () => {
        var _a2;
        const required = (_a2 = state2.results["assets.plan"]) == null ? void 0 : _a2.required_consumers;
        if (!required) throw new Error("Review the affected consumers first.");
        state2.assetAcknowledgements = required;
        ctx2.notify("Declared consumers acknowledged. Review the plan again.");
        await ctx2.render();
      },
      "asset-apply": async () => {
        var _a2;
        const reviewed = state2.pending;
        if ((reviewed == null ? void 0 : reviewed.kind) !== "assets" || reviewed.artifact_id !== state2.artifact.artifact_id || reviewed.document_id !== key3 || ((_a2 = state2.results["assets.inspect"]) == null ? void 0 : _a2.document_id) !== key3 || reviewed.signature !== JSON.stringify({ schema: json("asset-schema"), edits: request2() })) throw Error("Review the current graphics changes first.");
        await ctx2.run("structured.apply", { ...ctx2.projectParams(), plan_id: reviewed.plan_id }, { render: false });
        if (state2.pending !== reviewed || reviewed.signature !== JSON.stringify({ schema: json("asset-schema"), edits: request2() })) {
          ctx2.notify("Build created. Your newer graphics edits are still staged.");
          return;
        }
        state2.pending = null;
        state2.paint = null;
        ctx2.setDraft("paint-buffer", "");
        ctx2.setDraft("asset-changes", "[]");
        state2.assetAcknowledgements = [];
        await ctx2.render();
        ctx2.notify("Build created.");
      },
      "asset-palette-load": () => {
        var _a2;
        const entry = (_a2 = editorPalette(ctx2, palette2)) == null ? void 0 : _a2.entries[Number(read("palette-index"))];
        if (!entry) throw new Error("Choose an existing palette entry.");
        for (const channel of ["r", "g", "b"]) ctx2.setDraft("palette-" + channel, String(entry.components[channel]));
        return ctx2.render();
      },
      "asset-palette-change": () => {
        if (!palette2) throw new Error("This descriptor has no palette.");
        const index = Number(read("palette-index")), entry = palette2.entries[index];
        if (!entry) throw new Error("Choose an existing palette entry.");
        const changes = json("asset-changes").filter((c) => !(c.kind === "palette" && c.palette_id === palette2.id && c.index === entry.index && c.bank === entry.bank));
        changes.push({ kind: "palette", palette_id: palette2.id, bank: entry.bank, index: entry.index, before: entry.components, after: { r: Number(read("palette-r")), g: Number(read("palette-g")), b: Number(read("palette-b")) } });
        ctx2.setDraft("asset-changes", JSON.stringify(changes, null, 2));
        state2.pending = null;
        state2.assetAcknowledgements = [];
        ctx2.notify("Palette change added.");
        return ctx2.render();
      },
      "asset-discard": () => {
        state2.pixelHistoryScope = null;
        ctx2.setDraft("paint-buffer", "");
        ctx2.setDraft("asset-changes", "[]");
        state2.paint = null;
        state2.pending = null;
        state2.assetAcknowledgements = [];
        delete state2.results["assets.plan"];
        ctx2.render();
      }
    });
    if (((_k = state2.candidateReview) == null ? void 0 : _k.artifact_id) === state2.artifact.artifact_id) return `${heading("", "Confirm graphics candidate", "")}<section class="card"><p>${esc(state2.candidateReview.reason)}</p><p>Confirm the format and allocation, then load the declaration.</p>${graphicsDeclaration(ctx2)}${button("Cancel candidate", "candidate-cancel")}</section>`;
    const pending = ((_l = state2.pending) == null ? void 0 : _l.kind) === "assets" && state2.pending.artifact_id === state2.artifact.artifact_id;
    return `${heading("Asset workshop", "Graphics & fonts", "Inspect declared tiles, palettes, maps, and fonts. Shared consumers require explicit acknowledgment.")}<div class="identity"><strong>${esc(state2.artifact.name)}</strong><code>${short(state2.artifact.sha256)}</code>${badge((document2 == null ? void 0 : document2.write_supported) ? "Editable" : "Declaration needed", (document2 == null ? void 0 : document2.write_supported) ? "good" : "warm")}</div><div class="grid-two asset-workspace"><div class="asset-editors">${spriteAssembly(ctx2, document2, bitmap)}${animationStudio(ctx2, document2, bitmap)}${paletteEditor(ctx2, palette2)}${assetTools(ctx2, document2, bitmap, palette2)}<section class="card asset-collection"><div class="card-heading"><h3>Tile collection</h3><span class="subtle">${(bitmap == null ? void 0 : bitmap.count) || 0} cells · ${esc((bitmap == null ? void 0 : bitmap.codec) || "No codec loaded")}</span></div>${bitmap ? `<div class="pixel-grid">${bitmap.cells.slice((state2.assetPage || 0) * 64, (state2.assetPage || 0) * 64 + 64).map((cell) => `<div class="pixel-card"><canvas width="${bitmap.width}" height="${bitmap.height}" data-cell="${cell.index}" aria-label="Tile ${cell.index}"></canvas>${button("Edit tile " + cell.index, "asset-select-cell", { id: String(cell.index) })}</div>`).join("")}</div>` : empty("Load a declared asset descriptor", "Unknown compression and codecs remain read only.")}<div class="actions">${button("Previous page", "asset-page", { id: "-1", disabled: !(state2.assetPage > 0) })}${button("Next page", "asset-page", { id: "1", disabled: !bitmap || (state2.assetPage || 0) * 64 + 64 >= bitmap.count })}</div><div class="swatches" aria-label="Declared palette colors">${(palette2 == null ? void 0 : palette2.entries.slice(0, 64).map((entry, i) => `<span class="swatch" data-color-index="${i}" title="Color ${entry.index} (${entry.components.r}, ${entry.components.g}, ${entry.components.b})"></span>`).join("")) || ""}</div></section>${bitmap ? `<section class="card asset-pixel-editor"><div class="card-heading"><h3>Pixel editor · cell ${selected2}</h3><span id="pixel-edit-status">${JSON.stringify(pixelBuffer(ctx2, document2, bitmap, selected2)) !== JSON.stringify(bitmap.cells[selected2].pixels) ? badge("Staged", "warm") : badge("Unchanged")}</span></div><div class="preview-pair pixel-comparison"><div><span>Original tile</span><div class="pixel-card"><canvas id="paint-original" aria-label="Original selected tile"></canvas></div></div><div><span>Editing · paint here</span><div class="pixel-card"><canvas id="paint-canvas" width="${bitmap.width}" height="${bitmap.height}" tabindex="0" role="img" aria-label="Pixel editor: arrows move; Space paints selected index"></canvas><small>Drag to paint. Undo restores a complete stroke.</small></div></div></div><p id="pixel-preview-status" class="preview-caption" role="status" aria-live="polite"></p><div>${field("paint-color", "Palette index", ctx2.draft("paint-color", "1"), { type: "number", min: 0 })}<p class="subtle small">Grayscale shows stored indices when no palette is declared.</p>${button("Discard pending pixels", "asset-discard")}</div></section>` : ""}</div><section class="card"><h3>Graphics setup</h3>${graphicsDeclaration(ctx2)}${jsonEditor("asset-schema", "Advanced asset schema", ctx2.draft("asset-schema", JSON.stringify(fallback, null, 2)), false)}${button("Inspect assets", "asset-inspect", { icon: "assets" })}${jsonEditor("asset-changes", "Additional cell / palette / map / advance changes", ctx2.draft("asset-changes", "[]"), false)}<div class="actions">${button("Review asset changes", "asset-plan", { primary: !pending, disabled: !(document2 == null ? void 0 : document2.write_supported) })}${pending ? button("Create asset build", "asset-apply", { primary: true, icon: "check" }) : ""}</div>${((_n = (_m = state2.results["assets.plan"]) == null ? void 0 : _m.required_consumers) == null ? void 0 : _n.length) && !((_o = state2.results["assets.plan"]) == null ? void 0 : _o.ok) ? `<div class="notice warm">${state2.results["assets.plan"].required_consumers.length} declared consumers are affected. Read the report below before acknowledging them.</div>${button("Acknowledge listed consumers", "asset-acknowledge")}` : ""}</section></div>${report(state2.results["assets.plan"], "Asset plan & affected consumers")}${report(state2.results["structured.apply"], "Structured build")}`;
  }
  function documentNode(id) {
    return document.getElementById(id);
  }
  function draw(canvas, bitmap, pixels, palette2) {
    const context = canvas.getContext("2d"), image = context.createImageData(bitmap.width, bitmap.height);
    pixels.forEach((value, index) => {
      var _a;
      const color = ((_a = palette2 == null ? void 0 : palette2.entries[value]) == null ? void 0 : _a.rgb) || literalRGB(bitmap, value);
      image.data.set([color.r, color.g, color.b, 255], index * 4);
    });
    context.putImageData(image, 0, 0);
  }
  function drawPaint(ctx2, doc) {
    var _a, _b, _c, _d;
    const bitmap = doc.bitmaps.find((b) => b.id === ctx2.state.assetBitmapId) || doc.bitmaps[0], original = doc.palettes.find((p) => p.id === bitmap.palette_id), palette2 = editorPalette(ctx2, original), canvas = documentNode("paint-canvas"), before = documentNode("paint-original");
    const index = ((_a = ctx2.state.paint) == null ? void 0 : _a.cell_index) ?? 0, pixels = pixelBuffer(ctx2, doc, bitmap, index), status = documentNode("pixel-edit-status");
    if (status) status.innerHTML = JSON.stringify(pixels) !== JSON.stringify(bitmap.cells[index].pixels) ? badge("Staged", "warm") : badge("Unchanged");
    if (canvas) draw(canvas, bitmap, pixels, palette2);
    if (before) {
      before.width = bitmap.width;
      before.height = bitmap.height;
      draw(before, bitmap, bitmap.cells[index].pixels, original);
    }
    const notice = documentNode("pixel-preview-status");
    if (notice) notice.textContent = "Live editing preview · " + pixels.filter((v, i) => v !== bitmap.cells[index].pixels[i]).length + " stored pixels changed · review and build to save.";
    (_b = documentNode("sprite-canvas")) == null ? void 0 : _b.dispatchEvent(new Event("sprite-refresh"));
    (_c = documentNode("animation-canvas")) == null ? void 0 : _c.dispatchEvent(new Event("animation-refresh"));
    (_d = documentNode("map-preview")) == null ? void 0 : _d.dispatchEvent(new Event("map-refresh"));
  }
  function mount5(ctx2) {
    const doc = ctx2.state.results["assets.inspect"];
    if (!(doc == null ? void 0 : doc.ok)) return;
    const bitmap = doc.bitmaps.find((b) => b.id === ctx2.state.assetBitmapId) || doc.bitmaps[0], palette2 = doc.palettes.find((p) => p.id === bitmap.palette_id);
    const refresh = () => {
      const colors = editorPalette(ctx2, palette2);
      document.querySelectorAll("canvas[data-cell]").forEach((canvas) => {
        const index = Number(canvas.dataset.cell);
        draw(canvas, bitmap, pixelBuffer(ctx2, doc, bitmap, index), colors);
      });
      document.querySelectorAll("[data-color-index]").forEach((node) => {
        const c = colors.entries[Number(node.dataset.colorIndex)].rgb;
        node.style.backgroundColor = `rgb(${c.r},${c.g},${c.b})`;
      });
      drawPaint(ctx2, doc);
    };
    refresh();
    mountTools(ctx2, doc, bitmap, () => drawPaint(ctx2, doc));
    mountSprite(ctx2, doc, bitmap, palette2);
    mountAnimation(ctx2, doc, bitmap, palette2);
    mountPaletteEditor(ctx2, doc, palette2, refresh);
  }

  // romancer/ui/views/playtest.js
  var playtest_exports = {};
  __export(playtest_exports, {
    mount: () => mount6,
    render: () => render9
  });

  // romancer/ui/visual_controls.js
  function selectedRegion(rect, start, end, width, height) {
    const pixel = (p) => ({ x: Math.max(0, Math.min(width - 1, Math.floor((p.x - rect.left) / rect.width * width))), y: Math.max(0, Math.min(height - 1, Math.floor((p.y - rect.top) / rect.height * height))) }), a = pixel(start), b = pixel(end), region = { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x) + 1, height: Math.abs(a.y - b.y) + 1 };
    if (!Number.isFinite(rect.width) || !Number.isFinite(rect.height) || rect.width <= 0 || rect.height <= 0 || region.width > 256 || region.height > 256) throw Error("Choose a region no larger than 256 × 256 pixels.");
    return region;
  }
  function checkpointControls(ctx2) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2, ticket = selectionKey(state2), frame = state2.frame, recording = ((_a = state2.recordingRoute) == null ? void 0 : _a.status) === "RECORDING" && ((_b = state2.recordingRoute.selection) == null ? void 0 : _b.id) === ((_c = state2.artifact) == null ? void 0 : _c.artifact_id);
    const saved = ((_d = state2.visualRegion) == null ? void 0 : _d.scope) === ticket && state2.visualRegion.frame_sha256 === (frame == null ? void 0 : frame.sha256) ? state2.visualRegion.region : null;
    ctx2.use({
      "visual-checkpoint": async () => {
        var _a2;
        stopPlayback(state2);
        const selected2 = state2.visualRegion;
        if (!selected2 || selected2.scope !== selectionKey(state2) || selected2.frame_sha256 !== ((_a2 = state2.frame) == null ? void 0 : _a2.sha256)) throw Error("Pause, capture a frame and select the region again.");
        const params = ctx2.projectParams(), result = await ctx2.run("routes.record_region", { ...params, region: selected2.region, frame_sha256: selected2.frame_sha256 }, { render: false, refresh: false });
        if (ticket !== selectionKey(state2)) return;
        state2.lastVisualCheckpoint = result;
        ctx2.notify("Screenshot checkpoint added to the last recorded input step.");
        await ctx2.render();
      },
      "visual-capture": async () => {
        stopPlayback(state2);
        const result = await ctx2.run("runtime.capture", ctx2.projectParams(), { render: false, refresh: false });
        if (ticket !== selectionKey(state2)) return;
        state2.frame = result;
        state2.visualRegion = null;
        await ctx2.render();
      },
      "visual-region-set": () => {
        if (!frame) throw Error("Capture a frame first.");
        const region = Object.fromEntries(["x", "y", "width", "height"].map((k) => [k, Number(read("visual-" + k))]));
        if (Object.values(region).some((n) => !Number.isInteger(n)) || region.x < 0 || region.y < 0 || region.width < 1 || region.height < 1 || region.width > 256 || region.height > 256 || region.x + region.width > frame.width || region.y + region.height > frame.height) throw Error("Select a valid region inside this frame, up to 256 × 256 pixels.");
        state2.visualRegion = { scope: ticket, frame_sha256: frame.sha256, region };
        return ctx2.render();
      }
    });
    return `<details class="card" id="visual-checkpoints" ${recording || state2.graphicsRegionOpen ? "open" : ""}><summary>Frame region & screenshot checkpoints</summary><p>Pause and select a sprite or region for graphics investigation. Recorded routes can also compare that region on replay.</p><div class="actions">${button("Record inputs in Routes", "navigate", { id: "routes" })}${button("Pause & capture frame", "visual-capture", { disabled: !state2.runtime })}</div>
 ${frame ? `<div class="hex-scroll"><canvas id="visual-region-canvas" tabindex="0" aria-label="Drag to select a screenshot checkpoint region"></canvas></div><p id="visual-region-label">${saved ? `Region ${saved.x}, ${saved.y} · ${saved.width} × ${saved.height}` : "Drag a rectangle over the measured screenshot."}</p><details><summary>Enter region coordinates</summary><div class="field-row">${["x", "y", "width", "height"].map((k) => field("visual-" + k, k[0].toUpperCase() + k.slice(1), (saved == null ? void 0 : saved[k]) ?? (k === "width" ? Math.min(256, frame.width) : k === "height" ? Math.min(256, frame.height) : 0), { type: "number", min: k === "x" || k === "y" ? 0 : 1 })).join("")}</div>${button("Select region", "visual-region-set")}</details>${button("Add screenshot checkpoint", "visual-checkpoint", { primary: true, disabled: !recording || !saved || state2.playing })}` : "<p>Load a game and advance to its first measured frame.</p>"}
 ${recording ? '<p class="subtle">Checkpoint attaches to the most recent recorded input. Stop and save the route when finished.</p>' : '<p class="subtle">Start a route recording before adding a checkpoint.</p>'}</details>`;
  }
  function mountCheckpoint(ctx2) {
    var _a;
    const canvas = document.getElementById("visual-region-canvas"), frame = ctx2.state.frame;
    if (!canvas || !frame) return;
    canvas.width = frame.width;
    canvas.height = frame.height;
    canvas.style.width = Math.min(640, frame.width * 2) + "px";
    canvas.style.imageRendering = "pixelated";
    canvas.style.touchAction = "none";
    const raw = Uint8Array.from(atob(frame.rgb24_base64), (c) => c.charCodeAt(0)), context = canvas.getContext("2d"), image = context.createImageData(frame.width, frame.height);
    for (let i = 0; i < frame.width * frame.height; i++) image.data.set([raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2], 255], i * 4);
    const draw2 = (region) => {
      context.putImageData(image, 0, 0);
      if (region) {
        context.strokeStyle = "#76d9c3";
        context.lineWidth = 1;
        context.strokeRect(region.x + 0.5, region.y + 0.5, region.width - 1, region.height - 1);
      }
    };
    draw2(((_a = ctx2.state.visualRegion) == null ? void 0 : _a.frame_sha256) === frame.sha256 ? ctx2.state.visualRegion.region : null);
    let start = null, pointer = null, last = null;
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      stopPlayback(ctx2.state);
      start = { x: event.clientX, y: event.clientY };
      pointer = event.pointerId;
      canvas.setPointerCapture(pointer);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (event.pointerId !== pointer) return;
      try {
        last = selectedRegion(canvas.getBoundingClientRect(), start, { x: event.clientX, y: event.clientY }, frame.width, frame.height);
        draw2(last);
        document.getElementById("visual-region-label").textContent = `Region ${last.x}, ${last.y} · ${last.width} × ${last.height}`;
      } catch (error) {
        last = null;
        document.getElementById("visual-region-label").textContent = error.message;
      }
    });
    const finish = async (event) => {
      if (event.pointerId !== pointer) return;
      pointer = null;
      try {
        last = selectedRegion(canvas.getBoundingClientRect(), start, { x: event.clientX, y: event.clientY }, frame.width, frame.height);
        ctx2.state.visualRegion = { scope: selectionKey(ctx2.state), frame_sha256: frame.sha256, region: last };
        await ctx2.render();
      } catch (error) {
        ctx2.notify(error.message, true);
      }
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", () => {
      pointer = null;
      draw2(null);
    });
  }
  function visualFailures(evidence2) {
    if (!evidence2) return "";
    const report2 = evidence2.report || evidence2, trusted = evidence2.runtime_trusted === true && evidence2.authentication === "current_application" || evidence2.runtime_trusted !== false && report2.origin === "owned_native_worker" && report2.worker_close_acknowledged === true && report2.worker_exit_code === 0 && !!report2.evidence_id, trustLabel = evidence2.runtime_trusted === false ? "Historical imported report" : trusted ? "Current local execution" : "Unverified report", rows = (report2.observations || []).filter((o) => o.kind === "frame_region" && !o.pass);
    if (!rows.length) return "";
    return `<section class="card"><h3>Screenshot differences</h3><p>${badge(trustLabel, trusted ? "good" : "neutral")} ${esc(evidence2.evidence_id || report2.evidence_id || "")}</p>${rows.map((r) => `<p>Step ${r.step + 1} · region ${r.region.x}, ${r.region.y} · ${r.region.width} × ${r.region.height} · ${r.changed_pixels ?? "Unknown"} changed pixels${r.reason ? " · " + esc(r.reason) : ""}</p>${r.visual ? `<div class="visual-comparison">${[["expected_png_base64", "Expected"], ["actual_png_base64", "Actual"], ["difference_png_base64", "Difference"]].map(([key3, label]) => `<figure><figcaption>${label}</figcaption><img src="data:image/png;base64,${esc(r.visual[key3])}" alt="${label} screenshot region" loading="lazy"></figure>`).join("")}</div>` : ""}<details><summary>Measured frame identity</summary><code>${esc(r.actual_frame_sha256)}</code></details>`).join("")}</section>`;
  }
  async function suitePictures(ctx2, suite) {
    var _a;
    if ((suite == null ? void 0 : suite.project_id) !== ((_a = ctx2.state.project) == null ? void 0 : _a.project_id)) return "";
    const ids = suite.tests.filter((t) => t.status !== "PASS").flatMap((t) => [t.baseline_id, t.candidate_id]).filter(Boolean).slice(0, 8), pictures = [];
    for (const evidence_id of ids) {
      try {
        const record = await ctx2.api.call("reports.get", { ...ctx2.projectParams(), evidence_id });
        pictures.push(visualFailures(record));
      } catch {
        pictures.push("<p>A stored screenshot report is unavailable. Run this test again.</p>");
      }
    }
    return pictures.join("");
  }

  // romancer/ui/save_manager.js
  function saveManager(ctx2, listing) {
    var _a, _b;
    const { state: state2 } = ctx2, ticket = selectionKey(state2), active = ((_a = state2.runtime) == null ? void 0 : _a.artifact_id) === ((_b = state2.artifact) == null ? void 0 : _b.artifact_id), current2 = () => selectionKey(state2) === ticket;
    ctx2.use({
      "save-capture": async () => {
        stopPlayback(state2);
        await ctx2.run("saves.capture", { ...ctx2.sourceParams(), name: read("save-name") }, { render: false });
        if (current2()) {
          ctx2.notify("Battery save backed up.");
          await ctx2.render();
        }
      },
      "save-import": async () => {
        stopPlayback(state2);
        const file = document.getElementById("save-file").files[0], name = read("save-name"), params = ctx2.sourceParams();
        if (!file) throw Error("Choose a raw .sav or .srm file first.");
        const input = await ctx2.api.uploadInput(params.project_id, file, "save");
        if (!current2()) throw Error("The ROM changed. Import for the selected ROM again.");
        await ctx2.run("saves.import", { ...params, input_id: input.input_id, name }, { render: false });
        if (current2()) {
          ctx2.notify("Save imported. Restart explicitly to use it.");
          await ctx2.render();
        }
      },
      "save-export": async () => {
        const params = ctx2.sourceParams(), result = await ctx2.run("saves.export", { ...params, save_id: read("save-choice") }, { render: false });
        if (current2()) await ctx2.api.download(params.project_id, result.export.export_id, "battery-save.sav");
      },
      "save-restore": async () => {
        stopPlayback(state2);
        const params = ctx2.sourceParams();
        try {
          const result = await ctx2.run("saves.restore", { ...params, save_id: read("save-choice") }, { render: false, refresh: false });
          if (!current2()) return;
          state2.runtime = result.runtime;
          state2.frame = null;
          ctx2.notify("Restarted with selected save. Previous RAM is in an automatic backup.");
        } catch (error) {
          const status = await ctx2.api.call("runtime.status", { project_id: params.project_id }).catch(() => null);
          if (current2() && (status == null ? void 0 : status.active) === false) {
            state2.runtime = null;
            state2.frame = null;
          }
          throw error;
        } finally {
          if (current2()) await ctx2.render();
        }
      }
    });
    const saves = listing.saves;
    return `<section class="card"><h3>Battery saves</h3><p>Raw game saves, separate from emulator save states.</p>${active ? "" : '<p class="notice">Load the selected ROM before importing, capturing or restoring a save.</p>'}
 ${field("save-name", "Save name", ctx2.draft("save-name", "My progress"))}${fileInput("save-file", "Raw save file", ".sav,.srm")}<div class="actions">${button("Back up current save", "save-capture", { disabled: !active })}${button("Import save", "save-import", { disabled: !active })}</div>
 ${saves.length ? `${select("save-choice", "Saved progress", saves.map((r) => [r.save_id, `${r.name} · ${size(r.size)}${r.origin === "automatic_backup" ? " · automatic backup" : ""}`]), ctx2.draft("save-choice", saves.at(-1).save_id))}<div class="actions">${button("Download selected save", "save-export")}${button("Restart with selected save", "save-restore", { disabled: !active })}</div><p class="subtle">Restart makes an automatic backup first. Matching ROM, core, setup and save size are required.</p>` : '<p class="subtle">No battery saves captured for this exact ROM revision yet.</p>'}
 ${listing.truncated ? "<p>Only the first 512 session records were inspected. Keep a private backup of older sessions.</p>" : ""}<details><summary>Supported save format</summary><p>Raw exposed cartridge save RAM, up to 8 MiB, with the exact size reported by the loaded core. Wrapped saves and save states need their original tool to export a raw save. Capturing RAM does not prove an in-game save event.</p></details></section>`;
  }

  // romancer/ui/audio_live.js
  function decodePCM(packet) {
    if ((packet == null ? void 0 : packet.format) !== "s16le" || packet.channels !== 2 || packet.complete !== true || packet.dropped_frames || packet.invalid_batches || !Number.isFinite(packet.sample_rate) || packet.sample_rate < 8e3 || packet.sample_rate > 192e3 || !Number.isSafeInteger(packet.captured_frames) || packet.captured_frames < 0 || packet.captured_frames > 48e3) throw new Error("Audio packet is incomplete or outside playback limits.");
    const encoded = packet.pcm_s16le_base64;
    if (typeof encoded !== "string" || encoded.length > 256e3 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) throw new Error("Invalid PCM encoding.");
    const raw = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    if (raw.length !== packet.captured_frames * 4) throw new Error("Audio sample count differs from the packet.");
    const view = new DataView(raw.buffer), left = new Float32Array(packet.captured_frames), right = new Float32Array(packet.captured_frames);
    for (let i = 0; i < left.length; i++) {
      left[i] = view.getInt16(i * 4, true) / 32768;
      right[i] = view.getInt16(i * 4 + 2, true) / 32768;
    }
    return { left, right, rate: packet.sample_rate, duration: left.length / packet.sample_rate };
  }
  function soundCheckPacket() {
    const count = 1e3, raw = new Uint8Array(count * 4), view = new DataView(raw.buffer);
    for (let i = 0; i < count; i++) {
      const sample = Math.round(Math.sin(i * 2 * Math.PI * 440 / 8e3) * 6e3);
      view.setInt16(i * 4, sample, true);
      view.setInt16(i * 4 + 2, sample, true);
    }
    return { format: "s16le", channels: 2, sample_rate: 8e3, captured_frames: count, complete: true, dropped_frames: 0, invalid_batches: 0, pcm_s16le_base64: btoa(String.fromCharCode(...raw)) };
  }
  var LiveAudio = class {
    constructor(factory = () => new AudioContext()) {
      this.factory = factory;
      this.ticket = 0;
      this.nodes = /* @__PURE__ */ new Set();
      this.volume = 1;
      this.muted = false;
      this.active = false;
    }
    async start() {
      this.stop();
      const ticket = this.ticket;
      try {
        this.context = this.factory();
        this.gain = this.context.createGain();
        this.gain.connect(this.context.destination);
        this.setVolume(this.volume, this.muted);
        await this.context.resume();
        if (ticket !== this.ticket) return;
        this.active = true;
        this.next = this.context.currentTime;
      } catch (error) {
        if (ticket === this.ticket) this.stop();
        throw error;
      }
    }
    get queuedSeconds() {
      return this.active ? Math.max(0, this.next - this.context.currentTime) : 0;
    }
    setVolume(value, muted = this.muted) {
      if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error("Volume must be between0 and1.");
      this.volume = value;
      this.muted = muted;
      if (this.gain) this.gain.gain.value = muted ? 0 : value;
    }
    enqueue(packet, ticket) {
      if (!this.active || ticket !== this.ticket) return false;
      const decoded = decodePCM(packet);
      if (!decoded.left.length) return false;
      if (decoded.duration > 0.25) throw new Error("Audio packet exceeds250ms.");
      const start = Math.max(this.context.currentTime + 0.01, this.next);
      if (start + decoded.duration - this.context.currentTime > 0.25) return false;
      const buffer = this.context.createBuffer(2, decoded.left.length, decoded.rate);
      buffer.copyToChannel(decoded.left, 0);
      buffer.copyToChannel(decoded.right, 1);
      const node = this.context.createBufferSource();
      node.buffer = buffer;
      node.connect(this.gain);
      this.nodes.add(node);
      node.onended = () => {
        this.nodes.delete(node);
        node.disconnect();
      };
      node.start(start);
      this.next = start + decoded.duration;
      return true;
    }
    stop() {
      this.ticket++;
      this.active = false;
      for (const node of this.nodes) {
        try {
          node.stop();
          node.disconnect();
        } catch {
        }
      }
      this.nodes.clear();
      if (this.gain) {
        this.gain.disconnect();
        this.gain = null;
      }
      if (this.context) {
        this.context.close().catch(() => {
        });
        this.context = null;
      }
      this.next = 0;
    }
  };

  // romancer/ui/views/playtest.js
  async function render9(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y;
    const { state: state2 } = ctx2;
    state2.liveMuted ??= getSettings().startMuted;
    const missing = requireProject(ctx2);
    if (missing) return missing;
    if (!state2.artifact && !((_a = state2.project.containers) == null ? void 0 : _a.length)) return empty("Import a game to playtest", "Choose a native libretro core that supports your source.");
    const saveListing = state2.artifact ? await ctx2.api.call("saves.list", ctx2.sourceParams()) : { saves: [] };
    const setup2 = await runtimeSetup(ctx2), contentSha = ((_b = state2.runtime) == null ? void 0 : _b.game_sha256) || ((_c = state2.artifact) == null ? void 0 : _c.sha256), coreSha = ((_d = state2.runtime) == null ? void 0 : _d.core_sha256) || ((_f = (_e = state2.profile) == null ? void 0 : _e.core_identity) == null ? void 0 : _f.sha256), setupSha = ((_g = state2.runtime) == null ? void 0 : _g.runtime_identity_sha256) || ((_i = (_h = state2.runtime) == null ? void 0 : _h.loaded) == null ? void 0 : _i.runtime_identity_sha256), checkpoints = (await ctx2.api.call("runtime.checkpoints", ctx2.projectParams())).checkpoints.filter((c) => (!contentSha || c.game_sha256 === contentSha) && (!coreSha || c.core_sha256 === coreSha) && (!setupSha || c.runtime_identity_sha256 === setupSha));
    const capture = async () => {
      const result = await ctx2.run("runtime.capture", ctx2.projectParams(), { refresh: false, render: false });
      state2.frame = result;
      await ctx2.render();
      return result;
    };
    const advance = async (buttons, frames) => {
      await ctx2.run("runtime.advance", { ...ctx2.projectParams(), frames, buttons, port: 0 }, { refresh: false, render: false });
      await capture();
    };
    ctx2.use({
      "controller-physical": () => {
        const chosen = Number(read("physical-pad"));
        state2.physicalPadIndex = Number.isInteger(chosen) && chosen >= -2 && chosen <= 15 ? chosen : -1;
        ctx2.notify("Input device selected.");
      },
      "controller-reload": async () => {
        var _a2;
        const system_id = read("profile-family"), device = Number(read("controller-type"));
        if (!Number.isInteger(device) || !controllerChoices.some(([id]) => id === device)) throw Error("Choose a controller advertised by this engine.");
        stopPlayback(state2);
        const saved = await ctx2.run("profiles.controller", { system_id, controller_devices: { ...((_a2 = state2.profile) == null ? void 0 : _a2.controller_devices) || {}, "0": device } }, { refresh: false, render: false });
        state2.profile = saved.profile;
        await ctx2.run("runtime.close", ctx2.projectParams(), { refresh: false, render: false });
        state2.runtime = null;
        state2.frame = null;
        state2.runtime = await ctx2.run("runtime.load_profile", { ...ctx2.sourceParams(), system_id }, { refresh: false, render: false });
        await ctx2.render();
        ctx2.notify("Controller type changed. Game restarted.");
      },
      "runtime-check": async () => {
        stopPlayback(state2);
        await ctx2.run("runtime.smoke_profile", { ...ctx2.sourceParams(), system_id: read("profile-family") }, { refresh: false, render: false });
        return ctx2.render();
      },
      "runtime-view": () => {
        state2.playtestExpanded = !state2.playtestExpanded;
        return ctx2.render();
      },
      "runtime-pause": () => {
        stopPlayback(state2);
        return ctx2.render();
      },
      "runtime-sound-check": async () => {
        stopPlayback(state2);
        state2.liveAudio ??= new LiveAudio();
        await state2.liveAudio.start();
        state2.liveAudio.setVolume(0.7, false);
        const ticket = state2.liveAudio.ticket;
        state2.liveAudio.enqueue(soundCheckPacket(), ticket);
        await new Promise((resolve) => setTimeout(resolve, 180));
        if (state2.liveAudio.ticket !== ticket) return;
        state2.liveAudio.stop();
        ctx2.notify("Sound test sent to audio output.");
        await ctx2.render();
      },
      "runtime-volume": () => {
        var _a2;
        (_a2 = state2.liveAudio) == null ? void 0 : _a2.setVolume(Number(read("runtime-volume")) / 100, state2.liveMuted || false);
      },
      "runtime-mute": () => {
        var _a2;
        state2.liveMuted = !state2.liveMuted;
        (_a2 = state2.liveAudio) == null ? void 0 : _a2.setVolume(state2.liveAudio.volume, state2.liveMuted);
        return ctx2.render();
      },
      "runtime-reset": async () => {
        stopPlayback(state2);
        await ctx2.api.call("runtime.close", ctx2.projectParams());
        state2.runtime = null;
        state2.frame = null;
        const content = read("runtime-content");
        state2.runtime = await ctx2.run(content.startsWith("disc:") ? "runtime.load_disc" : "runtime.load_profile", { ...ctx2.projectParams(), ...content.startsWith("disc:") ? { container_id: content.slice(5) } : { artifact_id: content }, system_id: read("profile-family") }, { refresh: false, render: false });
        return ctx2.render();
      },
      "runtime-play": async () => {
        var _a2, _b2, _c2, _d2, _e2, _f2, _g2, _h2, _i2, _j2, _k2, _l2;
        if (state2.playing) return;
        state2.playbackTicket = (state2.playbackTicket || 0) + 1;
        const ticket = state2.playbackTicket, project_id = (_a2 = state2.project) == null ? void 0 : _a2.project_id, artifact_id = (_b2 = state2.artifact) == null ? void 0 : _b2.artifact_id, session = (_c2 = state2.runtime) == null ? void 0 : _c2.session_dir;
        state2.liveAudio ??= new LiveAudio();
        await state2.liveAudio.start();
        if (state2.playbackTicket !== ticket || state2.page !== "playtest" || ((_d2 = state2.project) == null ? void 0 : _d2.project_id) !== project_id || ((_e2 = state2.artifact) == null ? void 0 : _e2.artifact_id) !== artifact_id || ((_f2 = state2.runtime) == null ? void 0 : _f2.session_dir) !== session) return;
        state2.liveAudio.setVolume(Number(ctx2.draft("runtime-volume", String(getSettings().volume))) / 100, state2.liveMuted || false);
        state2.playing = true;
        const audioTicket = state2.liveAudio.ticket;
        await ctx2.render();
        (_g2 = document.getElementById("runtime-controller")) == null ? void 0 : _g2.focus();
        let due = performance.now();
        try {
          while (state2.playing && (state2.playbackTicket || 0) === ticket && ((_h2 = state2.project) == null ? void 0 : _h2.project_id) === project_id && ((_i2 = state2.runtime) == null ? void 0 : _i2.session_dir) === session) {
            const started = performance.now(), pad = ((_j2 = document.activeElement) == null ? void 0 : _j2.id) === "runtime-controller" ? padForSelection(((_k2 = navigator.getGamepads) == null ? void 0 : _k2.call(navigator)) || [], state2.physicalPadIndex ?? -1) : null;
            const buttons = [.../* @__PURE__ */ new Set([...state2.heldButtons || [], ...controllerButtons(pad)])];
            const packet = await ctx2.api.call("runtime.step", { project_id, frames: 3, buttons, port: 0 });
            if (!state2.playing || (state2.playbackTicket || 0) !== ticket) break;
            state2.frame = packet.frame;
            drawFrame(state2.frame);
            state2.liveAudio.enqueue(packet.audio, audioTicket);
            const fps = Number((_l2 = packet.timing) == null ? void 0 : _l2.fps);
            if (!Number.isFinite(fps) || fps < 10 || fps > 240) throw new Error("The core returned unsupported playback timing.");
            due = Math.max(due + 3e3 / fps, started);
            await new Promise((resolve) => setTimeout(resolve, Math.max(0, due - performance.now())));
          }
        } catch (error) {
          ctx2.notify(error.message, true);
        } finally {
          if ((state2.playbackTicket || 0) === ticket) {
            stopPlayback(state2);
            await ctx2.render();
          }
        }
      },
      "core-choose": async () => {
        const selected2 = await ctx2.run("system.pick_file", {}, { refresh: false, render: false });
        if (selected2.path) {
          document.getElementById("core-path").value = selected2.path;
          ctx2.setDraft("core-path", selected2.path);
          writePreference("romancer-core", selected2.path);
        }
      },
      "runtime-load": async () => {
        var _a2;
        state2.liveMuted = getSettings().startMuted;
        (_a2 = ctx2.setDraft) == null ? void 0 : _a2.call(ctx2, "runtime-volume", String(getSettings().volume));
        const system_id = read("profile-family"), content = read("runtime-content");
        state2.runtime = await ctx2.run(content.startsWith("disc:") ? "runtime.load_disc" : "runtime.load_profile", { ...ctx2.projectParams(), ...content.startsWith("disc:") ? { container_id: content.slice(5) } : { artifact_id: content }, system_id }, { refresh: false, render: false });
        state2.frame = null;
        await ctx2.render();
        ctx2.notify("Native worker loaded.");
      },
      "runtime-close": async () => {
        stopPlayback(state2);
        await ctx2.run("runtime.close", ctx2.projectParams(), { refresh: false, render: false });
        state2.runtime = null;
        state2.frame = null;
        await ctx2.render();
      },
      "runtime-advance": () => advance([], Number(read("runtime-frames"))),
      "runtime-input": (node) => advance([node.dataset.id], Number(read("input-frames"))),
      "runtime-capture": capture,
      "runtime-save": async () => {
        stopPlayback(state2);
        state2.snapshot = await ctx2.run("runtime.save_state", ctx2.projectParams(), { refresh: false, render: false });
        await ctx2.render();
        ctx2.notify("Save state captured and bound to this core and game.");
      },
      "runtime-restore": async () => {
        stopPlayback(state2);
        const snapshot_id = read("checkpoint-id");
        if (!snapshot_id) throw new Error("Choose a saved state.");
        const restored = await ctx2.run("runtime.load_state", { ...ctx2.projectParams(), snapshot_id }, { refresh: false, render: false });
        state2.runtime = { ...state2.runtime, ...restored };
        state2.frame = null;
        await advance([], 1);
        ctx2.notify("State loaded. Paused after one frame to refresh the screen.");
      },
      "runtime-load-save": async () => {
        state2.runtime = await ctx2.run("runtime.load_game_save", { ...ctx2.sourceParams(), system_id: read("profile-family"), save_id: read("game-save-id") }, { refresh: false, render: false });
        state2.frame = null;
        await ctx2.render();
      },
      "runtime-save-game": () => ctx2.run("runtime.save_game", ctx2.projectParams(), { refresh: false }),
      "runtime-audio-export": async () => {
        const result = await ctx2.run("runtime.export_audio", ctx2.projectParams());
        await ctx2.api.download(state2.project.project_id, result.export.export_id, "capture.wav");
      },
      "runtime-audio": async () => {
        const result = await ctx2.run("runtime.audio", ctx2.projectParams(), { refresh: false, render: false });
        state2.audio = result;
        await ctx2.render();
        ctx2.notify(result.observed ? "Captured PCM is available in the audio report." : "The worker has no new captured audio.");
      },
      "audio-export": () => ctx2.run("audio.capture", { ...ctx2.projectParams(), config: json("audio-config"), baseline: json("audio-baseline"), format: "wav" }),
      "evidence-record": () => ctx2.run("captures.record", { ...ctx2.sourceParams(), config: json("capture-config") }),
      "evidence-search": () => ctx2.run("captures.search", { ...ctx2.projectParams(), query: json("capture-query") }),
      "evidence-open": (node) => ctx2.run("captures.get", { ...ctx2.projectParams(), capture_id: node.dataset.id }),
      "evidence-annotate": () => {
        const selected2 = state2.results["captures.get"];
        if (!selected2) throw new Error("Open a stored capture first.");
        return ctx2.run("captures.annotate", { ...ctx2.projectParams(), capture_id: selected2.record.capture_id, entries: json("capture-annotations") });
      }
    });
    const active = !!state2.runtime;
    const loaded = ((_k = (_j = state2.runtime) == null ? void 0 : _j.loaded) == null ? void 0 : _k.loaded) || ((_l = state2.runtime) == null ? void 0 : _l.loaded), advertised = ((_n = (_m = loaded == null ? void 0 : loaded.controller_types) == null ? void 0 : _m.find((p) => p.port === 0)) == null ? void 0 : _n.devices) || [];
    const controllerChoices = [[1, "Standard joypad"], ...advertised.filter((d) => d.selectable && d.id !== 1 && d.id !== 0).map((d) => [d.id, d.name])];
    const pads = typeof navigator !== "undefined" ? [...((_o = navigator.getGamepads) == null ? void 0 : _o.call(navigator)) || []].filter(Boolean) : [];
    const physicalChoices = [[-1, "Automatic gamepad"], [-2, "Keyboard only"], ...pads.map((p) => [p.index, p.id || "Gamepad " + (p.index + 1)])];
    const controllerSetup = `<div class="field-row">${select("physical-pad", "Input device", physicalChoices, state2.physicalPadIndex ?? -1)}${button("Use input device", "controller-physical")}</div>${active ? `<div class="field-row">${select("controller-type", "Emulated controller", controllerChoices, ((_p = loaded == null ? void 0 : loaded.controller_devices) == null ? void 0 : _p["0"]) ?? 1)}${button("Apply type & restart game", "controller-reload")}</div><p class="subtle">Changing the emulated type restarts the selected ROM. Save states require the same controller setup.</p>` : ""}`;
    const stateControls = `<div class="playtest-toolbar"><div class="actions">${state2.playing ? button("Pause", "runtime-pause", { primary: true }) : button("Play", "runtime-play", { disabled: !active, primary: true })}${button("Save state", "runtime-save", { disabled: !active })}</div><div class="actions state-slot">${select("checkpoint-id", "Saved state", checkpoints.map((c) => [c.snapshot_id, c.created_utc ? c.created_utc.replace("T", " ").replace("+00:00", " UTC") : c.snapshot_id.slice(0, 8) + " · " + c.run_mode]), ((_q = state2.snapshot) == null ? void 0 : _q.snapshot_id) || ((_r = checkpoints.at(-1)) == null ? void 0 : _r.snapshot_id))}${button("Load state", "runtime-restore", { disabled: !active || !checkpoints.length })}</div></div>`;
    return `${heading("", "Playtest", "", active ? button(state2.playtestExpanded ? "Show setup" : "Expand game", "runtime-view") + button("Close worker", "runtime-close", { icon: "close" }) : "")}<div class="identity">${badge(active ? "NATIVE WORKER LOADED" : state2.profileAvailable ? "READY TO LOAD" : "SETUP REQUIRED", active ? "good" : "warm")}<strong>${esc(((_s = state2.artifact) == null ? void 0 : _s.name) || "Selected source")}</strong><code>${short((_t = state2.artifact) == null ? void 0 : _t.sha256)}</code></div><div class="grid-two playtest-layout ${active && state2.playtestExpanded ? "playtest-expanded" : ""}"><section class="card"><div class="card-heading"><h3>Playtest screen</h3><span class="subtle" id="runtime-frame-label">${state2.frame ? `Frame ${state2.frame.index} · ${state2.frame.width} × ${state2.frame.height}` : "No measured frame yet"}</span></div>${stateControls}<div class="actions">${button("Inspect graphics", "graphics-show-region", { disabled: !state2.frame, icon: "assets" })}</div><div class="screen" id="runtime-controller" tabindex="0" aria-label="Game controller keyboard focus">${state2.frame || active ? '<canvas id="runtime-screen" aria-label="Measured emulator capture"></canvas>' : empty(state2.profileAvailable ? "Ready to playtest" : "Connect a compatible core", state2.profileAvailable ? "Load game to begin." : "Choose a core in System setup.")}</div><details class="manual-runtime"><summary>Controller & frame tools</summary>${controllerSetup}<div class="runtime-controls"><div><div class="field-row">${field("runtime-frames", "Frames to advance", ctx2.draft("runtime-frames", "60"), { type: "number", min: 1 })}${field("input-frames", "Frames per input", ctx2.draft("input-frames", "1"), { type: "number", min: 1 })}</div><div class="actions">${button("Advance frames", "runtime-advance", { primary: true, disabled: !active, icon: "playtest" })}${button("Capture", "runtime-capture", { disabled: !active })}${button("Reset", "runtime-reset", { disabled: !active })}${button(state2.liveMuted ? "Unmute" : "Mute", "runtime-mute", { disabled: !active })}${field("runtime-volume", "Volume (%)", ctx2.draft("runtime-volume", String(getSettings().volume)), { type: "number", min: 0, max: 100 })}${button("Set volume", "runtime-volume", { disabled: !active })}${button("Test sound", "runtime-sound-check")}${button("Check ROM", "runtime-check", { disabled: !state2.profile })}</div></div><div class="dpad" aria-label="Controller directions">${button("↑", "runtime-input", { id: "up", disabled: !active })}${button("←", "runtime-input", { id: "left", disabled: !active })}${button("→", "runtime-input", { id: "right", disabled: !active })}${button("↓", "runtime-input", { id: "down", disabled: !active })}</div></div><div class="actions">${["a", "b", "x", "y", "l", "r", "start", "select"].map((id) => button(id.toUpperCase(), "runtime-input", { id, disabled: !active })).join("")}</div><p class="subtle">Use your saved controller keys while the game has focus.</p></details></section><section class="card playtest-setup"><h3>System setup</h3>${setup2}${button("Load game", "runtime-load", { primary: !active, disabled: active || !state2.profile })}<details class="config"><summary>Advanced core setup</summary>${field("core-path", "Native libretro core", ctx2.draft("core-path", ((_u = state2.profile) == null ? void 0 : _u.core) || readPreference("romancer-core") || ""), { placeholder: state2.capabilities.platform === "Windows" ? "C:\\RetroArch\\cores\\snes9x_libretro.dll" : "/path/to/core_libretro.so", hint: `Choose a core built for ${state2.capabilities.platform}. A Linux .so cannot load in Windows Python.` })}<div class="actions">${button("Choose core", "core-choose", { icon: "folder" })}${button("Load selected source", "runtime-load", { primary: !active, disabled: active })}</div>${jsonEditor("core-options", "Advanced core options", ctx2.draft("core-options", JSON.stringify(((_v = state2.profile) == null ? void 0 : _v.options) || {}, null, 2)))}</details><div class="config"><h3>Audio</h3>${button("Drain audio", "runtime-audio", { disabled: !active })}</div>${((_w = state2.audio) == null ? void 0 : _w.observed) ? `<canvas id="pcm-wave" width="480" height="80" aria-label="Captured PCM waveform"></canvas><audio id="pcm-player" controls aria-label="Play captured audio"></audio>${button("Save captured WAV", "runtime-audio-export", { disabled: !state2.audio.complete })}` : ""}<details class="config"><summary>Audio capture test (advanced)</summary>${jsonEditor("audio-config", "Cold-boot audio capture configuration", ctx2.draft("audio-config", JSON.stringify({ schema_version: 1, load: {}, steps: [{ frames: 1, buttons: [], port: 0 }], timeout_seconds: 30 }, null, 2)))}${jsonEditor("audio-baseline", "Exact sample-duration baseline", ctx2.draft("audio-baseline", "{}"))}${button("Capture & export WAV", "audio-export")}<p class="subtle small">Audio duration is checked against samples and an explicit rational baseline, independently of video timing.</p></details></section></div>${((_x = state2.results["runtime.smoke_profile"]) == null ? void 0 : _x.source_sha256) === ((_y = state2.artifact) == null ? void 0 : _y.sha256) ? `<section class="card"><h3>ROM startup check</h3><p>${state2.results["runtime.smoke_profile"].frames_advanced} frames · ${state2.results["runtime.smoke_profile"].frame.width} × ${state2.results["runtime.smoke_profile"].frame.height} video · ${state2.results["runtime.smoke_profile"].audio.captured_frames} audio sample frames · worker closed</p><p class="subtle">Startup observations only. Regression checks need expected results.</p><div class="actions">${button("Record a test route", "navigate", { id: "routes" })}${button("Compare regression runs", "navigate", { id: "regression" })}</div></section>` : ""}${report(state2.results["runtime.smoke_profile"], "ROM check details")}${report(state2.results["runtime.load"], "Worker capabilities")}${report(state2.results["runtime.close"], "Worker closure")}${report(state2.results["runtime.save_state"] ? { ...state2.results["runtime.save_state"], state_base64: "[local snapshot payload hidden]" } : null, "State identity")}${report(state2.audio ? { ...state2.audio, pcm_s16le_base64: "[PCM payload hidden]" } : null, "Captured audio")}${report(state2.results["audio.capture"], "WAV export")}${state2.artifact ? saveManager(ctx2, saveListing) + checkpointControls(ctx2) + graphicsInvestigation(ctx2) : ""}${evidence(ctx2)}`;
  }
  function mount6(ctx2) {
    mountController(ctx2);
    mountCheckpoint(ctx2);
    mountAudio(ctx2.state.audio);
    drawFrame(ctx2.state.frame);
  }
  function drawFrame(frame) {
    const canvas = document.getElementById("runtime-screen");
    if (!frame || !canvas) return;
    const raw = Uint8Array.from(atob(frame.rgb24_base64), (c) => c.charCodeAt(0));
    canvas.width = frame.width;
    canvas.height = frame.height;
    const context = canvas.getContext("2d"), image = context.createImageData(frame.width, frame.height);
    for (let i = 0; i < frame.width * frame.height; i++) image.data.set([raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2], 255], i * 4);
    context.putImageData(image, 0, 0);
    const label = document.getElementById("runtime-frame-label");
    if (label) label.textContent = "Frame " + frame.index + " · " + frame.width + " × " + frame.height;
  }
  function evidence(ctx2) {
    const { state: state2 } = ctx2, found = state2.results["captures.search"], selected2 = state2.results["captures.get"];
    return `<details class="card"><summary>Capture evidence library (advanced)</summary><div class="card-heading"><h3>Capture evidence library</h3>${badge("SOURCE-BOUND")}</div><p class="subtle">Record a fresh measured run, then search and annotate its stored PNG. Annotations remain human statements; native pixels keep their measured origin.</p>${jsonEditor("capture-config", "Recording configuration", ctx2.draft("capture-config", JSON.stringify({ load: {}, steps: [{ frames: 1, buttons: [], port: 0 }], initial_state_file: null, timeout: 30 }, null, 2)))}${button("Record native evidence", "evidence-record")}${jsonEditor("capture-query", "Capture search filters", ctx2.draft("capture-query", '{"limit":20}'))}${button("Search stored captures", "evidence-search")}<div class="actions">${((found == null ? void 0 : found.matches) || []).map((row) => button(row.capture_id.slice(0, 12) + " · " + row.run_mode, "evidence-open", { id: row.capture_id })).join("")}</div>${selected2 ? `${selected2.runtime_trusted === false ? "<p>Historical imported capture</p>" : ""}<div class="screen"><img alt="Verified stored native capture" style="max-width:100%;image-rendering:pixelated" src="data:image/png;base64,${selected2.png_base64}"></div>${report({ ...selected2, png_base64: "[verified PNG shown above]" }, "Capture identity")}${jsonEditor("capture-annotations", "New annotations", ctx2.draft("capture-annotations", JSON.stringify([{ kind: "note", text: "", method: "manual", author: "RetchEWretched", locator: null, region: null, resource: null, supersedes: null }], null, 2)))}${button("Add annotations", "evidence-annotate")}` : ""}${report(state2.results["captures.record"], "Recorded evidence")}${report(state2.results["captures.annotate"], "Annotations")}</details>`;
  }

  // romancer/ui/views/debug.js
  var debug_exports = {};
  __export(debug_exports, {
    mount: () => mount7,
    render: () => render10
  });

  // romancer/ui/value_finder.js
  function finderTarget(text) {
    if (!text.trim()) return null;
    const n = Number(text);
    if (!Number.isSafeInteger(n)) throw Error("Enter a whole number or leave the value blank.");
    return n;
  }
  var matchingFinder = (state2, result) => {
    var _a;
    return (result == null ? void 0 : result.selection_scope) === selectionKey(state2) && result.source_sha256 === ((_a = state2.artifact) == null ? void 0 : _a.sha256);
  };
  function valueFinder(ctx2) {
    var _a;
    const { state: state2 } = ctx2, scope = selectionKey(state2), params = { ...ctx2.sourceParams() }, current2 = () => selectionKey(state2) === scope;
    const result = matchingFinder(state2, state2.valueSearch) ? state2.valueSearch : null, video = matchingFinder(state2, state2.valueVideo) ? state2.valueVideo : null;
    const keep = async (operation, parameters, key3) => {
      const next = await ctx2.run(operation, { ...params, ...parameters }, { render: false });
      if (!current2()) return;
      state2[key3] = { ...next, selection_scope: scope };
      delete state2.results[operation];
      return ctx2.render();
    };
    ctx2.use({
      "finder-start": () => keep("values.start", { region: 2, offset: finderTarget(read("finder-offset")), length: finderTarget(read("finder-length")), width: Number(read("finder-width")), endian: read("finder-endian"), signed: read("finder-sign") === "true", target: finderTarget(read("finder-value")) }, "valueSearch"),
      "finder-narrow": () => {
        if (!result) throw Error("Start a search for this source first.");
        return keep("values.narrow", { search_id: result.search_id, relation: read("finder-relation"), target: finderTarget(read("finder-value")) }, "valueSearch");
      },
      "finder-watch": (node) => {
        var _a2, _b;
        if (!current2() || !result) throw Error("Start a current-source search first.");
        const offset = Number(node.dataset.id);
        if (!result.matches.some((m) => m.offset === offset)) throw Error("Select a measured result.");
        const watches = ((_b = (_a2 = state2.artifact.descriptors) == null ? void 0 : _a2.watches) == null ? void 0 : _b.watches) || [];
        return ctx2.run("watches.save", { ...params, watches: [...watches, { name: "RAM 0x" + offset.toString(16), region: result.region, offset, length: result.width }] });
      },
      "video-read": () => keep("video.inspect", { offset: finderTarget(read("video-offset")), length: finderTarget(read("video-length")), codec: read("video-codec") }, "valueVideo")
    });
    const codecs2 = [["tile8-planar2-msb-v1", "NES planar 2-bit"], ["tile8-paired2-msb-v1", "Game Boy / paired 2-bit"], ["tile8-paired4-msb-v1", "SNES paired 4-bit"], ["tile8-packed4-high-v1", "Genesis packed 4-bit"], ["tile8-packed4-low-v1", "GBA packed 4-bit"]];
    return `<section class="card"><h3>Find a changing value</h3><p>Search a bounded System RAM range. Play to change the value, pause, then narrow the results. RAM matches do not identify a ROM location.</p><div class="field-row">${field("finder-offset", "RAM region offset", ctx2.draft("finder-offset", "0"))}${field("finder-length", "Bytes (1–4096)", ctx2.draft("finder-length", "2048"))}${select("finder-width", "Integer width", [[1, "8 bit"], [2, "16 bit"], [4, "32 bit"]], ctx2.draft("finder-width", "1"))}${select("finder-endian", "Byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("finder-endian", state2.artifact.system_id === "genesis" ? "big" : "little"))}${select("finder-sign", "Sign", [["false", "Unsigned"], ["true", "Signed"]], ctx2.draft("finder-sign", "false"))}${field("finder-value", "Exact value (blank for unknown)", ctx2.draft("finder-value", ""))}</div><div class="actions">${button("Start RAM search", "finder-start", { disabled: !state2.runtime, primary: !result })}${select("finder-relation", "Keep values that", [["equal", "Equal exact value"], ["changed", "Changed"], ["unchanged", "Stayed the same"], ["increased", "Increased"], ["decreased", "Decreased"]], ctx2.draft("finder-relation", "changed"))}${button("Capture & narrow", "finder-narrow", { disabled: !result || !state2.runtime, primary: !!result })}${button("Open Playtest", "navigate", { id: "playtest" })}</div>${result ? `<p>${result.total} matches · showing ${result.matches.length} · observation ${result.sequence}</p><div class="table-wrap"><table><thead><tr><th>RAM offset</th><th>Previous</th><th>Current</th><th></th></tr></thead><tbody>${result.matches.map((m) => `<tr><td><code>0x${m.offset.toString(16)}</code></td><td>${esc(m.previous ?? "—")}</td><td>${esc(m.value)}</td><td>${button("Add watch", "finder-watch", { id: String(m.offset) })}</td></tr>`).join("")}</tbody></table></div>` : ""}</section><details class="card"><summary>Available video memory</summary><p>Read bytes exposed by the selected core and decode the chosen tested tile format. Indexed grayscale preview; palette, OAM and ROM ownership remain unknown.</p><div class="field-row">${field("video-offset", "Video RAM offset", ctx2.draft("video-offset", "0"))}${field("video-length", "Bytes (1–4096)", ctx2.draft("video-length", "256"))}${select("video-codec", "Tile format", codecs2, ctx2.draft("video-codec", ((_a = codecs2[["nes", "gb", "snes", "genesis", "gba"].indexOf(state2.artifact.system_id === "gbc" ? "gb" : state2.artifact.system_id)]) == null ? void 0 : _a[0]) || codecs2[0][0]))}</div>${button("Read video tiles", "video-read", { disabled: !state2.runtime })}${video ? `<p>${video.tiles.length} decoded tiles · showing ${Math.min(128, video.tiles.length)}</p><canvas id="video-tiles" aria-label="Measured video memory indexed tile preview"></canvas>` : ""}</details>`;
  }
  function mountValueFinder(ctx2) {
    const result = ctx2.state.valueVideo, canvas = document.getElementById("video-tiles");
    if (!canvas || !matchingFinder(ctx2.state, result)) return;
    const tiles = result.tiles.slice(0, 128), columns2 = 16;
    canvas.width = columns2 * 8;
    canvas.height = Math.ceil(tiles.length / columns2) * 8;
    const c = canvas.getContext("2d"), image = c.createImageData(canvas.width, canvas.height);
    const maximum = result.codec.includes("2-") ? 3 : 15;
    tiles.forEach((tile, n) => tile.forEach((value, i) => {
      const p = ((Math.floor(n / columns2) * 8 + Math.floor(i / 8)) * canvas.width + n % columns2 * 8 + i % 8) * 4, shade = Math.round(value / maximum * 255);
      image.data.set([shade, shade, shade, 255], p);
    }));
    c.putImageData(image, 0, 0);
    canvas.style.width = "min(100%,512px)";
    canvas.style.imageRendering = "pixelated";
  }

  // romancer/ui/investigation_series.js
  function seriesNumber(text) {
    if (!text.trim()) return null;
    const value = Number(text);
    if (!Number.isSafeInteger(value)) throw Error("Enter a whole number, or leave the observed value blank.");
    return value;
  }
  function currentResult(state2, scope, result) {
    var _a, _b;
    return selectionKey(state2) === scope && (result == null ? void 0 : result.source_sha256) === ((_a = state2.artifact) == null ? void 0 : _a.sha256) && result.artifact_id === ((_b = state2.artifact) == null ? void 0 : _b.artifact_id);
  }
  async function investigationSeries(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, scope = selectionKey(state2), params = { ...ctx2.sourceParams() };
    let entry = state2.investigationSeries;
    if ((entry == null ? void 0 : entry.scope) !== scope) state2.investigationSeries = entry = { scope, result: null, generation: 0, page: 0, error: null };
    const owned = () => selectionKey(state2) === scope && state2.investigationSeries === entry;
    const save = async (operation, parameters, native = false) => {
      var _a2;
      if (!owned()) throw Error("The selected source changed. Open its investigation again.");
      const runtime = state2.runtime;
      if (native && (runtime == null ? void 0 : runtime.game_sha256) !== ((_a2 = state2.artifact) == null ? void 0 : _a2.sha256)) throw Error("Load this source in Playtest first.");
      const generation = ++entry.generation;
      entry.error = null;
      const result2 = await ctx2.api.call(operation, { ...params, ...parameters });
      if (!owned() || entry.generation !== generation || native && state2.runtime !== runtime) return;
      if ((result2 == null ? void 0 : result2.ok) === false) throw Error(result2.error || "Investigation could not finish.");
      if (!currentResult(state2, scope, result2)) throw Error("Investigation result belongs to another selected source.");
      entry.result = result2;
      entry.loaded = true;
      entry.page = 0;
      ctx2.setDraft("investigation-id", result2.investigation_id);
      await ctx2.render();
    };
    const remembered = ctx2.draft("investigation-id", "");
    if (!entry.loaded && remembered) {
      entry.loaded = true;
      const generation = ++entry.generation;
      try {
        const result2 = await ctx2.api.call("investigations.get", { ...params, investigation_id: remembered });
        if (owned() && entry.generation === generation) {
          if ((result2 == null ? void 0 : result2.ok) === false) throw Error(result2.error);
          if (!currentResult(state2, scope, result2)) throw Error("Saved investigation belongs to another source.");
          entry.result = result2;
        }
      } catch (error) {
        if (owned() && entry.generation === generation) entry.error = error.message;
      }
    }
    const result = currentResult(state2, scope, entry.result) ? entry.result : null;
    ctx2.use({
      "series-start": () => save("investigations.start", {
        title: read("series-title").trim(),
        region: 2,
        offset: seriesNumber(read("series-offset")),
        length: seriesNumber(read("series-length")),
        value: seriesNumber(read("series-value"))
      }, true),
      "series-capture": async () => {
        if (!owned() || !result) throw Error("Start an investigation for the selected source first.");
        if (!result.runtime_trusted) throw Error("Historical investigations are read-only. Start a fresh investigation.");
        const relation = read("series-relation");
        return save("investigations.capture", {
          investigation_id: result.investigation_id,
          label: read("series-label").trim() || "Observation " + (result.observation_count + 1),
          value: seriesNumber(read("series-value")),
          relation,
          delta: relation === "delta" ? seriesNumber(read("series-delta")) : null
        }, true);
      },
      "series-refresh": async () => {
        if (!owned() || !result) throw Error("Open an investigation for this source first.");
        return save("investigations.get", { investigation_id: result.investigation_id });
      },
      "series-page": (node) => {
        if (!owned()) return;
        entry.page = Math.max(0, entry.page + Number(node.dataset.id));
        return ctx2.render();
      },
      "series-watch": (node) => {
        var _a2;
        if (!owned() || !result) throw Error("Analyze the current source first.");
        const candidate = result.candidates.find((c) => c.candidate_id === node.dataset.id);
        if (!candidate) throw Error("Select a current hypothesis.");
        const saved = (_a2 = state2.artifact.descriptors) == null ? void 0 : _a2.watches, existing = (saved == null ? void 0 : saved.source_sha256) === state2.artifact.sha256 ? saved.watches : [];
        return ctx2.run("watches.save", { ...params, watches: [...existing || [], { name: "Candidate 0x" + candidate.offset.toString(16), region: 2, offset: candidate.offset, length: candidate.width }] });
      }
    });
    const ready = ((_a = state2.runtime) == null ? void 0 : _a.game_sha256) === ((_b = state2.artifact) == null ? void 0 : _b.sha256), candidates = (result == null ? void 0 : result.candidates) || [], rows = candidates.slice(entry.page * 24, (entry.page + 1) * 24);
    return `<section class="card investigation-series"><div class="card-heading"><h2>Find out what changes</h2>${result ? button("Reopen evidence", "series-refresh") : ""}</div><p>Pause the game, record a number or change, then repeat. ROMancer tests numeric formats and filters the results. No game profile is required.</p>${entry.error ? `<p class="notice warm">${esc(entry.error)}</p>` : ""}<div class="field-row">${field("series-title", "What are you investigating?", ctx2.draft("series-title", "A changing number"))}${field("series-value", "Value on screen (optional)", ctx2.draft("series-value", ""), { placeholder: "Leave blank if unknown" })}</div><details><summary>Memory range</summary><div class="field-row">${field("series-offset", "System RAM offset", ctx2.draft("series-offset", "0"))}${field("series-length", "Bytes to observe (1–4096)", ctx2.draft("series-length", "2048"))}</div><p>Offsets refer to the memory region exposed by the emulator. ROMancer does not invent a CPU address from this number.</p></details><div class="actions">${button(result ? "Start a separate investigation" : "Capture before", "series-start", { primary: !result, disabled: !ready })}${button("Open Playtest", "navigate", { id: "playtest" })}</div>${!ready ? '<p class="subtle">Load the selected ROM in Playtest to record observations. Saved evidence can be read without a running game.</p>' : ""}${result ? `<div class="identity"><strong>${esc(result.title)}</strong><span>${result.observation_count} observations · ${result.unchanged_controls} unchanged controls</span>${result.runtime_trusted ? "" : "<strong>Historical evidence · read only</strong>"}</div><div class="field-row">${field("series-label", "Observation label", ctx2.draft("series-label", ""))}${select("series-relation", "What happened?", [["changed", "It changed"], ["increased", "It increased"], ["decreased", "It decreased"], ["unchanged", "It stayed unchanged (control)"], ["delta", "It changed by an exact amount"]], ctx2.draft("series-relation", "changed"))}${field("series-delta", "Exact change, when selected", ctx2.draft("series-delta", ""), { placeholder: "For example -5" })}</div>${button("Capture & investigate", "series-capture", { primary: true, disabled: !ready || !result.runtime_trusted || result.observation_count >= 32 })}<p class="notice">${esc(result.next_experiment)}</p><details><summary>Observation history · ${result.history.length}</summary><div class="table-wrap"><table><thead><tr><th>Observation</th><th>Number supplied</th><th>Change</th><th>Native sequence</th></tr></thead><tbody>${result.history.map((row) => `<tr><td>${esc(row.label)}</td><td>${esc(row.value ?? "—")}</td><td>${esc(row.relation)}</td><td>${esc(row.sequence)}</td></tr>`).join("")}</tbody></table></div></details><h3>Correlated hypotheses · ${result.total}</h3><p class="subtle">Agreement across observations does not yet identify a named property, writing instruction or ROM location.</p>${result.truncated ? `<p class="notice warm">Showing the best ${candidates.length} of ${result.total} matching hypotheses. Narrow the range or add an observation to separate them.</p>` : ""}${rows.length ? `<div class="table-wrap"><table><thead><tr><th>RAM offset</th><th>Format tested</th><th>Values observed</th><th>Display relationship</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr><td><code>0x${row.offset.toString(16)}</code></td><td>${row.width * 8} bit · ${esc(row.endian)} · ${esc(row.encoding)}${row.signed ? " · signed" : ""}</td><td>${row.values.map(esc).join(" → ")}</td><td>${row.model === "exact" ? "Matches supplied numbers" : row.model === "constant_offset" ? "Stored = displayed " + (row.bias < 0 ? "− " + Math.abs(row.bias) : "+ " + row.bias) : "Matches change/control observations"}</td><td>${button("Add watch", "series-watch", { id: row.candidate_id })}</td></tr>`).join("")}</tbody></table></div><div class="actions">${button("Previous hypotheses", "series-page", { id: "-1", disabled: !entry.page })}<span>Page ${entry.page + 1}</span>${button("Next hypotheses", "series-page", { id: "1", disabled: (entry.page + 1) * 24 >= candidates.length })}</div>` : "<p>No surviving numeric hypotheses yet. Keep the earlier observations and try the suggested next experiment.</p>"}` : ""}</section>`;
  }

  // romancer/ui/memory_watches.js
  function memoryWatches(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, source = state2.artifact;
    if (!source) return "";
    const watches = ((_b = (_a = source.descriptors) == null ? void 0 : _a.watches) == null ? void 0 : _b.source_sha256) === source.sha256 ? source.descriptors.watches.watches : [];
    const scope = selectionKey(state2), runtime = state2.runtime, params = { ...ctx2.projectParams() }, signature = JSON.stringify(watches);
    if (state2.watchScope !== scope || state2.watchRuntime !== runtime) {
      state2.watchScope = scope;
      state2.watchRuntime = runtime;
      state2.watchReadings = null;
      state2.watchBaseline = null;
      state2.watchChanges = null;
      state2.watchGeneration = (state2.watchGeneration || 0) + 1;
    }
    const current2 = () => {
      var _a2, _b2, _c;
      const saved = (_b2 = (_a2 = state2.artifact) == null ? void 0 : _a2.descriptors) == null ? void 0 : _b2.watches;
      return selectionKey(state2) === scope && state2.runtime === runtime && JSON.stringify((saved == null ? void 0 : saved.source_sha256) === ((_c = state2.artifact) == null ? void 0 : _c.sha256) ? saved.watches : []) === signature;
    };
    const save = (next) => {
      if (!current2()) throw Error("The selected source changed. Add watches again.");
      state2.watchGeneration++;
      state2.watchBaseline = null;
      state2.watchReadings = null;
      state2.watchChanges = null;
      return ctx2.run("watches.save", { ...ctx2.sourceParams(), watches: next });
    };
    ctx2.use({
      "watch-add": () => save([...watches, { name: read("watch-name"), region: Number(read("watch-region")), offset: Number(read("watch-offset")), length: Number(read("watch-length")) }]),
      "watch-remove": (node) => save(watches.filter((_, i) => i !== Number(node.dataset.id))),
      "watch-read": async () => {
        if (!current2() || !runtime) throw Error("Load this source in Playtest before reading watches.");
        const generation = ++state2.watchGeneration, baseline = state2.watchBaseline, valid = () => current2() && state2.watchGeneration === generation && state2.watchBaseline === baseline, readings = {}, changes = {};
        let context = null;
        for (const watch of watches) {
          const result = await ctx2.api.call("runtime.memory", { ...params, region: watch.region, offset: watch.offset, length: watch.length });
          if (!valid()) return;
          if (result.game_sha256 !== source.sha256) throw new Error("The loaded game differs from the selected source. Load this source in Playtest.");
          const binding = JSON.stringify([result.worker_session_id, result.epoch, result.game_sha256, result.core_sha256, Object.entries(result.core_options || {}).sort()]);
          if (context !== null && context !== binding) throw Error("The runtime context changed while reading watches. Read them again.");
          context = binding;
          readings[watch.name] = result;
        }
        if (baseline) for (const watch of watches) {
          const before = baseline[watch.name];
          if (before) {
            const compared = await ctx2.api.call("watches.compare", { before, after: readings[watch.name] });
            if (!valid()) return;
            changes[watch.name] = compared;
          }
        }
        if (!valid()) return;
        state2.watchReadings = readings;
        state2.watchChanges = changes;
        return ctx2.render();
      },
      "watch-baseline": () => {
        if (!current2() || !state2.watchReadings) throw new Error("Read current watches first.");
        state2.watchGeneration++;
        state2.watchBaseline = structuredClone(state2.watchReadings);
        state2.watchChanges = null;
        return ctx2.render();
      }
    });
    return `<section class="card"><h3>Memory watches</h3><div class="field-row">${field("watch-name", "Name", ctx2.draft("watch-name", "Watch " + (watches.length + 1)))}${select("watch-region", "Memory region", [[2, "System RAM"], [3, "Video RAM"], [0, "Save RAM"]], ctx2.draft("watch-region", "2"))}${field("watch-offset", "Region offset", ctx2.draft("watch-offset", "0"))}${field("watch-length", "Bytes (1–256)", ctx2.draft("watch-length", "1"))}</div>${button("Add watch", "watch-add", { disabled: watches.length >= 32 })}<div class="table-wrap"><table><thead><tr><th>Name</th><th>Range</th><th>Current bytes</th><th>Changes</th><th></th></tr></thead><tbody>${watches.map((watch, i) => {
      var _a2, _b2, _c, _d;
      return `<tr><td>${esc(watch.name)}</td><td>${watch.region}:0x${watch.offset.toString(16)} · ${watch.length}</td><td><code>${esc(((_b2 = (_a2 = state2.watchReadings) == null ? void 0 : _a2[watch.name]) == null ? void 0 : _b2.raw_hex) || "Read to capture")}</code></td><td>${((_d = (_c = state2.watchChanges) == null ? void 0 : _c[watch.name]) == null ? void 0 : _d.changes.map((c) => "0x" + c.offset.toString(16) + ": " + c.before + " → " + c.after).join(", ")) || "—"}</td><td>${button("Remove", "watch-remove", { id: String(i) })}</td></tr>`;
    }).join("")}</tbody></table></div><div class="actions">${button("Read watches", "watch-read", { disabled: !state2.runtime || !watches.length })}${button("Set comparison baseline", "watch-baseline", { disabled: !state2.watchReadings })}</div><p class="subtle">${state2.watchBaseline ? "Baseline saved for this session. Advance in Playtest, then read again." : state2.runtime ? "Read watches, then set a comparison baseline." : "Load this source in Playtest to observe available memory."}</p></section>`;
  }

  // romancer/ui/hardware_reference.js
  function hardwareReference(ctx2) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2;
    if (!state2.artifact) return "";
    const scope = selectionKey(state2), system2 = state2.artifact.system_id;
    const doc = (_c = (_b = (_a = state2.romScans) == null ? void 0 : _a[scope]) == null ? void 0 : _b.result) == null ? void 0 : _c.hardware_reference;
    const result = ((_d = state2.hardwareAddress) == null ? void 0 : _d.scope) === scope ? state2.hardwareAddress.result : null;
    ctx2.use({ "hardware-explain": async () => {
      if (scope !== selectionKey(state2)) throw Error("The selected source changed. Explain the current address again.");
      const generation = state2.hardwareRequestGeneration = (state2.hardwareRequestGeneration || 0) + 1;
      const result2 = await ctx2.api.call("systems.classify_address", { system_id: system2, address: Number(read("hardware-address")), domain: read("hardware-domain") });
      if (scope !== selectionKey(state2) || state2.hardwareRequestGeneration !== generation) return;
      state2.hardwareAddress = { scope, result: result2 };
      await ctx2.render();
    } });
    const domains = Object.keys((doc == null ? void 0 : doc.domains) || { cpu: 0 });
    return `<details class="card hardware-reference"><summary>Hardware & address help</summary>${doc ? `<p><strong>${esc(doc.cpu)}</strong> · ${esc(doc.endian)}-endian CPU convention</p><p>${esc(doc.mapping)}</p><p>${esc(doc.graphics)}</p>` : "<p>Finish a ROM scan for the system overview. Address help is available now.</p>"}<div class="field-row">${select("hardware-domain", "Address domain", domains.map((domain) => [domain, { cpu: "CPU address", ppu: "NES PPU address", vram: "Physical VRAM offset", apu: "SNES audio CPU address" }[domain] || domain]), ctx2.draft("hardware-domain", "cpu"))}${field("hardware-address", "Address or offset", ctx2.draft("hardware-address", "0x8000"))}${button("Explain address", "hardware-explain")}</div>${(result == null ? void 0 : result.ok) ? `<div class="notice"><strong>${esc(result.label)}</strong><p>${esc(result.note)}</p><p>This describes a hardware range. It does not identify a game value or resolve a ROM file offset.</p></div>` : ""}<p>For file bytes, use Address explorer with a checked mapping. Native memory snapshots use offsets within the core’s exposed region.</p>${doc ? `<details><summary>Technical references</summary>${doc.references.filter((url) => /^https?:\/\//i.test(url)).map((url, index) => `<p><a href="${esc(url)}" target="_blank" rel="noreferrer noopener">Reference ${index + 1}</a></p>`).join("")}</details>` : ""}</details>`;
  }

  // romancer/ui/views/debug.js
  async function render10(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    if (!state2.artifact) return empty("Select a source or build", "A case binds exact source bytes and a registered build.");
    const scope = selectionKey(state2), params = { ...ctx2.sourceParams() }, source = state2.artifact, current2 = () => selectionKey(state2) === scope;
    const references = ((_a = state2.debugReferences) == null ? void 0 : _a.scope) === scope && state2.debugReferences.result.source_sha256 === source.sha256 ? state2.debugReferences.result : null;
    const mapped = ((_b = state2.debugAddress) == null ? void 0 : _b.scope) === scope && state2.debugAddress.result.source_sha256 === source.sha256 && state2.debugAddress.result.artifact_id === source.artifact_id ? state2.debugAddress.result : null;
    const resolved = (mapped == null ? void 0 : mapped.ok) === true && mapped.status === "RESOLVED" && Number.isSafeInteger(mapped.offset) && mapped.offset >= 0 && mapped.offset < source.size;
    const keep = async (operation, parameters, key3) => {
      if (!current2()) throw Error("The selected source changed. Run this investigation again.");
      const generations = state2.debugRequestGeneration ??= {};
      const generation = generations[key3] = (generations[key3] || 0) + 1;
      delete state2[key3];
      const result2 = await ctx2.run(operation, { ...params, ...parameters }, { render: false });
      if (!current2() || generations[key3] !== generation) return;
      state2[key3] = { scope, result: result2 };
      return ctx2.render();
    };
    const jump = (offset) => {
      if (!current2()) throw Error("The selected source changed. Inspect the current result again.");
      if (!Number.isSafeInteger(offset) || offset < 0 || offset >= source.size) throw Error("The result is outside this source.");
      state2.resourceJump = offset;
      return ctx2.navigate("resources");
    };
    ctx2.use({
      "uses-read": () => keep("resources.address_uses", { offset: Number(read("uses-offset")) }, "debugReferences"),
      "uses-open": (node) => {
        const offset = Number(node.dataset.id);
        if (!(references == null ? void 0 : references.ok) || !references.uses.some((row) => row.offset === offset)) throw Error("Find current declared references again.");
        return jump(offset);
      },
      "address-open": () => {
        if (!resolved) throw Error("Resolve a current declared address again.");
        return jump(mapped.offset);
      },
      "address-resolve": () => {
        const system_id = read("address-system"), id = read("address-mapping");
        let mapping = { id };
        if (id === "nrom") mapping = { id, prg_offset: Number(read("address-prg")), prg_size: Number(read("address-prg-size")) };
        if (id === "prg-bank") mapping = { id, prg_offset: Number(read("address-prg")), bank_size: Number(read("address-bank-size")), window_start: Number(read("address-window")), window_size: Number(read("address-bank-size")) };
        if (["lorom", "hirom"].includes(id)) mapping = { id, copier_header: Number(read("address-prefix")) };
        if (id === "declared-window") mapping = { id, cpu_start: Number(read("address-window")), file_offset: Number(read("address-file")), length: Number(read("address-window-length")) };
        return keep("systems.address", { system_id, address: Number(read("cpu-address")), mapping, bank: read("address-bank").trim() ? Number(read("address-bank")) : null }, "debugAddress");
      },
      "compare-bytes": () => ctx2.run("resources.compare", { ...ctx2.sourceParams(), other_id: read("compare-other"), offset: Number(read("compare-offset")), length: Number(read("compare-length")) }),
      "memory-read": () => ctx2.run("runtime.memory", { ...ctx2.projectParams(), region: Number(read("memory-region")), offset: Number(read("memory-offset")), length: Number(read("memory-length")) }),
      "debug-inspect": () => ctx2.run("debug.inspect", { ...ctx2.sourceParams(), case: json("debug-case"), trace: json("debug-trace") }),
      "debug-observe": () => ctx2.run("debug.observe", { ...ctx2.sourceParams(), case: json("debug-case"), trace: json("debug-trace"), runtime: json("debug-runtime") })
    });
    const result = state2.results["debug.observe"] || state2.results["debug.inspect"];
    const investigation = await investigationSeries(ctx2);
    if (!current2()) return "";
    return `${heading("", "Investigation", "")}${investigation}<details class="card"><summary>Additional memory tools</summary>${valueFinder(ctx2)}${memoryWatches(ctx2)}</details>${hardwareReference(ctx2)}<section class="card"><h3>Declared references</h3>${field("uses-offset", "Target file offset", ctx2.draft("uses-offset", "0"))}${button("Find declared references", "uses-read")}${(references == null ? void 0 : references.ok) ? `<div>${references.uses.map((row) => `<div class="actions"><span>${esc(row.name)} · ${esc(row.kind)}</span>${button("Inspect0x" + row.offset.toString(16), "uses-open", { id: String(row.offset) })}</div>`).join("") || "<p>No declared references to this offset.</p>"}<p class="subtle">${references.partial ? "Partial scan (first4,096 table records)." : "Undeclared uses remain unknown."}</p></div>` : ""}</section><div class="grid-even"><section class="card"><h3>Address explorer</h3>${select("address-system", "System", [["nes", "NES"], ["snes", "SNES"], ["genesis", "Genesis"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]], ctx2.draft("address-system", state2.artifact.system_id || "nes"))}${field("cpu-address", "CPU address", ctx2.draft("cpu-address", "0x8000"))}${select("address-mapping", "Declared mapping", [["nrom", "NES NROM"], ["prg-bank", "NES explicit PRG bank"], ["lorom", "SNES LoROM"], ["hirom", "SNES HiROM"], ["linear", "Genesis linear"], ["gb-rom", "Game Boy explicit ROM bank"], ["rom", "GBA ROM windows"]], ctx2.draft("address-mapping", { nes: "nrom", snes: "lorom", genesis: "linear", gb: "gb-rom", gbc: "gb-rom", gba: "rom" }[state2.artifact.system_id] || "nrom"))}<details class="config"><summary>Mapping bounds</summary><div class="field-row">${field("address-bank", "Explicit bank (optional)", ctx2.draft("address-bank", ""))}${field("address-prg", "PRG file offset", ctx2.draft("address-prg", "16"))}${field("address-prg-size", "NROM PRG bytes", ctx2.draft("address-prg-size", "16384"))}${field("address-bank-size", "Bank bytes", ctx2.draft("address-bank-size", "8192"))}${field("address-window", "CPU window start", ctx2.draft("address-window", "0x8000"))}${field("address-prefix", "Copier header bytes", ctx2.draft("address-prefix", "0"))}${field("address-file", "Loaded-file offset", ctx2.draft("address-file", "0"))}${field("address-window-length", "Loaded-file bytes", ctx2.draft("address-window-length", "8192"))}</div></details>${button("Resolve address", "address-resolve", { primary: true })}${resolved ? button("Inspect mapped bytes", "address-open") + '<p class="subtle">Declared mapping only; active bank state was not observed.</p>' : ""}${report(mapped, "Mapped bytes")}</section><section class="card"><h3>Compare bytes</h3>${select("compare-other", "Compare selected source with", [...state2.project.sources, ...state2.project.builds].filter((r) => r.artifact_id !== state2.artifact.artifact_id).map((r) => [r.artifact_id, r.name]), ctx2.draft("compare-other", ""))}<div class="field-row">${field("compare-offset", "File offset", ctx2.draft("compare-offset", "0"))}${field("compare-length", "Bytes", ctx2.draft("compare-length", "256"))}</div>${button("Compare range", "compare-bytes")}${report(state2.results["resources.compare"], "Byte differences")}<h3>Native memory</h3><div class="field-row">${select("memory-region", "Region", [["2", "System RAM"], ["3", "Video RAM"], ["0", "Save RAM"]], ctx2.draft("memory-region", "2"))}${field("memory-offset", "Region offset", ctx2.draft("memory-offset", "0"))}${field("memory-length", "Bytes to observe", ctx2.draft("memory-length", "32"))}</div>${button("Capture memory snapshot", "memory-read", { disabled: !state2.runtime })}${report(state2.results["runtime.memory"], "Measured memory")}</section></div><details class="card"><summary>Advanced trace case</summary><div class="grid-two"><section class="card"><div class="card-heading"><h3>Case workspace</h3>${badge("EXPLICIT MAPPINGS")}</div><p class="subtle">Import your revision-bound case and trace JSON below. A bank or address space that has not been established stays unresolved.</p>${jsonEditor("debug-case", "Troubleshooting case", ctx2.draft("debug-case", "{}"), false)}${jsonEditor("debug-trace", "Explicit imported trace", ctx2.draft("debug-trace", "{}"), false)}<div class="actions">${button("Inspect case & source", "debug-inspect", { primary: true, icon: "debug" })}</div><div class="notice">Imported reads and writes are candidates. They do not establish an emulator write event or prove causation.</div></section><section class="card"><h3>Native observations</h3><p class="subtle">Use a fresh owned worker to compare declared memory probes before and after real controller input.</p>${jsonEditor("debug-runtime", "Observation configuration", ctx2.draft("debug-runtime", JSON.stringify({ load: {}, steps: [{ frames: 1, buttons: [], port: 0 }], initial_state_file: null, timeout: 30, frame_region: [0, 0, 1, 1], memory_probe_ids: [] }, null, 2)), true)}${button("Observe in native worker", "debug-observe", { icon: "playtest" })}<div class="notice warm">Memory snapshots are bounded observations. A changed value alone does not show which instruction wrote it.</div>${(result == null ? void 0 : result.probes) ? `<div class="table-wrap"><table><thead><tr><th>Probe</th><th>Resolution</th><th>Source bytes</th></tr></thead><tbody>${result.probes.map((p) => {
      var _a2;
      return `<tr><td>${esc(p.probe_id)}</td><td>${esc(p.status)}</td><td><code>${esc(((_a2 = p.source) == null ? void 0 : _a2.raw_hex) || "Unresolved")}</code></td></tr>`;
    }).join("")}</tbody></table></div>` : ""}</section></div></details>${report(state2.results["debug.inspect"], "Case inspection")}${report(state2.results["debug.observe"], "Measured before & after")}`;
  }
  function mount7(ctx2) {
    mountValueFinder(ctx2);
  }

  // romancer/ui/views/routes.js
  var routes_exports = {};
  __export(routes_exports, {
    render: () => render11
  });

  // romancer/ui/route_controls.js
  var familyOptions = [["nes", "NES"], ["snes", "SNES"], ["genesis", "Genesis"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]];
  function selection() {
    return { kind: "artifact", id: read("route-content") };
  }
  function assertion() {
    const kind = read("step-assertion");
    if (kind === "none") return null;
    if (kind === "memory_eq") return { kind, region: Number(read("step-region")), offset: Number(read("step-offset")), expected_hex: read("step-hex").replace(/\s/g, "").toLowerCase() };
    return { kind: "capture_sha256", sha256: read("step-capture").trim() };
  }
  async function routeStudio(ctx2, example) {
    var _a, _b, _c;
    const { state: state2 } = ctx2, definitions2 = (await ctx2.api.call("routes.list", ctx2.projectParams())).routes;
    let route;
    try {
      route = JSON.parse(ctx2.draft("route-json", JSON.stringify(example)));
    } catch {
      route = example;
    }
    const steps2 = route.steps || [];
    const saveLocal = async (value) => {
      ctx2.setDraft("route-json", JSON.stringify(value, null, 2));
      state2.savedRoute = null;
      await ctx2.render();
    };
    const configured = async () => {
      const selected2 = selection(), operation = "route.run_profile";
      const result = await ctx2.run(operation, { ...ctx2.projectParams(), artifact_id: selected2.id, system_id: read("route-system"), route: json("route-json"), timeout: Number(read("route-timeout")), initial_state: null }, { render: false });
      state2.results["route.run"] = result;
      await ctx2.render();
    };
    ctx2.use({
      "route-run": configured,
      "route-add-step": () => {
        const current2 = json("route-json"), check = assertion();
        current2.steps.push({ frames: Number(read("step-frames")), buttons: read("step-buttons").split(",").map((v) => v.trim()).filter(Boolean), port: Number(read("step-port")), assertions: check ? [check] : [], transition: null, checkpoint: read("step-checkpoint") === "yes" });
        return saveLocal(current2);
      },
      "route-remove-step": (node) => {
        const current2 = json("route-json");
        current2.steps.splice(Number(node.dataset.id), 1);
        return saveLocal(current2);
      },
      "route-set-assertion": () => {
        const current2 = json("route-json"), index = Number(read("step-index")), check = assertion();
        if (!current2.steps[index] || !check) throw new Error("Choose a step and an assertion.");
        current2.steps[index].assertions.push(check);
        return saveLocal(current2);
      },
      "route-preview": async () => {
        const current2 = json("route-json"), result = await ctx2.run("routes.compile", { name: read("route-name"), steps: current2.steps, max_frames: Number(read("route-max-frames")), max_actions: Number(read("route-max-actions")) }, { render: false });
        ctx2.setDraft("route-json", JSON.stringify(result.route, null, 2));
        await ctx2.render();
      },
      "route-save-definition": async () => {
        const result = await ctx2.run("routes.save", { ...ctx2.projectParams(), selection: selection(), system_id: read("route-system"), route: json("route-json"), initial_state_id: null }, { render: false });
        state2.savedRoute = result;
        ctx2.setDraft("route-definition", result.definition_id);
        await ctx2.render();
      },
      "route-open-definition": async () => {
        const result = await ctx2.api.call("routes.get", { ...ctx2.projectParams(), definition_id: read("route-definition") });
        state2.savedRoute = result;
        ctx2.setDraft("route-definition", result.definition_id);
        ctx2.setDraft("route-json", JSON.stringify(result.route, null, 2));
        ctx2.setDraft("route-system", result.system_id);
        await ctx2.render();
      },
      "route-replay-definition": async () => {
        const definition_id = read("route-definition");
        if (!definition_id) throw new Error("Choose a saved route.");
        const result = await ctx2.run("routes.run_saved", { ...ctx2.projectParams(), definition_id, selection: selection(), use_checkpoint: read("route-start") === "checkpoint", timeout: Number(read("route-timeout")) }, { render: false });
        state2.results["route.run"] = result;
        await ctx2.render();
      },
      "route-record-start": async () => {
        state2.recordingRoute = await ctx2.run("routes.record_start", { ...ctx2.projectParams(), system_id: read("route-system"), name: read("route-name") }, { render: false });
        await ctx2.render();
      },
      "route-record-capture": () => ctx2.run("routes.record_capture", ctx2.projectParams()),
      "route-record-memory": () => ctx2.run("routes.record_memory", { ...ctx2.projectParams(), region: Number(read("step-region")), offset: Number(read("step-offset")), length: Number(read("step-length")) }),
      "route-record-stop": async () => {
        const result = await ctx2.run("routes.record_stop", ctx2.projectParams(), { render: false });
        state2.recordingRoute = null;
        state2.savedRoute = result;
        ctx2.setDraft("route-definition", result.definition_id);
        ctx2.setDraft("route-json", JSON.stringify(result.route, null, 2));
        ctx2.notify(result.complete ? "Recorded route saved." : "Inputs saved. Add an assertion before replay.");
        await ctx2.render();
      }
    });
    return `<section class="card"><h3>Routes</h3><div class="field-row">${select("route-system", "Saved system setup", familyOptions, ctx2.draft("route-system", ((_a = state2.artifact) == null ? void 0 : _a.system_id) || "nes"))}${select("route-content", "Content", [...state2.artifact ? [[state2.artifact.artifact_id, state2.artifact.name]] : []], ctx2.draft("route-content", ((_b = state2.artifact) == null ? void 0 : _b.artifact_id) || ""))}${field("route-name", "Route name", ctx2.draft("route-name", route.id || "My route"))}</div><div class="actions">${button("Record playtest inputs", "route-record-start", { disabled: !state2.runtime || !!state2.recordingRoute })}${button("Open playtest", "navigate", { id: "playtest" })}${state2.recordingRoute ? button("Add current frame assertion", "route-record-capture") + button("Stop & save recording", "route-record-stop", { primary: true }) : ""}</div><div class="field-row">${select("route-definition", "Saved route", [["", "Choose a route"], ...definitions2.map((d) => [d.definition_id, d.name + " · " + d.steps + " steps" + (d.complete ? "" : " · draft")])], ctx2.draft("route-definition", ((_c = state2.savedRoute) == null ? void 0 : _c.definition_id) || ""))}${select("route-start", "Replay start", [["cold", "Cold start"], ["checkpoint", "Recorded checkpoint"]], ctx2.draft("route-start", "cold"))}</div><div class="actions">${button("Open definition", "route-open-definition", { disabled: !definitions2.length })}${button("Replay saved route", "route-replay-definition", { primary: true, disabled: !definitions2.length })}${button("Save as cold-start test", "route-save-definition")}</div>
<details class="config"><summary>Edit route steps</summary><div class="table-wrap"><table><thead><tr><th>Step</th><th>Frames</th><th>Input</th><th>Assertions</th><th></th></tr></thead><tbody>${steps2.map((s, i) => `<tr><td>${i + 1}</td><td>${s.frames}</td><td>${esc(s.buttons.join(", ") || "None")}</td><td>${s.assertions.length}</td><td>${button("Remove", "route-remove-step", { id: String(i) })}</td></tr>`).join("")}</tbody></table></div><div class="field-row">${field("step-frames", "Frames", ctx2.draft("step-frames", "60"))}${field("step-buttons", "Buttons (comma separated)", ctx2.draft("step-buttons", ""))}${field("step-port", "Controller port", ctx2.draft("step-port", "0"))}${select("step-checkpoint", "Save checkpoint after step", [["no", "No"], ["yes", "Yes"]], ctx2.draft("step-checkpoint", "no"))}${select("step-assertion", "Assertion", [["none", "None"], ["memory_eq", "Exact memory bytes"], ["capture_sha256", "Exact frame hash"]], ctx2.draft("step-assertion", "none"))}${field("step-region", "Memory region", ctx2.draft("step-region", "2"))}${field("step-offset", "Memory offset", ctx2.draft("step-offset", "0"))}${field("step-hex", "Expected bytes", ctx2.draft("step-hex", ""))}${field("step-capture", "Expected frame SHA-256", ctx2.draft("step-capture", ""))}${field("step-index", "Existing step index (starts at0)", ctx2.draft("step-index", "0"))}${field("step-length", "Bytes for live assertion", ctx2.draft("step-length", "1"))}</div><div class="actions">${button("Add step", "route-add-step")}${button("Add assertion to step", "route-set-assertion")}${state2.recordingRoute ? button("Record current memory assertion", "route-record-memory") : ""}</div><div class="field-row">${field("route-max-frames", "Maximum frames", ctx2.draft("route-max-frames", route.max_frames || 6e3))}${field("route-max-actions", "Maximum actions", ctx2.draft("route-max-actions", route.max_actions || 100))}</div><div class="actions">${button("Review route", "route-preview")}${button("Save definition", "route-save-definition")}</div></details>${report(state2.results["routes.compile"], "Route review")}</section>`;
  }

  // romancer/ui/views/routes.js
  var exampleRoute = { schema_version: 1, id: "my-route", max_frames: 600, max_actions: 10, steps: [{ frames: 60, buttons: [], port: 0, assertions: [], transition: null, checkpoint: false }] };
  async function render11(ctx2) {
    var _a;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    const reports = (await ctx2.api.call("reports.list", ctx2.projectParams())).reports, routeReports = reports.filter((r) => r.kind === "route");
    ctx2.use({
      "route-run": () => {
        if (!state2.artifact) throw new Error("Select a game source first.");
        return ctx2.run("route.run", { ...ctx2.sourceParams(), core: read("route-core"), options: json("route-options"), route: json("route-json"), timeout: Number(read("route-timeout")), initial_state: null });
      },
      "coverage-build": () => ctx2.run("coverage.build", { ...ctx2.projectParams(), evidence_ids: [...document.querySelectorAll('[name="coverage-evidence"]:checked')].map((n) => n.value), objectives: json("coverage-objectives") }),
      "battle-analyze": () => {
        const config = json("battle-config");
        return ctx2.run("battle.analyze", { profile: config.profile, observations: config.observations, budget: config.budget }, { refresh: false });
      }
    });
    const coverage = state2.results["coverage.build"];
    return `${heading("Routes & coverage", "Routes", "Execute actual controller input and assertions. Build coverage from authenticated route records.")}${await routeStudio(ctx2, exampleRoute)}<div class="grid-even"><section class="card"><div class="card-heading"><h3>Route replay</h3>${badge("NATIVE INPUT")}</div>${field("route-timeout", "Execution deadline (seconds)", ctx2.draft("route-timeout", "30"), { type: "number", min: 1 })}${jsonEditor("route-json", "Advanced route definition", ctx2.draft("route-json", JSON.stringify(exampleRoute, null, 2)), false)}${button("Execute route", "route-run", { primary: true, icon: "playtest", disabled: !state2.artifact })}<div class="notice">A route needs an exact memory or frame assertion.</div></section><section class="card"><div class="card-heading"><h3>Progression coverage</h3><span class="subtle">${routeReports.length} route records</span></div><div class="checklist">${routeReports.length ? routeReports.map((r) => `<label><input type="checkbox" name="coverage-evidence" value="${r.evidence_id}" ${r.status === "PASS" ? "checked" : ""}>${esc(r.route_id || r.evidence_id.slice(0, 8))} ${badge(r.status, r.status === "PASS" ? "good" : "warm")}</label>`).join("") : '<p class="subtle">Execute a route to create selectable evidence.</p>'}</div>${jsonEditor("coverage-objectives", "Required, optional & ending objectives", ctx2.draft("coverage-objectives", JSON.stringify({ required: [], optional: [], endings: [], unknown_edges: [] }, null, 2)), true)}${button("Build coverage graph", "coverage-build", { icon: "routes" })}<div class="notice">Unvisited, optional, ending, and unknown objectives are reported separately. Imported PASS labels cannot grant coverage.</div>${coverage ? `<div class="graph">${((_a = coverage.edges) == null ? void 0 : _a.map((edge) => `<div class="graph-node">${esc(edge.from)} → ${esc(edge.to)}<br><small>${esc(edge.objective)}</small></div>`).join("")) || '<p class="subtle">No measured transition edges.</p>'}</div>` : ""}</section></div><details class="card"><summary>Advanced declared resource model</summary><p class="subtle">Model explicitly declared ranges, equipment, action costs, and retry budgets. Recommendations state their assumptions.</p>${jsonEditor("battle-config", "Declared battle model", ctx2.draft("battle-config", JSON.stringify({ profile: { schema_version: 1, id: "my-model", semantics: "declared-action-cost-v1", actions: [{ id: "attack", label: "Attack", min_range: 0, max_range: 1, cost: {}, power: 10, accuracy_per_mille: 1e3 }] }, observations: [{ kind: "resources", values: {} }, { kind: "range", value: 1 }, { kind: "equipment", bonuses: {} }], budget: { retries_used: 0, max_retries: 3, failures_used: 0, max_failures: 2 } }, null, 2)))}${button("Analyze declared actions", "battle-analyze")}</details>${visualFailures(state2.results["route.run"])}${report(state2.results["route.run"], "Executed route")}${report(coverage, "Coverage findings")}${report(state2.results["battle.analyze"], "Action recommendations")}`;
  }

  // romancer/ui/views/regression.js
  var regression_exports = {};
  __export(regression_exports, {
    render: () => render12
  });
  async function render12(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    const definitions2 = (await ctx2.api.call("routes.list", ctx2.projectParams())).routes.filter((r) => r.complete);
    const reports = (await ctx2.api.call("reports.list", ctx2.projectParams())).reports.filter((r) => r.kind === "route");
    const suiteDefinitions = definitions2.filter((row) => !row.initial_state_id), artifacts = [...state2.project.sources, ...state2.project.builds], suite = state2.results["regression.run_suite"];
    ctx2.use({
      "suite-run": () => ctx2.run("regression.run_suite", { ...ctx2.projectParams(), source_id: read("suite-source"), target_id: read("suite-target"), definition_ids: [...document.querySelectorAll('[name="suite-route"]:checked')].map((node) => node.value), timeout: Number(read("suite-timeout")) }),
      "bisect-add-change": () => {
        const changes = JSON.parse(ctx2.draft("bisect-changes", "[]"));
        changes.push({ offset: Number(read("bisect-offset")), before: read("bisect-before").replace(/\s/g, "").toLowerCase(), after: read("bisect-after").replace(/\s/g, "").toLowerCase() });
        ctx2.setDraft("bisect-changes", JSON.stringify(changes));
        return ctx2.render();
      },
      "bisect-clear": () => {
        ctx2.setDraft("bisect-changes", "[]");
        return ctx2.render();
      },
      "bisect-saved": async () => {
        const definition = await ctx2.api.call("routes.get", { ...ctx2.projectParams(), definition_id: read("bisect-route") });
        return ctx2.run("regression.bisect_profile", { ...ctx2.sourceParams(), system_id: read("bisect-system"), route: definition.route, changes: JSON.parse(ctx2.draft("bisect-changes", "[]")), budget: { max_evaluations: Number(read("bisect-evaluations")) }, timeout: Number(read("bisect-timeout")) });
      },
      "regression-compare": () => ctx2.run("regression.compare", { ...ctx2.projectParams(), baseline_id: read("baseline-id"), candidate_id: read("candidate-id") }),
      "regression-bisect": () => {
        if (!state2.artifact) throw new Error("Select a source first.");
        const config = json("bisect-config");
        return ctx2.run("regression.bisect", { ...ctx2.sourceParams(), ...config });
      }
    });
    const evidenceSelect = (id, label) => `<label class="field"><span>${label}</span><select id="${id}"><option value="">Select a completed route</option>${reports.map((r) => `<option value="${r.evidence_id}">${esc(r.route_id || "Route")} · ${esc(r.status)} · ${r.evidence_id.slice(0, 8)}</option>`).join("")}</select></label>`;
    return `${heading("Change-focused regression", "Regression", "Compare recorded runs under matching routes and cores, or localize a reproducible failing edit.")}<section class="card"><h3>Run a regression suite</h3><div class="field-row">${select("suite-source", "Original / baseline", artifacts.map((row) => [row.artifact_id, row.name]), ctx2.draft("suite-source", (_a = state2.project.sources[0]) == null ? void 0 : _a.artifact_id))}${select("suite-target", "Build to test", state2.project.builds.map((row) => [row.artifact_id, row.name]), ctx2.draft("suite-target", ((_b = state2.artifact) == null ? void 0 : _b.kind) === "build" ? state2.artifact.artifact_id : (_c = state2.project.builds.at(-1)) == null ? void 0 : _c.artifact_id))}${field("suite-timeout", "Seconds per run (1–30)", ctx2.draft("suite-timeout", "15"), { type: "number", min: 1 })}</div><div class="suite-routes">${suiteDefinitions.length ? suiteDefinitions.map((row) => `<label><input type="checkbox" name="suite-route" value="${esc(row.definition_id)}"> ${esc(row.name)} · ${esc(row.system_id)}</label>`).join("") : "<p>Save a cold-start route with frame or memory assertions to create a test.</p>"}</div><div class="actions">${button("Run suite", "suite-run", { primary: true, disabled: !suiteDefinitions.length || !state2.project.builds.length })}${button("Create or record test routes", "navigate", { id: "routes" })}</div><p class="subtle">Choose up to8 tests. Each runs on the original and build in fresh workers. A failing baseline stays inconclusive. Total limit:120 seconds.</p></section>${(suite == null ? void 0 : suite.project_id) === state2.project.project_id ? `<section class="card"><div class="card-heading"><h3>Suite results</h3>${badge(suite.status, suite.status === "PASS" ? "good" : "warm")}</div><p>${esc(((_d = artifacts.find((row) => row.artifact_id === suite.source_id)) == null ? void 0 : _d.name) || suite.source_sha256)} → ${esc(((_e = artifacts.find((row) => row.artifact_id === suite.target_id)) == null ? void 0 : _e.name) || suite.target_sha256)}</p><p>${suite.counts.passed} passed · ${suite.counts.regression} regressions · ${suite.counts.inconclusive} inconclusive</p><div class="table-wrap"><table><thead><tr><th>Test</th><th>Baseline</th><th>Build</th><th>Result</th></tr></thead><tbody>${suite.tests.map((row) => `<tr><td>${esc(row.name)}</td><td>${esc(row.baseline_status || "Not completed")}</td><td>${esc(row.candidate_status || "Not run")}</td><td>${badge(row.status, row.status === "PASS" ? "good" : "warm")}${row.reason ? `<p>${esc(row.reason)}</p>` : ""}</td></tr>`).join("")}</tbody></table></div><p class="subtle">Selected assertions only. Untested gameplay remains unknown.</p></section>` : ""}${await suitePictures(ctx2, suite)}<div class="grid-even"><section class="card"><div class="card-heading"><h3>Compare route runs</h3>${badge("STORED EVIDENCE")}</div>${evidenceSelect("baseline-id", "Baseline run")}${evidenceSelect("candidate-id", "Candidate run")}${button("Compare recorded outcomes", "regression-compare", { primary: true, icon: "regression", disabled: reports.length < 2 })}<div class="notice">Different routes or core revisions produce an inconclusive comparison. The source revision may differ because this is a change comparison.</div></section><section class="card"><h3>Reproduce & bisect</h3>${select("bisect-system", "Saved system setup", [["nes", "NES"], ["snes", "SNES"], ["genesis", "Genesis"], ["gb", "Game Boy"], ["gbc", "Game Boy Color"], ["gba", "GBA"]], ctx2.draft("bisect-system", ((_f = state2.artifact) == null ? void 0 : _f.system_id) || "nes"))}${select("bisect-route", "Assertion route", definitions2.map((d) => [d.definition_id, d.name]), ctx2.draft("bisect-route", (_g = definitions2[0]) == null ? void 0 : _g.definition_id))}<div class="field-row">${field("bisect-offset", "Edit offset", ctx2.draft("bisect-offset", "0"))}${field("bisect-before", "Expected bytes", ctx2.draft("bisect-before", ""))}${field("bisect-after", "Replacement bytes", ctx2.draft("bisect-after", ""))}${field("bisect-evaluations", "Maximum evaluations", ctx2.draft("bisect-evaluations", "16"))}${field("bisect-timeout", "Seconds per run", ctx2.draft("bisect-timeout", "30"))}</div><div class="actions">${button("Add candidate edit", "bisect-add-change")}${button("Clear edits", "bisect-clear")}</div><pre>${esc(ctx2.draft("bisect-changes", "[]"))}</pre>${button("Test & narrow edits", "bisect-saved", { disabled: !state2.artifact || !definitions2.length, primary: true })}<p class="subtle">Evaluate subsets of fixed byte edits by rebuilding and actually running the declared route. The empty baseline must pass and the full set must fail.</p>${jsonEditor("bisect-config", "Advanced bisection configuration", ctx2.draft("bisect-config", JSON.stringify({ core: readPreference("romancer-core") || "", options: {}, route: {}, changes: [], budget: { max_evaluations: 16 }, timeout: 30 }, null, 2)), false)}${button("Run bounded bisection", "regression-bisect", { icon: "regression", disabled: !state2.artifact })}<div class="notice warm">Every evaluation uses an owned worker and creates evidence. Cancellation stops further subsets; completed build outputs remain inspectable.</div></section></div>${report(state2.results["regression.compare"], "Run comparison")}${report(state2.results["regression.bisect_profile"] || state2.results["regression.bisect"], "Reproduced failing subset")}`;
  }

  // romancer/ui/views/release.js
  var release_exports = {};
  __export(release_exports, {
    mount: () => mount8,
    render: () => render13
  });

  // romancer/ui/patch_controls.js
  function canApplyPatch(state2, preview) {
    var _a, _b, _c;
    return !!((preview == null ? void 0 : preview.ok) && preview.plan_id && preview.changed_bytes > 0 && preview.project_id === ((_a = state2.project) == null ? void 0 : _a.project_id) && preview.source_id === ((_b = state2.artifact) == null ? void 0 : _b.artifact_id) && preview.source_sha256 === ((_c = state2.artifact) == null ? void 0 : _c.sha256));
  }
  async function preparePatch(ctx2, file, expectedReference) {
    if (!ctx2.state.project || !ctx2.state.artifact) throw new Error("Select the original ROM in the top bar first.");
    if (!file) throw new Error("Choose a BPS or IPS patch first.");
    const scope = selectionKey(ctx2.state), project_id = ctx2.state.project.project_id, artifact_id = ctx2.state.artifact.artifact_id, request2 = (ctx2.state.patchRequest || 0) + 1;
    ctx2.state.patchRequest = request2;
    const current2 = () => selectionKey(ctx2.state) === scope && ctx2.state.patchRequest === request2;
    const input = await ctx2.api.uploadInput(project_id, file, "patch");
    if (!current2()) throw new Error("The selected file or ROM changed. Preview the patch for the new selection.");
    const preview = await ctx2.run("patches.preview", { project_id, artifact_id, input_id: input.input_id, expected_reference: expectedReference }, { render: false });
    if (!current2()) throw new Error("The selection changed while the patch was checked. Preview it again.");
    ctx2.state.patchImport = { scope, input, preview, file };
    return preview;
  }
  function patchControls(ctx2) {
    var _a, _b;
    const { state: state2 } = ctx2, scope = selectionKey(state2), selected2 = ((_a = state2.patchImport) == null ? void 0 : _a.scope) === scope ? state2.patchImport : null, preview = selected2 == null ? void 0 : selected2.preview;
    ctx2.use({
      "patch-preview": async () => {
        var _a2, _b2;
        const file = ((_a2 = document.getElementById("patch-file")) == null ? void 0 : _a2.files[0]) || (((_b2 = state2.patchFile) == null ? void 0 : _b2.scope) === scope ? state2.patchFile.file : null) || (selected2 == null ? void 0 : selected2.file);
        await preparePatch(ctx2, file, read("patch-reference"));
        await ctx2.render();
      },
      "patch-apply": async () => {
        const saved = state2.patchImport;
        if ((saved == null ? void 0 : saved.scope) !== selectionKey(state2) || !canApplyPatch(state2, saved.preview)) throw new Error("Preview the patch against this exact ROM first.");
        const ticket = selectionKey(state2), result = await ctx2.run("patches.apply", { project_id: state2.project.project_id, plan_id: saved.preview.plan_id, name: read("patch-build-name") }, { render: false });
        if (ticket !== selectionKey(state2)) return;
        state2.patchImport = null;
        await ctx2.refreshProject();
        await ctx2.setArtifact(result.artifact_id);
        ctx2.notify("Patched build created. Your original is unchanged.");
        await ctx2.navigate("playtest");
      }
    });
    return `<section class="card" id="patch-import"><h3>Apply a downloaded patch</h3><p>Selected original: <strong>${esc(((_b = state2.artifact) == null ? void 0 : _b.name) || "Choose a ROM in the top bar")}</strong></p>
 ${fileInput("patch-file", "Patch file — choose or drop a BPS / IPS patch", ".bps,.ips")}${selected2 ? `<p>${esc(selected2.input.name)}</p>` : ""}
 ${field("patch-reference", "Expected original CRC32 or SHA256 (required for IPS)", ctx2.draft("patch-reference", ""), { hint: "Use the full-file checksum supplied by the patch author. BPS also checks its embedded checksums." })}
 <div class="actions">${button("Preview patch", "patch-preview", { primary: !preview, disabled: !state2.artifact })}</div>
 ${preview ? `<div class="notice">${badge(preview.format)} ${size(preview.target_size)} · ${preview.changed_bytes.toLocaleString()} changed bytes<p>${esc(preview.reference)}</p></div>
 ${preview.changed_bytes ? `${field("patch-build-name", "New build name", ctx2.draft("patch-build-name", "Patched build"))}${button("Create patched build", "patch-apply", { primary: true, disabled: !canApplyPatch(state2, preview) })}` : "<p>This patch makes no changes to the selected file.</p>"}
 <details><summary>Changed ranges and identities</summary><p>Original SHA256: <code>${esc(preview.source_sha256)}</code></p><p>Target SHA256: <code>${esc(preview.target_sha256)}</code></p><ul>${(preview.ranges || []).map((r) => `<li>0x${r.offset.toString(16)} · ${r.length} bytes</li>`).join("")}</ul>${preview.ranges_truncated ? "<p>More changed ranges exist; the total byte count includes them.</p>" : ""}</details>` : '<p class="subtle">Preview first. Applying creates a separate build.</p>'}</section>`;
  }
  function mountPatchControls(ctx2) {
    var _a, _b;
    const root = document.getElementById("patch-import");
    if (!root) return;
    const invalidate = (file) => {
      ctx2.state.patchRequest = (ctx2.state.patchRequest || 0) + 1;
      if (file) ctx2.state.patchFile = { scope: selectionKey(ctx2.state), file };
      if (ctx2.state.patchImport) ctx2.state.patchImport.preview = null;
      const button2 = root.querySelector('[data-action="patch-apply"]');
      if (button2) button2.disabled = true;
    };
    (_a = root.querySelector("#patch-file")) == null ? void 0 : _a.addEventListener("change", (event) => invalidate(event.target.files[0]));
    (_b = root.querySelector("#patch-reference")) == null ? void 0 : _b.addEventListener("input", () => invalidate());
    root.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    root.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer.files.length !== 1) {
        ctx2.notify("Drop one BPS or IPS patch at a time.", true);
        return;
      }
      const file = event.dataTransfer.files[0];
      invalidate(file);
      const label = document.createElement("p");
      label.textContent = "Selected patch: " + file.name;
      root.querySelector("#patch-file").closest("label").append(label);
    });
  }

  // romancer/ui/views/release.js
  async function render13(ctx2) {
    var _a;
    const { state: state2 } = ctx2, missing = requireProject(ctx2);
    if (missing) return missing;
    const p = state2.project, exports = (await ctx2.api.call("exports.list", ctx2.projectParams())).exports;
    ctx2.use({
      "release-patch": () => ctx2.run("release.prepare", { ...ctx2.projectParams(), source_id: read("release-source"), target_id: read("release-target"), title: read("release-title"), description: read("release-description") }),
      "release-verify": (node) => ctx2.run("release.verify", { ...ctx2.projectParams(), source_id: read("release-source"), export_id: node.dataset.id }),
      "release-disc": () => ctx2.run("release.disc_set", { ...ctx2.projectParams(), source_id: read("disc-release-source"), target_id: read("disc-release-target"), title: read("release-title") }),
      "release-apply-set": () => ctx2.run("release.apply_set", { source_cue: read("set-original"), archive: read("set-archive"), destination: read("set-destination") }),
      "release-package": () => ctx2.run("release.package", { ...ctx2.projectParams(), export_ids: [...document.querySelectorAll('[name="release-export"]:checked')].map((n) => n.value), title: read("release-title") }),
      "walkthrough-export": () => ctx2.run("docs.walkthrough", { ...ctx2.projectParams(), evidence_id: read("walkthrough-id"), annotations: json("walkthrough-annotations") })
    });
    return `${heading("Release preparation", "Export", "Generate a BPS patch, apply it independently to the exact original, and package selected public artifacts.")}${patchControls(ctx2)}<div class="grid-two"><section class="card"><div class="card-heading"><h3>Prepare a verified patch</h3>${badge("BPS1", "good")}</div><div class="field-row">${select2("release-source", "Original revision", p.sources)}${select2("release-target", "Target build", p.builds)}</div>${field("release-title", "Release title", ctx2.draft("release-title", p.name))}${field("release-description", "Release notes", ctx2.draft("release-description", ""))}<div class="notice">BPS carries source, target, and patch checksums. ROMancer also binds SHA-256 identities and verifies the target with a separate decoder.</div>${button("Create & independently verify patch", "release-patch", { primary: true, icon: "shield", disabled: !p.sources.length || !p.builds.length })}<p class="subtle small">Images up to 8 GiB. Complete reconstruction is checked before export.</p></section><section class="card"><h3>Release selection</h3><p class="subtle">Only approved patch and text roles can enter a release package. Game images, saves, runtime captures, and private reports are excluded.</p><div class="checklist">${exports.filter((e) => ["patch", "documentation", "credits", "notice"].includes(e.role)).map((e) => `<label><input type="checkbox" name="release-export" value="${e.export_id}" checked>${esc(e.role)} · ${size(e.size)} · ${short(e.sha256)}</label>`).join("") || '<p class="subtle">Prepare a patch or export documentation first.</p>'}</div><div class="actions">${button("Package selected exports", "release-package", { icon: "release", disabled: !exports.some((e) => ["patch", "documentation", "credits", "notice"].includes(e.role)) })}</div><div class="notice">Default credit<br><strong>By RetchEWretched</strong></div></section></div><section class="card"><div class="card-heading"><h3>Prepared exports</h3><span class="subtle">${exports.length} artifacts</span></div>${exports.length ? `<div class="table-wrap"><table><thead><tr><th>Artifact</th><th>Role</th><th>Size</th><th>Identity</th><th>Actions</th></tr></thead><tbody>${exports.map((e) => `<tr><td>${esc(e.name)}</td><td>${badge(e.role)}</td><td>${size(e.size)}</td><td><code>${short(e.sha256)}</code></td><td><div class="actions">${button("Download", "download", { id: e.export_id, name: e.name, icon: "download" })}${e.role === "patch" ? button("Verify", "release-verify", { id: e.export_id, icon: "shield" }) : ""}</div></td></tr>`).join("")}</tbody></table></div>` : empty("Your first release starts with a build", "Edit a source and create a separate build, then return here to prepare its patch.")}</section><section class="card"><h3>Walkthrough documentation</h3><p class="subtle">Export author annotations for measured objectives. Unknown directions retain an explicit uncertainty label.</p>${field("walkthrough-id", "Stored coverage evidence ID", ctx2.draft("walkthrough-id", ((_a = state2.results["coverage.build"]) == null ? void 0 : _a.evidence_id) || ""))}${jsonEditor("walkthrough-annotations", "Player-facing objective annotations", ctx2.draft("walkthrough-annotations", "{}"))}${button("Export walkthrough", "walkthrough-export", { icon: "download" })}</section><details class="card"><summary>Disc patch sets (advanced)</summary><div class="field-row">${containerSelect("disc-release-source", "Original set", p.containers || [])}${containerSelect("disc-release-target", "Built set", p.containers || [])}</div>${button("Create verified patch set", "release-disc", { disabled: (p.containers || []).length < 2 })}${field("set-original", "Original CUE path", ctx2.draft("set-original", ""))}${field("set-archive", "Patch set ZIP", ctx2.draft("set-archive", ""))}${field("set-destination", "New output folder", ctx2.draft("set-destination", ""))}${button("Apply & verify complete set", "release-apply-set")}</details>${report(state2.results["release.disc_set"], "Disc patch set")}${report(state2.results["release.apply_set"], "Reconstructed set")}${report(state2.results["release.prepare"], "Independent patch verification")}${report(state2.results["release.verify"], "Reverification")}${report(state2.results["release.package"], "Positive-manifest package")}`;
  }
  function select2(id, label, rows) {
    return `<label class="field"><span>${label}</span><select id="${id}">${rows.length ? rows.map((r) => `<option value="${r.artifact_id}">${esc(r.name)} · ${short(r.sha256)}</option>`).join("") : '<option value="">No matching artifact</option>'}</select></label>`;
  }
  function containerSelect(id, label, rows) {
    return `<label class="field"><span>${label}</span><select id="${id}">${rows.map((r) => `<option value="${r.container_id}">${esc(r.name || r.cue || r.container_id)}</option>`).join("")}</select></label>`;
  }
  function mount8(ctx2) {
    mountPatchControls(ctx2);
  }

  // romancer/ui/views/settings.js
  var settings_exports = {};
  __export(settings_exports, {
    mount: () => mount9,
    render: () => render14
  });
  var settingIds = { theme: "settings-theme", scale: "settings-scale", autoDeepScan: "settings-auto-deep-scan", autoGraphics: "settings-auto-graphics", rememberWorkspace: "settings-remember-workspace", volume: "settings-volume", startMuted: "settings-start-muted", loopPreview: "settings-loop-preview", reduceMotion: "settings-reduce-motion", advancedTools: "settings-advanced-tools" };
  async function editorFor(ctx2) {
    if (!ctx2.state.settingsEditor) {
      const editor2 = { values: getSettings(), loaded: false, busy: false, dirty: false, error: "" };
      ctx2.state.settingsEditor = editor2;
      editor2.ready = (async () => {
        try {
          editor2.values = await loadSettings(ctx2.api);
          editor2.loaded = true;
        } catch (error) {
          editor2.error = "Settings could not be loaded: " + error.message;
        }
      })();
    }
    const editor = ctx2.state.settingsEditor;
    await editor.ready;
    return editor;
  }
  function formValues() {
    const result = {};
    for (const [key3, id] of Object.entries(settingIds)) {
      const node = document.getElementById(id);
      if (!node) throw Error("Settings controls are no longer visible. Reopen Settings.");
      result[key3] = typeof DEFAULT_SETTINGS[key3] === "boolean" ? node.checked : typeof DEFAULT_SETTINGS[key3] === "number" ? node.value.trim() ? Number(node.value) : NaN : node.value;
    }
    return result;
  }
  var returnPage = (state2) => state2.settingsReturnPage && state2.settingsReturnPage !== "settings" ? state2.settingsReturnPage : "overview";
  async function submitSettings(ctx2, close) {
    var _a;
    const editor = ctx2.state.settingsEditor;
    if (!editor || editor.busy || !editor.loaded) return;
    try {
      editor.values = formValues();
      editor.busy = true;
      editor.error = "";
      await ctx2.render();
      const saved = await saveSettings(ctx2.api, editor.values);
      editor.values = saved;
      editor.dirty = false;
      editor.busy = false;
      (_a = ctx2.notify) == null ? void 0 : _a.call(ctx2, "Settings saved.");
      if (close) {
        ctx2.state.settingsEditor = null;
        await ctx2.navigate(returnPage(ctx2.state));
      } else await ctx2.render();
    } catch (error) {
      editor.busy = false;
      editor.error = error.message;
      await ctx2.render();
    }
  }
  function checkbox(editor, key3, label, hint = "") {
    return `<label class="settings-check" for="${settingIds[key3]}"><input type="checkbox" id="${settingIds[key3]}" ${editor.values[key3] ? "checked" : ""}><span>${esc(label)}${hint ? `<small>${esc(hint)}</small>` : ""}</span></label>`;
  }
  function settingsForm(editor) {
    const v = editor.values, disabled = editor.busy || !editor.loaded;
    return `<section class="card settings-card"><form id="settings-form"><h2>Preferences</h2><p>Apply saves these preferences for this workspace. OK saves and closes; Cancel discards unapplied changes.</p>${editor.error ? `<div class="notice"><p class="error" role="alert">${esc(editor.error)}</p>${button("Reload saved settings (discard form)", "settings-reload", { disabled: editor.busy })}</div>` : ""}<div class="grid-even"><fieldset class="settings-group"${editor.busy ? " disabled" : ""}><legend>Appearance</legend>${select("settings-theme", "Theme", [["romancer", "ROMancer (default)"], ["dark", "Dark"], ["light", "Light"]], v.theme)}${select("settings-scale", "Interface size", [[100, "100%"], [125, "125%"], [150, "150%"], [200, "200%"]], v.scale)}<p class="subtle">ROMancer keeps the original sea-green appearance.</p>${checkbox(editor, "reduceMotion", "Reduce interface motion")}</fieldset><fieldset class="settings-group"${editor.busy ? " disabled" : ""}><legend>Automatic tasks</legend>${checkbox(editor, "autoDeepScan", "Auto deep scan on ROM load", "Find supported resources when a ROM is opened.")}${checkbox(editor, "autoGraphics", "Inspect gameplay graphics automatically", "Analyze available playtest frames for graphics candidates.")}${checkbox(editor, "rememberWorkspace", "Remember my workspace", "Reopen the last project, ROM, page, and editing position.")}</fieldset><fieldset class="settings-group"${editor.busy ? " disabled" : ""}><legend>Audio</legend><label class="field" for="settings-volume"><span>Volume <output id="settings-volume-value" for="settings-volume">${v.volume}%</output></span><input id="settings-volume" type="range" min="0" max="100" step="1" value="${v.volume}"></label>${checkbox(editor, "startMuted", "Start game audio muted")}${checkbox(editor, "loopPreview", "Loop audio previews")}</fieldset><fieldset class="settings-group"${editor.busy ? " disabled" : ""}><legend>Workspace tools</legend>${checkbox(editor, "advancedTools", "Show advanced tools in navigation", "Keep debugging and engineering tools within easy reach.")}<p class="subtle">Project recovery, system setup, and AI tools remain available below.</p></fieldset></div><div class="actions settings-actions">${button("OK", "settings-ok", { primary: true, disabled })}${button("Apply", "settings-apply", { disabled })}${button("Cancel", "settings-cancel", { disabled: editor.busy })}${button("Restore defaults", "settings-defaults", { disabled: editor.busy })}<span class="subtle" id="settings-form-status" role="status">${editor.busy ? "Saving settings…" : editor.dirty ? "Unapplied changes" : "Preferences apply to this workspace"}</span></div></form></section>`;
  }
  var columns = [["identification", "Identification"], ["raw_inspection", "Inspection"], ["structured_formats", "Declared formats"], ["automatic_resource_discovery", "Resource discovery"], ["runtime_control", "Saved setup"]];
  async function render14(ctx2) {
    var _a, _b;
    const editor = await editorFor(ctx2);
    ctx2.use({ "settings-reload": async () => {
      if (editor.busy) return;
      ctx2.state.settingsEditor = null;
      await ctx2.render();
    }, "settings-apply": () => submitSettings(ctx2, false), "settings-ok": () => submitSettings(ctx2, true), "settings-cancel": async () => {
      if (editor.busy) return;
      ctx2.state.settingsEditor = null;
      await ctx2.navigate(returnPage(ctx2.state));
    }, "settings-defaults": async () => {
      if (editor.busy) return;
      editor.values = { ...DEFAULT_SETTINGS };
      editor.dirty = true;
      editor.error = "";
      await ctx2.render();
    } });
    const agent = (_a = ctx2.state.results) == null ? void 0 : _a["system.agent_config"];
    const c = ctx2.state.capabilities || {}, packs = [...((_b = c.systems) == null ? void 0 : _b.systems) || []].sort((a, b) => Number(b.release_focus) - Number(a.release_focus));
    const setups = Object.fromEntries(await Promise.all(packs.map(async (pack) => {
      try {
        const saved = await ctx2.api.call("profiles.get", { system_id: pack.id });
        if (!saved.profile) return [pack.id, { status: "Choose core", tone: "neutral", reason: "No core is configured in this workspace." }];
        await ctx2.api.call("profiles.validate", { system_id: pack.id });
        return [pack.id, { status: "Ready", tone: "good", reason: saved.engine ? saved.engine + " is included; engine identities checked. Gameplay needs a loaded ROM." : "Core and system-file identities checked. Gameplay needs a loaded ROM." }];
      } catch (error) {
        return [pack.id, { status: "Needs attention", tone: "warm", reason: error.message }];
      }
    })));
    ctx2.use({ "agent-config": () => ctx2.run("system.agent_config", { allow_writes: read("agent-access") === "editing", read_roots: read("agent-rom-root").trim() ? [read("agent-rom-root").trim()] : [] }, { refresh: false }), "agent-copy": async () => {
      if (!(agent == null ? void 0 : agent.configuration)) throw Error("Create a configuration first.");
      await navigator.clipboard.writeText(JSON.stringify(agent.configuration, null, 2));
      ctx2.notify("Agent configuration copied.");
    }, "settings-setup": async (node) => {
      const family = node.dataset.id;
      if (!ctx2.state.project) {
        const project = await ctx2.api.call("project.demo_system", { system_id: family });
        await ctx2.openProject(project.project_id);
      }
      ctx2.state.profileFamily = family;
      ctx2.state.profileLoadedFamily = null;
      await ctx2.navigate("playtest");
    } });
    ctx2.use({ "project-backup": () => ctx2.run("project.backup", { ...ctx2.projectParams(), destination: read("backup-path"), roles: ["sources", "builds", "reports", "sessions", "captures"] }), "project-restore": async () => {
      const result = await ctx2.run("project.restore", { archive: read("restore-path") }, { render: false });
      await ctx2.refreshProject();
      ctx2.notify("Project restored. Select it in the project list.");
      await ctx2.render();
    }, "project-migrate": () => ctx2.run("project.migrate", ctx2.projectParams()), "project-recover": () => ctx2.run("project.recover_lock", ctx2.projectParams()) });
    return `${heading("Settings & capabilities", "Settings", "System formats, configured tools, and measured evidence are reported separately.")}
 ${settingsForm(editor)}<details class="card"><summary>Diagnostics &amp; support</summary>${supportControls(ctx2)}</details><details class="card"><summary>AI & LLM access</summary><p>Connect a local MCP client. Inspection is the default; editing uses the same reviewed plans and separate builds.</p>${select("agent-access", "Agent access", [["inspection", "Inspect only"], ["editing", "Inspect, edit & playtest"]], ctx2.draft("agent-access", "inspection"))}${field("agent-rom-root", "ROM import folder (optional)", ctx2.draft("agent-rom-root", ""))}${button("Create client configuration", "agent-config")}${(agent == null ? void 0 : agent.configuration) ? `<p>${esc(agent.note)}</p><pre>${esc(JSON.stringify(agent.configuration, null, 2))}</pre>${button("Copy configuration", "agent-copy")}` : ""}</details><section class="card"><h3>Getting started</h3><p>Basic and Advanced lessons, at your pace.</p>${button("Open tutorials", "tutorial-hub")}</section><details class="card"><summary>Projects &amp; recovery</summary>${ctx2.state.project ? `${field("backup-path", "Private backup file", ctx2.draft("backup-path", ctx2.state.project.path + "-backup.zip"))}<p class="subtle">Includes source images, builds, saves, captures and reports.</p><div class="actions">${button("Save private backup", "project-backup")}${button("Migrate project", "project-migrate")}${button("Recover abandoned lock", "project-recover")}</div>` : ""}${field("restore-path", "Backup to restore", "", { placeholder: "C:\\Backups\\project.zip" })}${button("Restore project", "project-restore")}</details><details class="card"><summary>Application &amp; system setup</summary><div class="grid-even"><section class="card"><h3>Application</h3><div class="table-wrap"><table><tbody>
 <tr><td>Version</td><td>${esc(c.display_version || c.version)}</td></tr><tr><td>Runtime</td><td>Python ${esc(c.python)}</td></tr><tr><td>Platform</td><td>${esc(c.platform)}</td></tr>
 <tr><td>Image support</td><td>${badge(c.pillow ? "Pillow available" : "Pillow missing", c.pillow ? "good" : "warm")}</td></tr><tr><td>Project storage</td><td>Owned source copies and separate builds</td></tr>
 <tr><td>Server</td><td>Authenticated loopback session</td></tr></tbody></table></div><div class="notice">${esc(c.runtime_note)}</div></section>
 <section class="card"><h3>Systems</h3><p>NES · SNES · GEN · Game Boy · Game Boy Color · GBA</p><p class="subtle">Declare text and graphics for your source. Select a saved core setup to playtest.</p>${button("About & credit", "about", { icon: "shield" })}</section></div>
 <section class="card"><h3>System support matrix</h3><div class="table-wrap"><table><thead><tr><th>Family</th>${columns.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>
 ${packs.map((pack) => `<tr><td><strong>${esc(pack.label)}${pack.release_focus ? "" : " (advanced)"}</strong><br><small>${esc(pack.formats.join(", "))}</small></td>${columns.map(([key3]) => {
      const capability = key3 === "runtime_control" ? setups[pack.id] : pack.capabilities[key3];
      const label = capability.status === "supported" ? "Available" : capability.status === "experimental" ? "Header-based" : capability.status;
      return `<td title="${esc(capability.reason)}">${badge(label, capability.tone || (capability.status === "supported" ? "good" : "neutral"))}${key3 === "runtime_control" ? `<div class="actions">${button(capability.status === "Ready" ? "Open setup" : "Set up", "settings-setup", { id: pack.id })}</div>` : ""}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>
 <details><summary>What these statuses mean</summary><p>Available describes the listed editing feature. Header-based identification, including SNES, can remain ambiguous. Ready means included or saved core inputs were checked; it does not certify every game.</p><p>Choose core is a setup step for this workspace. Open Set up to find a local core. ROM health checks live in Resources.</p></details></section>
 ${report(c.systems, "Current system registry")}</details>`;
  }
  function mount9(ctx2) {
    var _a;
    const editor = ctx2.state.settingsEditor;
    if (!editor) return;
    for (const [key3, id] of Object.entries(settingIds)) {
      const node = document.getElementById(id);
      node == null ? void 0 : node.addEventListener("input", () => {
        if (editor.busy || ctx2.state.settingsEditor !== editor) return;
        editor.values[key3] = typeof DEFAULT_SETTINGS[key3] === "boolean" ? node.checked : typeof DEFAULT_SETTINGS[key3] === "number" ? Number(node.value) : node.value;
        editor.dirty = true;
        editor.error = "";
        const status = document.getElementById("settings-form-status");
        if (status) status.textContent = "Unapplied changes";
        const volume = document.getElementById("settings-volume-value");
        if (volume && key3 === "volume") volume.textContent = node.value + "%";
      });
    }
    (_a = document.getElementById("settings-form")) == null ? void 0 : _a.addEventListener("submit", (event) => {
      event.preventDefault();
      submitSettings(ctx2, true);
    });
  }

  // romancer/ui/views/levels.js
  var levels_exports = {};
  __export(levels_exports, {
    mount: () => mount10,
    render: () => render15
  });

  // romancer/ui/room_navigation.js
  function objectMetadata(doc, id, index) {
    var _a, _b;
    const room = doc.rooms.find((room2) => room2.id === id), definition = (_b = (_a = doc.definition) == null ? void 0 : _a.rooms) == null ? void 0 : _b.find((room2) => room2.id === id);
    return ((room == null ? void 0 : room.object_metadata) || (definition == null ? void 0 : definition.object_metadata) || []).find((entry) => entry.index === index) || null;
  }
  function objectFields(doc, id) {
    var _a, _b, _c, _d;
    const definition = (_b = (_a = doc.definition) == null ? void 0 : _a.rooms) == null ? void 0 : _b.find((room) => room.id === id);
    return ((_c = definition == null ? void 0 : definition.objects) == null ? void 0 : _c.fields) || Object.keys(((_d = doc.rooms.find((room) => room.id === id)) == null ? void 0 : _d.objects[0]) || {}).map((name) => ({ name, maximum: 65535 }));
  }
  function objectMaximum(doc, id, field2) {
    const room = doc.rooms.find((room2) => room2.id === id);
    return Math.min(field2.maximum ?? 65535, field2.name === "x" ? room.width - 1 : field2.name === "y" ? room.height - 1 : field2.name === "exit_room" ? doc.rooms.length - 1 : 65535);
  }
  function roomConnections(doc, model) {
    const result = [];
    for (const room of doc.rooms) {
      const objects = model.objects(room.id);
      for (let index = 0; index < objects.length; index++) {
        const metadata = objectMetadata(doc, room.id, index);
        if ((metadata == null ? void 0 : metadata.role) !== "exit" || !metadata.reference) continue;
        const field2 = metadata.reference.field, value = objects[index][field2], target = metadata.reference.targets.find((target2) => target2.value === value);
        if (target) result.push({ room_id: room.id, index, name: metadata.name, field: field2, value, target_room_id: target.room_id });
      }
    }
    return result;
  }
  function roomThumbnail(doc, model, id) {
    const room = model.room(id), sourceWidth = room.width * doc.block_width * 8, sourceHeight = room.height * doc.block_height * 8;
    const scale = Math.min(1, 160 / sourceWidth, 96 / sourceHeight), width = Math.max(1, Math.floor(sourceWidth * scale)), height = Math.max(1, Math.floor(sourceHeight * scale));
    const pixels = new Uint8ClampedArray(width * height * 4), cells = model.cells(id, "terrain"), blocks = model.blocks();
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const sx = Math.floor(x * sourceWidth / width), sy = Math.floor(y * sourceHeight / height), bx = Math.floor(sx / (doc.block_width * 8)), by = Math.floor(sy / (doc.block_height * 8));
      const part = Math.floor(sy / 8) % doc.block_height * doc.block_width + Math.floor(sx / 8) % doc.block_width;
      const tile = blocks[cells[by * room.width + bx]][part], value = doc.tiles[tile][sy % 8 * 8 + sx % 8];
      pixels.set([...doc.palette[value], 255], (y * width + x) * 4);
    }
    return { width, height, pixels };
  }
  function roomNavigation(doc, model, id) {
    const connections = roomConnections(doc, model), names4 = new Map(doc.rooms.map((room) => [room.id, room.name]));
    return `<section class="level-room-navigation"><h3>Choose a room</h3><p class="subtle">Select an object to move it, or choose a terrain brush to paint.</p><div class="level-room-list">${doc.rooms.map((room) => {
      const count = connections.filter((connection) => connection.room_id === room.id).length;
      return `<button type="button" class="level-room-card" data-action="levels-open-room" data-id="${esc(room.id)}" aria-pressed="${room.id === id}" aria-label="Open room ${esc(room.name)}"><canvas data-level-room-preview="${esc(room.id)}" aria-hidden="true"></canvas><strong>${esc(room.name)}</strong><span>${count} room ${count === 1 ? "link" : "links"}</span></button>`;
    }).join("")}</div><div class="level-connection-list">${connections.map((connection) => `<div class="level-connection"><span>${esc(names4.get(connection.room_id))}</span>${button(connection.name, "levels-select-object", { id: String(connection.index), name: connection.room_id })}<span aria-hidden="true">→</span>${button(names4.get(connection.target_room_id), "levels-open-room", { id: connection.target_room_id })}</div>`).join("")}</div></section>`;
  }
  function objectChoices(doc, model, id, allRecords = false) {
    return model.objects(id).flatMap((object, index) => {
      const metadata = objectMetadata(doc, id, index);
      return metadata || allRecords ? [{ index, object, metadata, label: (metadata == null ? void 0 : metadata.name) || "Record " + index }] : [];
    });
  }
  function visibleLevelObjects(doc, model, id, mode = "objects") {
    if (!["objects", "records"].includes(mode)) return [];
    const room = model.room(id);
    return objectChoices(doc, model, id, mode === "records").filter(({ object }) => Number.isSafeInteger(object.x) && Number.isSafeInteger(object.y) && object.x >= 0 && object.x < room.width && object.y >= 0 && object.y < room.height);
  }
  function selectedObjectIndex(ctx2, model, id) {
    var _a, _b;
    const choices = objectChoices(model.doc, model, id, ctx2.draft("level-overlay", "objects") === "records"), value = Number(ctx2.draft("level-object-index", "0"));
    return ((_a = choices.find((choice) => choice.index === value)) == null ? void 0 : _a.index) ?? ((_b = choices[0]) == null ? void 0 : _b.index) ?? null;
  }
  function objectInspector(ctx2, doc, model, id) {
    const allRecords = ctx2.draft("level-overlay", "objects") === "records", choices = objectChoices(doc, model, id, allRecords);
    if (!choices.length) return `<section class="card level-object-inspector"><h3>Objects</h3><p>No named objects in this room.</p>${model.objects(id).length ? "<details><summary>Advanced records</summary><p>Choose All records (Advanced) in Overlay to inspect or move raw record slots.</p></details>" : ""}</section>`;
    const index = selectedObjectIndex(ctx2, model, id), object = model.objects(id)[index], metadata = objectMetadata(doc, id, index), reference = (metadata == null ? void 0 : metadata.role) === "exit" ? metadata.reference : null;
    const names4 = new Map(doc.rooms.map((room) => [room.id, room.name]));
    const destination = reference ? select("level-object-destination", "Destination room", reference.targets.map((target) => [target.value, names4.get(target.room_id)]), object[reference.field]) : "";
    const controls = objectFields(doc, id).map((field2, position) => {
      if ((reference == null ? void 0 : reference.field) === field2.name) return "";
      const maximum = objectMaximum(doc, id, field2), label = field2.name === "x" ? "X position" : field2.name === "y" ? "Y position" : field2.name;
      return `<label class="field"><span>${esc(label)}</span><input id="level-object-input-${position}" type="number" min="0" max="${maximum}" step="1" value="${object[field2.name]}"><small>0 to ${maximum}</small></label>`;
    }).join("");
    const instruction = Number.isSafeInteger(object.x) && Number.isSafeInteger(object.y) ? "Choose Move object, then drag its label on the map." : "This object has no map position. Its values are available below.";
    return `<section class="card level-object-inspector"><h3>${allRecords ? "Records (Advanced)" : "Objects"}</h3>${select("level-object-index", "Selected object", choices.map((choice) => [choice.index, choice.label]), index)}<p class="subtle">${instruction}</p>${destination}${button("Update preview", "levels-object-apply")}<details class="level-object-advanced"><summary>Position & advanced values</summary><div class="field-row">${controls}</div><p class="subtle">These values come from the layout definition. Names and roles do not establish game behavior.</p><details><summary>Raw record</summary><pre>${esc(JSON.stringify(object, null, 2))}</pre></details></details></section>`;
  }
  function mountRoomNavigation(doc, model) {
    var _a;
    for (const canvas of ((_a = document.querySelectorAll) == null ? void 0 : _a.call(document, "[data-level-room-preview]")) || []) {
      const picture = roomThumbnail(doc, model, canvas.dataset.levelRoomPreview);
      canvas.width = picture.width;
      canvas.height = picture.height;
      const context = canvas.getContext("2d"), image = context.createImageData(picture.width, picture.height);
      image.data.set(picture.pixels);
      context.putImageData(image, 0, 0);
    }
  }

  // romancer/ui/level_canvas.js
  var integer8 = (v, min, max) => {
    if (!Number.isSafeInteger(v) || v < min || v > max) throw Error("Level value is outside declared bounds.");
    return v;
  };
  var key = (c) => [c.kind, c.room_id ?? "", c.index, c.part ?? c.field ?? ""].join(":");
  function levelScale(width, height, viewportHeight, availableWidth, mode) {
    if (mode === "fit") return Math.max(0.25, Math.min(3, Math.max(160, viewportHeight - 420) / height, availableWidth / width));
    const value = Number(mode);
    integer8(value, 1, 3);
    return value;
  }
  var LevelDraft = class {
    constructor(doc, changes = []) {
      this.doc = doc;
      this.changes = /* @__PURE__ */ new Map();
      this.past = [];
      this.future = [];
      this.start = null;
      if (!Array.isArray(changes) || changes.length > 8192) throw Error("Level draft exceeds its change budget.");
      for (const change of changes) this.set(change);
    }
    room(id) {
      const r = this.doc.rooms.find((r2) => r2.id === id);
      if (!r) throw Error("Unknown room.");
      return r;
    }
    set(c) {
      var _a, _b, _c, _d, _e, _f;
      let original, max;
      if (c.kind === "metatile") {
        integer8(c.index, 0, this.doc.metatiles.length - 1);
        integer8(c.part, 0, this.doc.metatiles[c.index].length - 1);
        original = this.doc.metatiles[c.index][c.part];
        max = this.doc.tiles.length - 1;
      } else {
        const r = this.room(c.room_id);
        if (c.kind === "object") {
          integer8(c.index, 0, r.objects.length - 1);
          if (!(c.field in r.objects[c.index])) throw Error("Unknown object field.");
          original = r.objects[c.index][c.field];
          const declared2 = (_c = (_b = (_a = this.doc.definition) == null ? void 0 : _a.rooms.find((x) => x.id === r.id)) == null ? void 0 : _b.objects) == null ? void 0 : _c.fields.find((f) => f.name === c.field);
          max = Math.min((declared2 == null ? void 0 : declared2.maximum) ?? 65535, c.field === "x" ? r.width - 1 : c.field === "y" ? r.height - 1 : c.field === "exit_room" ? this.doc.rooms.length - 1 : 65535);
        } else {
          if (!["terrain", "collision"].includes(c.kind) || !r[c.kind]) throw Error("This layer is not declared.");
          integer8(c.index, 0, r[c.kind].length - 1);
          original = r[c.kind][c.index];
          const declared2 = (_e = (_d = this.doc.definition) == null ? void 0 : _d.rooms.find((x) => x.id === r.id)) == null ? void 0 : _e[c.kind];
          max = c.kind === "terrain" ? this.doc.metatiles.length - 1 : 2 ** (8 * ((declared2 == null ? void 0 : declared2.entry_bytes) || 1)) - 1;
        }
      }
      integer8(c.value, 0, max);
      if (c.kind === "object") {
        const metadata = objectMetadata(this.doc, c.room_id, c.index);
        if ((metadata == null ? void 0 : metadata.role) === "exit" && ((_f = metadata.reference) == null ? void 0 : _f.field) === c.field && !metadata.reference.targets.some((target) => target.value === c.value)) throw Error("Exit destination is not mapped.");
      }
      if (c.value === original) this.changes.delete(key(c));
      else this.changes.set(key(c), { ...c });
      if (this.changes.size > 8192) {
        this.changes.delete(key(c));
        throw Error("Review at most8192level changes.");
      }
    }
    values() {
      return [...this.changes.values()];
    }
    cells(id, layer) {
      const original = this.room(id)[layer];
      if (!original) throw Error("This layer is not declared.");
      return original.map((v, index) => {
        var _a;
        return ((_a = this.changes.get(key({ kind: layer, room_id: id, index }))) == null ? void 0 : _a.value) ?? v;
      });
    }
    blocks() {
      return this.doc.metatiles.map((parts, index) => parts.map((v, part) => {
        var _a;
        return ((_a = this.changes.get(key({ kind: "metatile", index, part }))) == null ? void 0 : _a.value) ?? v;
      }));
    }
    objects(id) {
      return this.room(id).objects.map((obj, index) => Object.fromEntries(Object.entries(obj).map(([field2, v]) => {
        var _a;
        return [field2, ((_a = this.changes.get(key({ kind: "object", room_id: id, index, field: field2 }))) == null ? void 0 : _a.value) ?? v];
      })));
    }
    begin() {
      this.start = JSON.stringify(this.values());
    }
    commit() {
      if (this.start !== null && this.start !== JSON.stringify(this.values())) {
        this.past.push(this.start);
        if (this.past.length > 32) this.past.shift();
        this.future = [];
      }
      this.start = null;
    }
    restore(text) {
      this.changes.clear();
      for (const c of JSON.parse(text)) this.set(c);
    }
    cancel() {
      if (this.start !== null) this.restore(this.start);
      this.start = null;
    }
    undo() {
      if (this.past.length) {
        this.future.push(JSON.stringify(this.values()));
        this.restore(this.past.pop());
      }
    }
    redo() {
      if (this.future.length) {
        this.past.push(JSON.stringify(this.values()));
        this.restore(this.future.pop());
      }
    }
    paint(id, layer, index, value) {
      this.set({ kind: layer, room_id: id, index, value });
    }
    fill(id, layer, index, value) {
      const r = this.room(id), cells = this.cells(id, layer);
      integer8(index, 0, cells.length - 1);
      integer8(value, 0, layer === "terrain" ? this.doc.metatiles.length - 1 : 65535);
      const old = cells[index];
      if (old === value) return;
      const queue = [index], seen = /* @__PURE__ */ new Set();
      while (queue.length) {
        const at = queue.pop();
        if (seen.has(at) || cells[at] !== old) continue;
        seen.add(at);
        this.paint(id, layer, at, value);
        const x = at % r.width, y = Math.floor(at / r.width);
        for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) if (x + dx >= 0 && x + dx < r.width && y + dy >= 0 && y + dy < r.height) queue.push((y + dy) * r.width + x + dx);
      }
    }
    copy(id, layer, rect) {
      const r = this.room(id);
      for (const k of ["x", "y"]) integer8(rect[k], 0, (k === "x" ? r.width : r.height) - 1);
      integer8(rect.width, 1, r.width - rect.x);
      integer8(rect.height, 1, r.height - rect.y);
      const cells = this.cells(id, layer);
      return { width: rect.width, height: rect.height, values: Array.from({ length: rect.width * rect.height }, (_, i) => cells[(rect.y + Math.floor(i / rect.width)) * r.width + rect.x + i % rect.width]) };
    }
    paste(id, layer, index, clip) {
      const r = this.room(id);
      integer8(index, 0, r.width * r.height - 1);
      if (!clip || !Array.isArray(clip.values)) throw Error("Copy a rectangle first.");
      const x = index % r.width, y = Math.floor(index / r.width);
      if (clip.width < 1 || clip.height < 1 || clip.values.length !== clip.width * clip.height || x + clip.width > r.width || y + clip.height > r.height) throw Error("Copied rectangle must fit inside room bounds.");
      clip.values.forEach((value, i) => this.paint(id, layer, (y + Math.floor(i / clip.width)) * r.width + x + i % clip.width, value));
    }
  };
  function roomPixels2(doc, model, id) {
    const room = model.room(id), blocks = model.blocks(), cells = model.cells(id, "terrain"), width = room.width * doc.block_width * 8, height = room.height * doc.block_height * 8;
    if (width * height > 4 * 1024 ** 2) throw Error("Room preview exceeds four million pixels.");
    const out = new Uint8ClampedArray(width * height * 4);
    cells.forEach((block, cell) => {
      blocks[block].forEach((tile, part) => {
        doc.tiles[tile].forEach((v, pixel) => {
          const x = cell % room.width * doc.block_width * 8 + part % doc.block_width * 8 + pixel % 8, y = Math.floor(cell / room.width) * doc.block_height * 8 + Math.floor(part / doc.block_width) * 8 + Math.floor(pixel / 8), rgb = doc.palette[v];
          out.set([...rgb, 255], (y * width + x) * 4);
        });
      });
    });
    return out;
  }
  function changedRoomCells(doc, model, id) {
    const room = model.room(id), changedBlocks = new Set(model.values().filter((c) => c.kind === "metatile").map((c) => c.index)), terrain = model.cells(id, "terrain"), collision = room.collision ? model.cells(id, "collision") : null, result = /* @__PURE__ */ new Set();
    terrain.forEach((value, index) => {
      if (value !== room.terrain[index] || changedBlocks.has(value) || collision && collision[index] !== room.collision[index]) result.add(index);
    });
    for (const c of model.values().filter((c2) => c2.kind === "object" && c2.room_id === id)) {
      const old = room.objects[c.index], next = model.objects(id)[c.index];
      for (const object of [old, next]) if (Number.isSafeInteger(object.x) && Number.isSafeInteger(object.y) && object.x >= 0 && object.x < room.width && object.y >= 0 && object.y < room.height) result.add(object.y * room.width + object.x);
    }
    return [...result].sort((a, b) => a - b);
  }
  function blockPixels(doc, model, index) {
    integer8(index, 0, doc.metatiles.length - 1);
    const width = doc.block_width * 8, height = doc.block_height * 8, pixels = new Uint8ClampedArray(width * height * 4);
    for (const [part, tile] of model.blocks()[index].entries()) for (const [pixel, value] of doc.tiles[tile].entries()) {
      const x = part % doc.block_width * 8 + pixel % 8, y = Math.floor(part / doc.block_width) * 8 + Math.floor(pixel / 8);
      pixels.set([...doc.palette[value], 255], (y * width + x) * 4);
    }
    return pixels;
  }
  function pickLevelBrush(model, id, layer, index) {
    const cells = model.cells(id, layer);
    integer8(index, 0, cells.length - 1);
    return cells[index];
  }
  function moveLevelObject(model, id, index, x, y) {
    const room = model.room(id);
    integer8(index, 0, room.objects.length - 1);
    integer8(x, 0, room.width - 1);
    integer8(y, 0, room.height - 1);
    const object = room.objects[index];
    if (!Object.hasOwn(object, "x") || !Object.hasOwn(object, "y")) throw Error("Object coordinates are not declared.");
    model.set({ kind: "object", room_id: id, index, field: "x", value: x });
    model.set({ kind: "object", room_id: id, index, field: "y", value: y });
  }
  function levelBrushPalette(doc, model, selected2) {
    return `<div class="level-brush-palette" role="group" aria-label="Terrain brushes">${model.blocks().map((_, index) => `<button type="button" data-level-brush="${index}" aria-pressed="${Number(selected2) === index}" aria-label="Paint with metatile ${index}" title="Metatile ${index}"><canvas data-level-block="${index}" aria-hidden="true"></canvas><span>${index}</span></button>`).join("")}</div>`;
  }
  function mountLevel(ctx2, doc, model, id, persist) {
    var _a, _b;
    const canvas = document.getElementById("level-canvas");
    if (!canvas) return;
    const scope = selectionKey(ctx2.state), current2 = () => scope === selectionKey(ctx2.state) && ctx2.state.page === "levels", room = model.room(id);
    let pointer = null, selected2 = 0, anchor = null, dragObject = null, dragOffset = { x: 0, y: 0 };
    const brushNodes = () => {
      var _a2;
      return [...((_a2 = document.querySelectorAll) == null ? void 0 : _a2.call(document, "[data-level-brush]")) || []];
    };
    const markerMode = () => read("level-overlay") === "records" ? "records" : read("level-overlay") === "objects" || read("level-tool") === "objects" ? "objects" : "none";
    const visibleMarkers = () => visibleLevelObjects(doc, model, id, markerMode());
    const markerRects = () => visibleMarkers().map((marker) => {
      const w = doc.block_width * 8, h = doc.block_height * 8, left = marker.object.x * w, top = marker.object.y * h, label = markerMode() === "records" ? String(marker.index) : marker.metadata.role[0].toUpperCase() + marker.metadata.role.slice(1), width = Math.min(room.width * w - left, Math.max(w, label.length * 6 + 6));
      return { ...marker, left, top, width, height: h, label };
    });
    const chooseBrush = (value) => {
      const input = document.getElementById("level-brush");
      if (input) input.value = String(value);
      ctx2.setDraft("level-brush", String(value));
      for (const node of brushNodes()) node.setAttribute("aria-pressed", String(Number(node.dataset.levelBrush) === value));
    };
    const originalCanvas = document.getElementById("level-original");
    if (room.width * doc.block_width * 8 * room.height * doc.block_height * 8 > 4 * 1024 ** 2) {
      const status = document.getElementById("level-difference-count");
      if (status) status.textContent = "Preview unavailable: this room exceeds the four-million-pixel preview limit.";
      canvas.width = 1;
      canvas.height = 1;
      return;
    }
    const originalPixels = originalCanvas ? roomPixels2(doc, new LevelDraft(doc), id) : null;
    const draw2 = () => {
      canvas.width = room.width * doc.block_width * 8;
      canvas.height = room.height * doc.block_height * 8;
      canvas.style.width = canvas.width * levelScale(canvas.width, canvas.height, window.innerHeight, canvas.parentElement.clientWidth, read("level-zoom")) + "px";
      const c = canvas.getContext("2d"), image = c.createImageData(canvas.width, canvas.height);
      image.data.set(roomPixels2(doc, model, id));
      c.putImageData(image, 0, 0);
      const w = doc.block_width * 8, h = doc.block_height * 8;
      if (read("level-overlay") === "collision" && room.collision) {
        const colors = ["#e75d6d88", "#66b9f088", "#ffca5c88"];
        model.cells(id, "collision").forEach((value, i) => {
          if (value) {
            c.fillStyle = colors[value % 4] || "#e75d6d88";
            c.fillRect(i % room.width * w, Math.floor(i / room.width) * h, w, h);
          }
        });
      }
      for (const marker of markerRects()) {
        c.fillStyle = "#76e2bd";
        c.fillRect(marker.left + 1, marker.top + 1, marker.width - 2, marker.height - 2);
        c.strokeStyle = "#102127";
        c.strokeRect(marker.left + 0.5, marker.top + 0.5, marker.width - 1, marker.height - 1);
        c.fillStyle = "#102127";
        c.font = "10px sans-serif";
        c.fillText(marker.label, marker.left + 3, marker.top + Math.min(11, marker.height - 2), Math.max(1, marker.width - 6));
      }
      const changes = changedRoomCells(doc, model, id);
      c.strokeStyle = "#ffca5c";
      c.lineWidth = 2;
      for (const cell of changes) c.strokeRect(cell % room.width * w + 1, Math.floor(cell / room.width) * h + 1, w - 2, h - 2);
      const label = document.getElementById("level-difference-count");
      if (label) label.textContent = changes.length ? "Preview updated · " + changes.length + " room cells changed · not built" : "Unchanged room preview";
      if (originalCanvas) {
        originalCanvas.width = canvas.width;
        originalCanvas.height = canvas.height;
        originalCanvas.style.width = canvas.style.width;
        const before = originalCanvas.getContext("2d"), picture = before.createImageData(canvas.width, canvas.height);
        picture.data.set(originalPixels);
        before.putImageData(picture, 0, 0);
      }
      c.strokeStyle = "#70d4b4";
      c.lineWidth = 1;
      c.strokeRect(selected2 % room.width * w + 0.5, Math.floor(selected2 / room.width) * h + 0.5, w - 1, h - 1);
    };
    const at = (e) => {
      const r = canvas.getBoundingClientRect(), x = Math.floor((e.clientX - r.left) / r.width * room.width), y = Math.floor((e.clientY - r.top) / r.height * room.height);
      return x < 0 || y < 0 || x >= room.width || y >= room.height ? null : y * room.width + x;
    };
    const paint = (index) => {
      var _a2;
      const layer = read("level-layer"), tool = read("level-tool");
      selected2 = index;
      if (tool === "paint") model.paint(id, layer, index, Number(read("level-brush")));
      else if (tool === "fill") model.fill(id, layer, index, Number(read("level-brush")));
      else if (tool === "paste") model.paste(id, layer, index, ctx2.state.levelClipboard);
      else if (tool === "pick") chooseBrush(pickLevelBrush(model, id, layer, index));
      else if (tool === "objects" && dragObject !== null) moveLevelObject(model, id, dragObject, Math.max(0, Math.min(room.width - 1, index % room.width - dragOffset.x)), Math.max(0, Math.min(room.height - 1, Math.floor(index / room.width) - dragOffset.y)));
      if (tool === "select" && anchor !== null) {
        ctx2.state.levelRect = { x: Math.min(anchor % room.width, index % room.width), y: Math.min(Math.floor(anchor / room.width), Math.floor(index / room.width)), width: Math.abs(anchor % room.width - index % room.width) + 1, height: Math.abs(Math.floor(anchor / room.width) - Math.floor(index / room.width)) + 1 };
      }
      const n = document.getElementById("level-position");
      if (n) n.textContent = `${dragObject !== null ? ((_a2 = objectMetadata(doc, id, dragObject)) == null ? void 0 : _a2.name) || "Record " + dragObject : "Room preview"} · ${model.values().length} preview changes`;
      draw2();
    };
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerdown", (e) => {
      if (!current2() || e.button !== 0) return;
      const index = at(e);
      if (index === null) return;
      e.preventDefault();
      canvas.focus();
      if (read("level-tool") === "objects") {
        const bounds2 = canvas.getBoundingClientRect(), px = (e.clientX - bounds2.left) / bounds2.width * canvas.width, py = (e.clientY - bounds2.top) / bounds2.height * canvas.height, hit = [...markerRects()].reverse().find((marker) => px >= marker.left && px < marker.left + marker.width && py >= marker.top && py < marker.top + marker.height);
        dragObject = (hit == null ? void 0 : hit.index) ?? -1;
        if (dragObject < 0) {
          dragObject = null;
          ctx2.notify("Choose an object label to move.");
          return;
        }
        dragOffset = { x: index % room.width - hit.object.x, y: Math.floor(index / room.width) - hit.object.y };
        ctx2.setDraft("level-object-index", String(dragObject));
        const selector = document.getElementById("level-object-index");
        if (selector) selector.value = String(dragObject);
      }
      pointer = e.pointerId;
      canvas.setPointerCapture(pointer);
      anchor = index;
      model.begin();
      try {
        paint(index);
      } catch (error) {
        model.cancel();
        pointer = null;
        dragObject = null;
        draw2();
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!current2() || pointer !== e.pointerId || !["paint", "select", "objects"].includes(read("level-tool"))) return;
      const index = at(e);
      if (index !== null) try {
        paint(index);
      } catch (error) {
        model.cancel();
        pointer = null;
        dragObject = null;
        draw2();
        ctx2.notify(error.message, true);
      }
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!current2() || pointer !== e.pointerId) return;
      pointer = null;
      dragObject = null;
      const changed2 = model.start !== JSON.stringify(model.values());
      model.commit();
      if (changed2) persist();
      ctx2.render();
    });
    canvas.addEventListener("pointercancel", () => {
      model.cancel();
      pointer = null;
      dragObject = null;
      draw2();
    });
    canvas.addEventListener("keydown", (e) => {
      if (!current2()) return;
      const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -room.width, ArrowDown: room.width }[e.key];
      if (delta) {
        e.preventDefault();
        selected2 = Math.max(0, Math.min(room.width * room.height - 1, selected2 + delta));
        draw2();
      }
      if (e.key === " ") {
        e.preventDefault();
        model.begin();
        try {
          paint(selected2);
          model.commit();
          persist();
          ctx2.render();
        } catch (error) {
          model.cancel();
          ctx2.notify(error.message, true);
        }
      }
    });
    for (const node of brushNodes()) {
      const index = Number(node.dataset.levelBrush), thumb = node.querySelector("canvas");
      if (thumb) {
        thumb.width = doc.block_width * 8;
        thumb.height = doc.block_height * 8;
        const painter = thumb.getContext("2d"), picture = painter.createImageData(thumb.width, thumb.height);
        picture.data.set(blockPixels(doc, model, index));
        painter.putImageData(picture, 0, 0);
      }
      node.addEventListener("click", () => {
        if (!current2()) return;
        chooseBrush(index);
        for (const [name, value] of [["level-layer", "terrain"], ["level-tool", "paint"]]) {
          const input = document.getElementById(name);
          if (input) input.value = value;
          ctx2.setDraft(name, value);
        }
        draw2();
      });
    }
    for (const name of ["level-overlay", "level-zoom", "level-tool"]) (_a = document.getElementById(name)) == null ? void 0 : _a.addEventListener("change", draw2);
    (_b = document.getElementById("level-brush")) == null ? void 0 : _b.addEventListener("change", () => chooseBrush(Number(read("level-brush"))));
    draw2();
  }

  // romancer/ui/game_maps.js
  var hex2 = (n) => "0x" + Number(n).toString(16).toUpperCase();
  var clone = (value) => JSON.parse(JSON.stringify(value));
  var key2 = (c) => c.kind === "arrival" ? `arrival:${c.table}:${c.id}` : `${c.kind}:${c.offset}`;
  var number2 = (value, max = 63) => {
    if (!/^\d+$/.test(String(value)) || !Number.isSafeInteger(Number(value)) || Number(value) > max) throw Error(`Enter a whole number from 0 to ${max}.`);
    return Number(value);
  };
  var objectName = (room, n) => room.header === 18539 && n.event === 274 ? "Mother" : `NPC definition ${n.index + 1}`;
  var MapDraft = class {
    constructor(doc) {
      this.doc = doc;
      this.changes = /* @__PURE__ */ new Map();
      this.past = [];
      this.future = [];
      this.revision = 0;
    }
    values() {
      return [...this.changes.values()].sort((a, b) => key2(a).localeCompare(key2(b))).map(clone);
    }
    entity(change) {
      if (change.kind === "command") return this.doc.map.commands.find((c) => c.offset === change.offset);
      if (change.kind === "npc") return this.doc.objects.find((n) => n.offset === change.offset);
      if (change.kind === "arrival") return this.doc.arrivals.find((a) => a.table === change.table && a.id === change.id);
      return null;
    }
    stage(change) {
      const base = this.entity(change), allowed = change.kind === "command" ? ["kind", "offset", "x", "y", "tile"] : change.kind === "npc" ? ["kind", "offset", "x", "y"] : ["kind", "table", "id", "x", "y"];
      if (!base || !["command", "npc", "arrival"].includes(change.kind) || Object.keys(change).some((k) => !allowed.includes(k))) throw Error("Unknown or protected map field.");
      if (change.kind !== "arrival" && !base.editable) throw Error("This definition is read-only.");
      if (change.kind === "arrival" && (change.table !== "main" || !this.doc.room.editable)) throw Error("This arrival is read-only.");
      const before = this.values(), id = key2(change), next = { ...this.changes.get(id) || {}, ...change };
      for (const name of ["x", "y", "tile"]) if (name in next) {
        number2(next[name]);
        if (!(name in base)) throw Error("This command has no tile field.");
        if (next[name] === base[name]) delete next[name];
      }
      if (!this.changes.has(id) && this.changes.size >= 64 && ["x", "y", "tile"].some((k) => k in next)) throw Error("At most 64 map records can be staged.");
      if (["x", "y", "tile"].some((k) => k in next)) this.changes.set(id, next);
      else this.changes.delete(id);
      if (JSON.stringify(before) !== JSON.stringify(this.values())) {
        this.past.push(before);
        if (this.past.length > 200) this.past.shift();
        this.future = [];
        this.revision++;
      }
    }
    restore(values) {
      this.changes = new Map(values.map((c) => [key2(c), clone(c)]));
      this.revision++;
    }
    undo() {
      if (this.past.length) {
        this.future.push(this.values());
        if (this.future.length > 200) this.future.shift();
        this.restore(this.past.pop());
      }
    }
    redo() {
      if (this.future.length) {
        this.past.push(this.values());
        if (this.past.length > 200) this.past.shift();
        this.restore(this.future.pop());
      }
    }
    clear() {
      if (this.changes.size) {
        this.past.push(this.values());
        if (this.past.length > 200) this.past.shift();
        this.future = [];
        this.restore([]);
      }
    }
    changed(entity, kind) {
      return { ...entity, ...this.changes.get(key2(kind === "arrival" ? { kind, table: entity.table, id: entity.id } : { kind, offset: entity.offset })) };
    }
  };
  function cropMap(center = [15, 31], overview = false) {
    return overview ? { x: 0, y: 0, width: 64, height: 64, scale: 4 } : { x: Math.max(0, Math.min(48, Math.round(center[0]) - 8)), y: Math.max(0, Math.min(52, Math.round(center[1]) - 6)), width: 16, height: 12, scale: 16 };
  }
  function mapPoint(crop, rect, point) {
    if (rect.width <= 0 || rect.height <= 0) return null;
    const x = Math.floor((point.x - rect.left) / rect.width * crop.width), y = Math.floor((point.y - rect.top) / rect.height * crop.height);
    return x >= 0 && y >= 0 && x < crop.width && y < crop.height ? [crop.x + x, crop.y + y] : null;
  }
  function mapPixels2(map, crop, cells = map.cells) {
    const scale = crop.scale || 16, width = crop.width * scale, height = crop.height * scale;
    if (width * height > 1024 * 1024 || (cells == null ? void 0 : cells.length) !== 4096) throw Error("Map preview exceeds supported bounds.");
    const pixels = new Uint8ClampedArray(width * height * 4), palette2 = map.palette || [[255, 255, 255], [170, 170, 170], [85, 85, 85], [0, 0, 0]];
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const sx = crop.x + Math.floor(x / scale), sy = crop.y + Math.floor(y / scale), tile = map.tiles[cells[sy * 64 + sx]], px = Math.floor(x % scale * 16 / scale), py = Math.floor(y % scale * 16 / scale), rgb = palette2[tile == null ? void 0 : tile[py * 16 + px]];
      if (!rgb) throw Error("Missing decoded map tile or color index.");
      pixels.set([...rgb, 255], (y * width + x) * 4);
    }
    return { width, height, pixels };
  }
  function selected(view) {
    const [kind, value, extra] = String(view.selection || "").split(":");
    if (!view.model) return null;
    const doc = view.model.doc;
    const entity = kind === "command" ? doc.map.commands.find((c) => c.offset === Number(value)) : kind === "npc" ? doc.objects.find((n) => n.offset === Number(value)) : kind === "arrival" ? doc.arrivals.find((a) => a.table === value && a.id === Number(extra)) : null;
    return entity ? { kind, entity } : null;
  }
  function targetKey(kind, e) {
    return kind === "arrival" ? `arrival:${e.table}:${e.id}` : `${kind}:${e.offset}`;
  }
  function currentTarget(view) {
    const chosen = selected(view);
    return chosen ? { ...chosen, entity: view.model.changed(chosen.entity, chosen.kind) } : null;
  }
  function requestFields(view) {
    const chosen = selected(view);
    if (!chosen) throw Error("Select an existing command, NPC or arrival.");
    const data = { kind: chosen.kind, ...chosen.kind === "arrival" ? { table: chosen.entity.table, id: chosen.entity.id } : { offset: chosen.entity.offset }, x: number2(read("maps-x")), y: number2(read("maps-y")) };
    if (chosen.kind === "command" && "tile" in chosen.entity) data.tile = number2(read("maps-tile"));
    return data;
  }
  function canEdit(view, chosen) {
    return !!chosen && view.model.doc.room.editable && (chosen.kind === "arrival" ? chosen.entity.table === "main" : chosen.entity.editable);
  }
  function savedChanges(ctx2, sha) {
    const text = ctx2.draft("game-map-changes", "{}");
    if (text === "{}" || !text) return { changes: {} };
    try {
      if (typeof text !== "string" || text.length > 65536) throw Error();
      const data = JSON.parse(text);
      if (!data || data.version !== 1 || data.source_sha256 !== sha || !data.changes_by_header || typeof data.changes_by_header !== "object" || Array.isArray(data.changes_by_header) || Object.keys(data).some((k) => !["version", "source_sha256", "changes_by_header"].includes(k))) throw Error();
      if (Object.entries(data.changes_by_header).some(([header, values]) => header !== String(18539) || !Array.isArray(values) || values.length > 64)) throw Error();
      return { changes: data.changes_by_header };
    } catch {
      return { changes: {}, note: "Saved map edits were ignored because their source, header or fields no longer match." };
    }
  }
  async function gameMaps(ctx2, { simpleAvailable = false } = {}) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2, scope = selectionKey(state2), params = { ...ctx2.sourceParams() };
    let view = state2.gameMapsView;
    if ((view == null ? void 0 : view.scope) !== scope) {
      const saved = savedChanges(ctx2, state2.artifact.sha256);
      view = { scope, header: 18539, offset: 0, query: "", request: 0, reviewSerial: 0, pending: null, models: /* @__PURE__ */ new Map(), overview: false, mode: "inspect", center: null, saved: saved.changes, draftNote: saved.note, active: true, epoch: 1 };
      state2.gameMapsView = view;
    }
    if (!view.active) {
      view.active = true;
      view.epoch = (view.epoch || 0) + 1;
    }
    const epoch = view.epoch;
    const current2 = () => scope === selectionKey(state2) && state2.gameMapsView === view && view.active && view.epoch === epoch && (state2.page === void 0 || state2.page === "levels");
    const invalidate = () => {
      view.pending = null;
      view.reviewSerial++;
    };
    const persist = () => {
      if (!current2()) return;
      const changes_by_header = {};
      for (const [header2, model2] of view.models) {
        const values = model2.values();
        if (header2 === 18539 && model2.doc.source_sha256 === state2.artifact.sha256 && values.length) changes_by_header[String(header2)] = values;
      }
      ctx2.setDraft("game-map-changes", JSON.stringify({ version: 1, source_sha256: state2.artifact.sha256, changes_by_header }));
      state2.historyEditor = "maps-edit";
    };
    view.persist = persist;
    const choose = (value) => {
      view.selection = value;
      view.formDirty = false;
      const target = currentTarget(view);
      if (target) view.center = [target.entity.x, target.entity.y];
    };
    ctx2.use({
      "maps-open-room": (node) => {
        if (!current2()) return;
        const header2 = number2(node.dataset.id, 28543);
        if (header2 < 18432) throw Error("Unknown room header.");
        view.header = header2;
        view.selection = null;
        view.center = null;
        view.formDirty = false;
        view.inspection = void 0;
        view.request++;
        invalidate();
        return ctx2.render();
      },
      "maps-search": () => {
        if (!current2()) return;
        const query2 = read("maps-query").trim();
        if (query2.length > 128) throw Error("Search is limited to 128 characters.");
        view.query = query2;
        view.offset = 0;
        view.catalog = void 0;
        view.request++;
        return ctx2.render();
      },
      "maps-page": (node) => {
        var _a2;
        if (!current2()) return;
        const offset2 = number2(node.dataset.id, 1e4);
        if (offset2 >= ((_a2 = view.catalog) == null ? void 0 : _a2.total) && offset2 !== 0) throw Error("This map page is no longer available.");
        view.offset = offset2;
        view.catalog = void 0;
        view.request++;
        return ctx2.render();
      },
      "maps-simple": () => {
        if (!current2() || !simpleAvailable) return;
        invalidate();
        view.request++;
        view.active = false;
        view.epoch++;
        ctx2.setDraft("ffl2-map-mode", "simple");
        return ctx2.render();
      },
      "maps-select": () => {
        if (!current2()) return;
        choose(read("maps-target"));
        return ctx2.render();
      },
      "maps-overview": () => {
        if (!current2()) return;
        view.overview = !view.overview;
        return ctx2.render();
      },
      "maps-pan": (node) => {
        if (!current2()) return;
        const [dx, dy] = String(node.dataset.id).split(",").map(Number);
        if (![[8, 0], [-8, 0], [0, 6], [0, -6]].some((p) => p[0] === dx && p[1] === dy)) throw Error("Unknown viewport direction.");
        const c = view.center || [15, 31];
        view.center = [Math.max(0, Math.min(63, c[0] + dx)), Math.max(0, Math.min(63, c[1] + dy))];
        view.overview = false;
        return ctx2.render();
      },
      "maps-mode": () => {
        if (!current2()) return;
        const value = read("maps-mode");
        if (!["inspect", "place"].includes(value)) throw Error("Unknown map tool.");
        view.mode = value;
        return ctx2.render();
      },
      "maps-stage": () => {
        if (!current2() || !view.model) return;
        if (!canEdit(view, selected(view))) throw Error("This map definition is read-only.");
        view.model.stage(requestFields(view));
        view.formDirty = false;
        invalidate();
        persist();
        return ctx2.render();
      },
      "maps-undo": () => {
        if (current2() && view.model) {
          view.model.undo();
          view.formDirty = false;
          invalidate();
          persist();
          return ctx2.render();
        }
      },
      "maps-redo": () => {
        if (current2() && view.model) {
          view.model.redo();
          view.formDirty = false;
          invalidate();
          persist();
          return ctx2.render();
        }
      },
      "maps-clear": () => {
        if (current2() && view.model) {
          view.model.clear();
          view.formDirty = false;
          invalidate();
          persist();
          return ctx2.render();
        }
      },
      "maps-review": async () => {
        if (!current2() || !view.model || !view.model.values().length) throw Error("Stage a map edit first.");
        if (view.formDirty) throw Error("Stage the changed coordinate fields before reviewing.");
        const model2 = view.model, header2 = view.header, changes = model2.values(), signature = JSON.stringify(changes), revision = model2.revision, serial = ++view.reviewSerial;
        view.pending = null;
        const result = await ctx2.run("games.maps.plan", { ...params, header: header2, changes }, { render: false, refresh: false });
        if (!current2() || view.header !== header2 || view.model !== model2 || view.reviewSerial !== serial || model2.revision !== revision || JSON.stringify(model2.values()) !== signature) return;
        if (result.ok === false || result.source_sha256 !== state2.artifact.sha256) throw Error("Map review does not match the selected ROM. Review again.");
        view.pending = { scope, header: header2, signature, revision, result };
        return ctx2.render();
      },
      "maps-build": async () => {
        var _a2;
        const pending2 = view.pending, model2 = view.model;
        if (!current2() || view.formDirty || !pending2 || pending2.scope !== scope || pending2.header !== view.header || pending2.revision !== (model2 == null ? void 0 : model2.revision) || pending2.signature !== JSON.stringify(model2.values())) throw Error("Review the current map changes first.");
        const result = await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: pending2.result.plan_id }, { render: false, refresh: false });
        if (!current2()) return;
        await ((_a2 = ctx2.refreshProject) == null ? void 0 : _a2.call(ctx2));
        if (!current2()) return;
        if (view.model !== model2 || view.pending !== pending2 || model2.revision !== pending2.revision || JSON.stringify(model2.values()) !== pending2.signature) {
          persist();
          ctx2.notify("Separate map build created. Your newer edits remain staged.");
          return ctx2.render();
        }
        model2.restore([]);
        view.pending = null;
        persist();
        await ctx2.setArtifact(result.artifact_id);
        ctx2.notify("Separate map build created. Playtest its story and door routes before exporting.");
      }
    });
    const token2 = ++view.request, header = view.header, offset = view.offset, query = view.query;
    const valid = () => current2() && view.request === token2 && view.header === header && view.offset === offset && view.query === query && (!ctx2.isCurrentRender || ctx2.isCurrentRender());
    const tasks = [view.catalog ? Promise.resolve(view.catalog) : ctx2.api.call("games.maps.catalog", { ...params, offset, limit: 12, query }), ((_b = (_a = view.inspection) == null ? void 0 : _a.room) == null ? void 0 : _b.header) === header ? Promise.resolve(view.inspection) : ctx2.api.call("games.maps.inspect", { ...params, header, state: null })];
    const [catalogResult, inspectResult] = await Promise.allSettled(tasks);
    if (!valid()) return "";
    const response = (result) => {
      var _a2;
      if (result.status === "rejected") return { error: ((_a2 = result.reason) == null ? void 0 : _a2.message) || "Map inspection failed." };
      if (result.value.source_sha256 !== state2.artifact.sha256) return { error: "Map response belongs to a different source. Reopen the map browser." };
      return result.value;
    };
    const catalogDoc = response(catalogResult), doc = response(inspectResult);
    if (catalogDoc.error) return `<section class="card"><h3>Game maps unavailable</h3><p>${esc(catalogDoc.error)}</p></section>`;
    view.catalog = catalogDoc;
    if (!doc.error) {
      view.inspection = doc;
      if (doc.map.status === "decoded") {
        let model2 = view.models.get(header);
        if (!model2) {
          model2 = new MapDraft(doc);
          try {
            for (const change of ((_c = view.saved) == null ? void 0 : _c[String(header)]) || []) model2.stage(change);
          } catch {
            model2 = new MapDraft(doc);
            view.draftNote = "Saved map edits were ignored because a definition or field no longer matches.";
          }
          view.models.set(header, model2);
        }
        view.model = model2;
        state2.gameMapEditor = model2;
        if (model2.values().length) state2.historyEditor = "maps-edit";
        if (!selected(view)) {
          const target = doc.map.commands.find((c) => c.offset === 131957 && c.editable) || doc.map.commands.find((c) => c.editable) || doc.arrivals[0];
          view.selection = target ? targetKey("op" in target ? "command" : "arrival", target) : null;
        }
        if (!view.center) {
          const target = currentTarget(view), arrival = doc.arrivals.find((a) => a.id === 509) || doc.arrivals[0];
          view.center = target ? [target.entity.x, target.entity.y] : arrival ? [arrival.x, arrival.y] : [32, 32];
        }
      } else {
        view.model = null;
        state2.gameMapEditor = null;
      }
    }
    const counts = catalogDoc.counts || {}, rows = catalogDoc.rooms || [], end = Math.min(catalogDoc.total, offset + rows.length);
    const browser = `<section class="card game-map-browser"><div class="card-heading"><h3>Real game maps</h3>${simpleAvailable ? button("Bedroom shortcut", "maps-simple") : ""}</div><p>${counts.rooms || 0} room definitions · ${counts.maps || 0} shared terrain streams · ${counts.arrivals || 0} arrivals. Names remain address labels where no game name is proven.</p>${view.draftNote ? `<p class="notice">${esc(view.draftNote)}</p>` : ""}<div class="field-row">${field("maps-query", "Find room or terrain address", query)}${button("Search maps", "maps-search")}</div><div class="resource-grid game-map-catalog">${rows.map((r) => {
      var _a2, _b2;
      return `<article class="card"><h4>${esc(r.label)}</h4>${((_a2 = r.thumbnail) == null ? void 0 : _a2.status) === "available" ? `<img width="96" height="96" src="${esc(r.thumbnail.data_url)}" alt="Decoded terrain overview for ${esc(r.label)}"><small>${esc(r.thumbnail.palette_status)}</small>` : `<p class="subtle">Preview unavailable: ${esc(((_b2 = r.thumbnail) == null ? void 0 : _b2.reason) || "Unknown format")}</p>`}<p>${r.object_count} NPC definitions · ${r.arrival_count} arrivals</p>${button(r.header === header ? "Viewing this room" : "Inspect room", "maps-open-room", { id: String(r.header), primary: r.header === header })}</article>`;
    }).join("")}</div><div class="actions">${button("Previous maps", "maps-page", { id: String(Math.max(0, offset - 12)), disabled: offset === 0 })}<span>${rows.length ? offset + 1 : 0}–${end} of ${catalogDoc.total}</span>${button("Next maps", "maps-page", { id: String(offset + 12), disabled: end >= catalogDoc.total })}</div></section>`;
    if (doc.error) return browser + `<section class="card"><h3>Room unavailable</h3><p>${esc(doc.error)}</p></section>`;
    if (doc.map.status !== "decoded") return browser + `<section class="card"><h3>${esc(doc.room.label)}</h3><p class="notice">Terrain preview unavailable: ${esc(doc.map.reason)}</p><p>Conditional terrain needs an explicit game-state value. Unsupported circle paths remain unavailable. No state is assumed.</p>${definitions(doc)}</section>`;
    const model = view.model, chosen = currentTarget(view), editable = canEdit(view, chosen), pending = ((_d = view.pending) == null ? void 0 : _d.revision) === model.revision && view.pending.signature === JSON.stringify(model.values()) ? view.pending : null;
    const options = [...doc.map.commands.filter((c) => "x" in c).map((c) => [targetKey("command", c), `${c.name || "Command"} ${hex2(c.offset)}${c.editable ? "" : " · read-only"}`]), ...doc.objects.map((n) => [targetKey("npc", n), objectName(doc.room, n) + (n.editable ? "" : " · conditional/read-only")]), ...doc.arrivals.map((a) => [targetKey("arrival", a), `Arrival ${a.table} ${hex2(a.id)}`])];
    const form = chosen ? `<aside class="card game-map-inspector"><h3>${chosen.kind === "npc" ? esc(objectName(doc.room, chosen.entity)) : chosen.kind === "arrival" ? "Arrival position" : "Existing terrain command"}</h3>${select("maps-target", "Selection", options, view.selection)}<div class="field-row">${field("maps-x", "X · 0–63", chosen.entity.x, { type: "number", min: 0, readonly: !editable })}${field("maps-y", "Y · 0–63", chosen.entity.y, { type: "number", min: 0, readonly: !editable })}${chosen.kind === "command" && "tile" in chosen.entity ? field("maps-tile", "Tile · 0–63", chosen.entity.tile, { type: "number", min: 0, readonly: !editable }) : ""}</div>${chosen.kind === "npc" ? `<p class="notice">NPCs are stored definitions. Their conditions may hide them in Playtest.${chosen.entity.event === 274 ? " Mother participates in the opening story. Moving her can affect the narrative; playtest the full conversation." : ""}</p>` : ""}${chosen.kind === "command" ? `<p>${chosen.entity.final_cells || 0} final terrain cells currently come from this command. Later commands can overwrite its drawing.</p><p>Edits preserve collision behavior, region bits and existing trigger bindings. Changes that fail these checks are refused.</p>` : ""}${chosen.kind === "arrival" ? "<p>Changes only the arrival position. Destination, facing and packed flags stay protected. Enter through its real door when playtesting.</p>" : ""}${button("Stage position / tile", "maps-stage", { disabled: !editable, reason: "This definition is read-only; writable scope is the initial shared atlas." })}</aside>` : "<p>Select an existing terrain command, NPC definition or arrival.</p>";
    return browser + `<section class="card game-map-workbench"><h3>${header === 18539 ? "Opening bedroom / shared interiors" : esc(doc.room.label)}</h3><p>Terrain ${hex2(doc.room.map_pointer)} · shared by ${doc.room.shared_headers.map(hex2).join(", ")}. A terrain edit affects every listed definition.</p>${!doc.map.palette ? '<p class="notice">Color-index grayscale preview. This room’s live palette has not been verified.</p>' : ""}<div class="field-row">${select("maps-mode", "Canvas tool", [["inspect", "Inspect terrain command"], ["place", "Place selected definition"]], view.mode)}${button(view.overview ? "Return to readable crop" : "Show full overview", "maps-overview")}${button("Left", "maps-pan", { id: "-8,0" })}${button("Right", "maps-pan", { id: "8,0" })}${button("Up", "maps-pan", { id: "0,-6" })}${button("Down", "maps-pan", { id: "0,6" })}</div><div class="level-editor-layout game-map-layout"><div><div class="preview-pair game-map-previews"><div><span>Original for this edit · selected ROM</span><canvas id="maps-original" aria-label="Original decoded game terrain"></canvas></div><div><span>${(pending == null ? void 0 : pending.result.preview_map) ? "Reviewed terrain · exact planned bytes" : "Staged placement overlay"}</span><canvas id="maps-edit" tabindex="0" aria-label="Decoded game map: inspect or place selected definition"></canvas></div></div><p id="maps-position" role="status">Readable crop around (${view.center.join(", ")}). NPC and arrival markers are outlines, not character artwork.</p><p>${(pending == null ? void 0 : pending.result.preview_map) ? "The reviewed terrain comes from the server’s bounded decoder." : "Placement outlines show staged coordinates. Review computes exact terrain, including restored and overwritten cells."}</p></div>${form}</div><div class="actions">${button("Undo staged edit", "maps-undo", { disabled: !model.past.length })}${button("Redo staged edit", "maps-redo", { disabled: !model.future.length })}${button("Clear staged edits", "maps-clear", { disabled: !model.values().length })}${button("Review map changes", "maps-review", { disabled: !model.values().length, primary: !pending })}</div><p>${model.values().length} staged records. The selected ROM remains unchanged.</p>${pending ? review(pending.result) : ""}${definitions(doc)}</section>`;
  }
  function definitions(doc) {
    return `<details><summary>NPC conditions and interactions</summary><p>These records are conditional definitions, not a list of characters guaranteed to be visible now. Interaction destinations remain read-only.</p><table><thead><tr><th>NPC definition</th><th>Position</th><th>Condition</th></tr></thead><tbody>${doc.objects.map((n) => `<tr><td>${esc(objectName(doc.room, n))}</td><td>${n.x}, ${n.y}</td><td>${esc(n.state_status || "Live condition unobserved")}</td></tr>`).join("")}</tbody></table><table><thead><tr><th>Interaction</th><th>Destination</th></tr></thead><tbody>${doc.links.map((l) => `<tr><td>${l.index}</td><td>${l.transition.kind === "saved-return" ? "Saved return to the previous location" : l.destination ? `Room ${esc(hex2(l.destination.header))} · ${l.destination.x}, ${l.destination.y}` : `Event reference ${esc(hex2(l.word))} · not a direct room destination`}</td></tr>`).join("")}</tbody></table></details>`;
  }
  function review(plan) {
    return `<section class="game-review"><h3>Review map changes</h3><p>${plan.edits.length} checked byte spans${plan.integrity_edit_count ? ` including ${plan.integrity_edit_count} integrity updates` : ""}. A separate build needs its own door and story playtests.</p><details><summary>Exact changed bytes</summary><table><thead><tr><th>Offset</th><th>Before</th><th>After</th></tr></thead><tbody>${plan.edits.map((e) => `<tr><td>${hex2(e.offset)}</td><td><code>${esc(e.before)}</code></td><td><code>${esc(e.after)}</code></td></tr>`).join("")}</tbody></table></details>${button("Create separate map build", "maps-build", { primary: true })}</section>`;
  }
  function mountGameMaps(ctx2) {
    var _a, _b, _c, _d;
    const view = ctx2.state.gameMapsView;
    if (!view || view.scope !== selectionKey(ctx2.state) || !view.model) return;
    const original = document.getElementById("maps-original"), canvas = document.getElementById("maps-edit");
    if (!canvas || !original) return;
    const scope = view.scope, epoch = view.epoch, current2 = () => scope === selectionKey(ctx2.state) && ctx2.state.gameMapsView === view && view.active && view.epoch === epoch && (ctx2.state.page === void 0 || ctx2.state.page === "levels");
    const map = view.model.doc.map, crop = cropMap(view.center, view.overview), pending = ((_a = view.pending) == null ? void 0 : _a.revision) === view.model.revision ? view.pending : null;
    function draw2(node, cells, editing) {
      const image = mapPixels2(map, crop, cells), g = node.getContext("2d");
      node.width = image.width;
      node.height = image.height;
      node.style.imageRendering = "pixelated";
      node.style.maxWidth = "100%";
      const frame = g.createImageData(image.width, image.height);
      frame.data.set(image.pixels);
      g.putImageData(frame, 0, 0);
      const scale = crop.scale, doc = view.model.doc, objects = editing ? (pending == null ? void 0 : pending.result.preview_objects) || doc.objects.map((n) => view.model.changed(n, "npc")) : doc.objects, arrivals = editing ? (pending == null ? void 0 : pending.result.preview_arrivals) || doc.arrivals.map((a) => view.model.changed(a, "arrival")) : doc.arrivals;
      const mark = (entity, color, label) => {
        if (entity.x < crop.x || entity.y < crop.y || entity.x >= crop.x + crop.width || entity.y >= crop.y + crop.height) return;
        const x = (entity.x - crop.x) * scale, y = (entity.y - crop.y) * scale;
        g.strokeStyle = color;
        g.lineWidth = 1;
        g.strokeRect(x + 1, y + 1, scale - 2, scale - 2);
        if (scale >= 12 && g.fillText) {
          g.fillStyle = color;
          g.font = "10px sans-serif";
          g.fillText(label, x + 2, y + 11);
        }
      };
      arrivals.forEach((a) => mark(a, "#3ba9ff", "A"));
      objects.forEach((n) => mark(n, "#ffbc49", "N"));
      const chosen = editing ? currentTarget(view) : selected(view);
      if (chosen) mark(chosen.entity, "#f7478c", "•");
    }
    draw2(original, map.cells, false);
    draw2(canvas, ((_b = pending == null ? void 0 : pending.result.preview_map) == null ? void 0 : _b.cells) || map.cells, true);
    canvas.addEventListener("click", (event) => {
      var _a2;
      if (!current2()) return;
      const point = mapPoint(crop, canvas.getBoundingClientRect(), { x: event.clientX, y: event.clientY });
      if (!point) return;
      const [x, y] = point;
      if (view.mode === "place") {
        const chosen = selected(view);
        if (!canEdit(view, chosen)) return ctx2.notify("Select an editable existing command, NPC or arrival first.");
        view.model.stage({ kind: chosen.kind, ...chosen.kind === "arrival" ? { table: chosen.entity.table, id: chosen.entity.id } : { offset: chosen.entity.offset }, x, y });
        view.formDirty = false;
        view.pending = null;
        view.reviewSerial++;
        view.persist();
      } else {
        const offset = (((_a2 = pending == null ? void 0 : pending.result.preview_map) == null ? void 0 : _a2.provenance) || map.provenance)[y * 64 + x];
        if (map.commands.some((c) => c.offset === offset)) view.selection = `command:${offset}`;
      }
      view.center = [x, y];
      ctx2.render();
    });
    for (const [id, action] of [["maps-target", "maps-select"], ["maps-mode", "maps-mode"]]) (_c = document.getElementById(id)) == null ? void 0 : _c.addEventListener("change", () => {
      if (!current2()) return;
      if (action === "maps-select") {
        view.selection = read(id);
        view.formDirty = false;
        const chosen = currentTarget(view);
        if (chosen) view.center = [chosen.entity.x, chosen.entity.y];
      } else view.mode = read(id);
      ctx2.render();
    });
    for (const id of ["maps-x", "maps-y", "maps-tile"]) (_d = document.getElementById(id)) == null ? void 0 : _d.addEventListener("input", () => {
      var _a2;
      if (!current2()) return;
      view.formDirty = true;
      view.pending = null;
      view.reviewSerial++;
      (_a2 = document.querySelectorAll) == null ? void 0 : _a2.call(document, '[data-action="maps-build"]').forEach((node) => node.disabled = true);
      const status = document.getElementById("maps-position");
      if (status) status.textContent = "Fields changed. Stage position / tile, then review again.";
    });
  }

  // romancer/ui/views/levels.js
  var codecs = { nes: "tile8-planar2-msb-v1", snes: "tile8-paired4-msb-v1", genesis: "tile8-packed4-high-v1", gb: "tile8-paired2-msb-v1", gbc: "tile8-paired2-msb-v1", gba: "tile8-packed4-low-v1" };
  var objectInteger = (id) => {
    const text = read(id).trim();
    if (!/^\d+$/.test(text)) throw Error("Enter a whole number for every object field.");
    return Number(text);
  };
  var practiceControls = () => `<details class="card"><summary>Advanced practice</summary><p>Open a separate test layout to learn the editor controls.</p>${button("Open test layout", "studio-example")}</details>`;
  async function render15(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l;
    const { state: state2 } = ctx2;
    ctx2.use({ "studio-example": async () => {
      const result = await ctx2.api.job("studio.example", {});
      await ctx2.openProject(result.project_id);
      return ctx2.navigate("levels");
    } });
    if (!state2.project || !state2.artifact) return heading("", "Levels", "") + empty("Choose a project or import a ROM", "Choose a project above, or import your ROM to get started.", button("Import ROM", "import", { primary: true })) + practiceControls();
    const scope = selectionKey(state2), current2 = () => scope === selectionKey(state2), saved = (_a = state2.artifact.descriptors) == null ? void 0 : _a.levels;
    let doc = state2.results["levels.inspect"];
    if ((doc == null ? void 0 : doc.source_sha256) !== state2.artifact.sha256) doc = null;
    if (!doc && (saved == null ? void 0 : saved.source_sha256) === state2.artifact.sha256) {
      try {
        doc = await ctx2.api.call("levels.inspect", { ...ctx2.sourceParams(), definition: saved });
      } catch {
        doc = null;
      }
      if (!current2() || ((_b = ctx2.isCurrentRender) == null ? void 0 : _b.call(ctx2)) === false) return "";
      if (doc) state2.results["levels.inspect"] = doc;
    }
    state2.levelRoomVisualScope = null;
    state2.gameMapRenderScope = null;
    if (!(doc == null ? void 0 : doc.ok) && !saved) {
      let game;
      try {
        game = await ctx2.api.call("games.inspect", ctx2.sourceParams());
      } catch {
      }
      if (!current2() || ((_c = ctx2.isCurrentRender) == null ? void 0 : _c.call(ctx2)) === false) return "";
      if (((_d = game == null ? void 0 : game.profile) == null ? void 0 : _d.id) === "ffl2-usa" && (game.map_workbench || ((_e = game.visual) == null ? void 0 : _e.kind) === "room-map")) {
        ctx2.use({ "ffl2-maps-open": () => {
          if (!current2()) return;
          ctx2.setDraft("ffl2-map-mode", "browser");
          return ctx2.render();
        } });
        if (ctx2.draft("ffl2-map-mode", "simple") === "browser" || !game.visual) {
          const markup2 = await gameMaps(ctx2, { simpleAvailable: ((_f = game.visual) == null ? void 0 : _f.kind) === "room-map" });
          if (!current2() || ((_g = ctx2.isCurrentRender) == null ? void 0 : _g.call(ctx2)) === false) return "";
          state2.gameMapRenderScope = scope;
          return heading("", "Levels", "") + markup2;
        }
        const markup = await gameEdits(ctx2);
        if (!current2() || ((_h = ctx2.isCurrentRender) == null ? void 0 : _h.call(ctx2)) === false) return "";
        state2.levelRoomVisualScope = scope;
        return heading("", "Levels", "") + `<section class="card"><h3>Explore the actual game</h3><p>Open the ROM’s room catalog, terrain commands, NPC definitions and arrivals.</p>${button("Browse game maps", "ffl2-maps-open")}</section>` + markup;
      }
      if (((_i = game == null ? void 0 : game.visual) == null ? void 0 : _i.kind) === "room-map") {
        const markup = await gameEdits(ctx2);
        if (!current2() || ((_j = ctx2.isCurrentRender) == null ? void 0 : _j.call(ctx2)) === false) return "";
        state2.levelRoomVisualScope = scope;
        return heading("", "Levels", "") + markup;
      }
    }
    const definition = (doc == null ? void 0 : doc.definition) || saved || {};
    let model = state2.levelEditor;
    if ((doc == null ? void 0 : doc.ok) && ((model == null ? void 0 : model.scope) !== scope || model.doc.document_id !== doc.document_id)) {
      let changes = [];
      try {
        const draft = JSON.parse(ctx2.draft("level-changes", "{}"));
        if (draft.document_id === doc.document_id) changes = draft.changes;
      } catch {
      }
      model = new LevelDraft(doc, changes);
      model.scope = scope;
      state2.levelEditor = model;
    }
    const room = (doc == null ? void 0 : doc.rooms.find((r) => r.id === ctx2.draft("level-room", ""))) || (doc == null ? void 0 : doc.rooms[0]), layer = ctx2.draft("level-layer", "terrain");
    const persist = () => {
      if (!current2()) return;
      state2.historyEditor = "level-canvas";
      ctx2.setDraft("level-changes", JSON.stringify({ document_id: doc.document_id, changes: model.values() }));
      state2.pending = null;
    };
    const change = (action) => {
      if (!current2()) return;
      model.begin();
      try {
        action();
        model.commit();
        persist();
        return ctx2.render();
      } catch (error) {
        model.cancel();
        throw error;
      }
    };
    ctx2.use({
      "levels-inspect": () => ctx2.run("levels.inspect", { ...ctx2.sourceParams(), definition: json("level-definition") }),
      "levels-save": () => ctx2.run("studio.definition", { ...ctx2.sourceParams(), kind: "levels", definition: json("level-definition") }),
      "levels-declare": () => {
        const n = (id) => Number(read("level-" + id)), g = (offset) => ({ offset, entry_bytes: n("entry"), endian: read("level-endian") }), next = { schema_version: 1, source_sha256: state2.artifact.sha256, name: read("level-name"), tiles: { offset: n("tiles-offset"), count: n("tiles-count"), codec: read("level-codec"), palette_offset: n("palette-offset"), palette_format: read("level-palette-format") }, metatiles: { ...g(n("blocks-offset")), count: n("blocks-count"), width: n("block-width"), height: n("block-height") }, rooms: [{ id: "room-0", name: read("level-name"), width: n("width"), height: n("height"), terrain: g(n("terrain-offset")), collision: read("level-collision-offset").trim() ? g(n("collision-offset")) : null, objects: null }] };
        ctx2.setDraft("level-definition", JSON.stringify(next, null, 2));
        return ctx2.run("levels.inspect", { ...ctx2.sourceParams(), definition: next });
      },
      "levels-room": () => {
        state2.levelRect = null;
        return ctx2.render();
      },
      "levels-open-room": (node) => {
        if (!current2()) return;
        model.room(node.dataset.id);
        ctx2.setDraft("level-room", node.dataset.id);
        ctx2.setDraft("level-object-index", "0");
        ctx2.setDraft("level-layer", "terrain");
        state2.levelRect = null;
        return ctx2.render();
      },
      "levels-select-object": (node) => {
        if (!current2()) return;
        const id = node.dataset.name, index = Number(node.dataset.id), objects2 = model.objects(id);
        if (!Number.isSafeInteger(index) || index < 0 || index >= objects2.length) throw Error("Unknown object slot.");
        ctx2.setDraft("level-room", id);
        ctx2.setDraft("level-object-index", String(index));
        ctx2.setDraft("level-overlay", "objects");
        ctx2.setDraft("level-tool", Number.isSafeInteger(objects2[index].x) && Number.isSafeInteger(objects2[index].y) ? "objects" : "paint");
        state2.levelRect = null;
        return ctx2.render();
      },
      "levels-object-apply": () => change(() => {
        const index = objectInteger("level-object-index"), objects2 = model.objects(room.id);
        if (!Number.isSafeInteger(index) || index < 0 || index >= objects2.length) throw Error("Unknown object slot.");
        const metadata = objectMetadata(doc, room.id, index), reference = (metadata == null ? void 0 : metadata.role) === "exit" ? metadata.reference : null, changes = objectFields(doc, room.id).map((field2, position) => ({ kind: "object", room_id: room.id, index, field: field2.name, value: objectInteger((reference == null ? void 0 : reference.field) === field2.name ? "level-object-destination" : "level-object-input-" + position) }));
        changes.forEach((change2) => model.set(change2));
      }),
      "levels-undo": () => {
        if (current2()) {
          model.undo();
          persist();
          return ctx2.render();
        }
      },
      "levels-redo": () => {
        if (current2()) {
          model.redo();
          persist();
          return ctx2.render();
        }
      },
      "levels-copy": () => {
        if (!state2.levelRect) throw Error("Use Select rectangle on the canvas first.");
        state2.levelClipboard = model.copy(room.id, read("level-layer"), state2.levelRect);
        ctx2.notify("Rectangle copied. Choose Paste and click its new top-left cell.");
      },
      "levels-block": () => change(() => model.set({ kind: "metatile", index: Number(read("level-block-index")), part: Number(read("level-block-part")), value: Number(read("level-block-tile")) })),
      "levels-object": () => change(() => model.set({ kind: "object", room_id: room.id, index: Number(read("level-object-index")), field: read("level-object-field"), value: Number(read("level-object-value")) })),
      "levels-plan": async () => {
        var _a2;
        if (!current2() || !doc) throw Error("Inspect this layout first.");
        const changes = model.values(), result = await ctx2.run("levels.plan", { ...ctx2.sourceParams(), definition: doc.definition, document_id: doc.document_id, changes }, { render: false });
        if (!current2() || ((_a2 = state2.results["levels.inspect"]) == null ? void 0 : _a2.document_id) !== doc.document_id || state2.levelEditor !== model || JSON.stringify(model.values()) !== JSON.stringify(changes)) return ctx2.render();
        state2.pending = { kind: "levels", artifact_id: state2.artifact.artifact_id, document_id: doc.document_id, plan_id: result.plan_id, changes: JSON.stringify(changes) };
        return ctx2.render();
      },
      "levels-build": async () => {
        var _a2, _b2;
        if (!current2() || ((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "levels" || state2.pending.artifact_id !== state2.artifact.artifact_id || state2.pending.document_id !== (doc == null ? void 0 : doc.document_id) || ((_b2 = state2.results["levels.inspect"]) == null ? void 0 : _b2.document_id) !== (doc == null ? void 0 : doc.document_id) || state2.pending.changes !== JSON.stringify(model.values())) throw Error("Review the current level changes first.");
        const submitted = ctx2.draft("level-changes", "{}"), submittedValues = JSON.stringify(model.values());
        await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: state2.pending.plan_id }, { render: false });
        if (!current2()) return;
        const activeStroke = state2.levelEditor === model && model.start !== null;
        const unchanged = state2.levelEditor === model && !activeStroke && ctx2.draft("level-changes", "{}") === submitted && JSON.stringify(model.values()) === submittedValues;
        if (unchanged) {
          model.changes.clear();
          model.past = [];
          model.future = [];
          persist();
        } else state2.pending = null;
        if (!activeStroke) await ctx2.render();
        ctx2.notify(unchanged ? "Separate level build created. Select it in Playtest." : "Separate level build created. Your newer edits are still staged.");
      }
    });
    const setup2 = `<details class="card"><summary>Advanced level setup</summary><p>Level editing needs a layout definition for this ROM. Confirm tile grids, object fields, and room-reference mappings before using them. Names and roles alone do not establish game behavior.</p><details><summary>Single-room layout form</summary><div class="field-row">${field("level-name", "Room name", ctx2.draft("level-name", "Room"))}${field("level-width", "Blocks across", ctx2.draft("level-width", "16"), { type: "number", min: 1 })}${field("level-height", "Blocks down", ctx2.draft("level-height", "14"), { type: "number", min: 1 })}${select("level-entry", "Grid integer bytes", [[1, "8 bit"], [2, "16 bit"]], ctx2.draft("level-entry", "1"))}${select("level-endian", "Grid byte order", [["little", "Little endian"], ["big", "Big endian"]], ctx2.draft("level-endian", "little"))}</div><div class="field-row">${field("level-tiles-offset", "Tiles offset", ctx2.draft("level-tiles-offset", "0"))}${field("level-tiles-count", "Tile count", ctx2.draft("level-tiles-count", "16"))}${select("level-codec", "Tile format", Object.entries(codecs).map(([system2, codec]) => [codec, system2.toUpperCase()]), ctx2.draft("level-codec", codecs[state2.artifact.system_id] || codecs.nes))}${field("level-palette-offset", "Palette offset", ctx2.draft("level-palette-offset", "0"))}${select("level-palette-format", "Palette format", [["rgb888", "RGB888"], ["rgb555-le", "RGB555 little endian"], ["rgb555-be", "RGB555 big endian"]], ctx2.draft("level-palette-format", "rgb555-le"))}</div><div class="field-row">${field("level-blocks-offset", "Metatile table offset", ctx2.draft("level-blocks-offset", "0"))}${field("level-blocks-count", "Metatile count", ctx2.draft("level-blocks-count", "16"))}${field("level-block-width", "Tiles per block across", ctx2.draft("level-block-width", "2"))}${field("level-block-height", "Tiles per block down", ctx2.draft("level-block-height", "2"))}${field("level-terrain-offset", "Terrain grid offset", ctx2.draft("level-terrain-offset", "0"))}${field("level-collision-offset", "Collision grid offset (optional)", ctx2.draft("level-collision-offset", ""))}</div>${button("Check declared layout", "levels-declare")}</details>${jsonEditor("level-definition", "Verified layout definition", ctx2.draft("level-definition", JSON.stringify(definition, null, 2)))}<div class="actions">${button("Inspect layout", "levels-inspect")}${button("Save checked definition", "levels-save")}</div></details>`;
    if (!(doc == null ? void 0 : doc.ok)) return heading("", "Levels", "") + empty("No supported level map for this ROM yet", "Inspect the ROM in Resources. A supported map definition is needed before its levels can be shown.", button("Investigate bytes", "navigate", { id: "resources", primary: true })) + setup2 + practiceControls();
    const objects = model.objects(room.id), namedObjects = objects.some((object, index) => !!objectMetadata(doc, room.id, index)), block = Number(ctx2.draft("level-block-index", "0")), uses = doc.uses[String(block)] || [], pending = ((_k = state2.pending) == null ? void 0 : _k.kind) === "levels" && state2.pending.document_id === doc.document_id;
    return `${heading("", "Levels", "")}<div class="identity"><strong>${esc(state2.artifact.name)}</strong><span>${model.values().length} preview changes</span></div><section class="card">${state2.project.demo && ((_l = doc.definition) == null ? void 0 : _l.name) === "Hillside editor-layout workshop" ? '<p class="notice">Practice layout. These room links and object records do not run in Playtest; only Hillside terrain and music do.</p>' : ""}${roomNavigation(doc, model, room.id)}<div class="field-row level-toolbar">${select("level-room", "Room", doc.rooms.map((r) => [r.id, r.name]), room.id)}${select("level-layer", "Paint layer", [["terrain", "Terrain"], ...room.collision ? [["collision", "Collision values"]] : []], layer)}${select("level-tool", "Tool", [["paint", "Paint"], ["pick", "Pick from room"], ["fill", "Fill"], ["select", "Select rectangle"], ["paste", "Paste rectangle"], ...objects.some((o) => Number.isSafeInteger(o.x) && Number.isSafeInteger(o.y)) ? [["objects", "Move object"]] : []], ctx2.draft("level-tool", namedObjects ? "objects" : "paint"))}<details><summary>Advanced brush value</summary>${field("level-brush", "Brush value", ctx2.draft("level-brush", "1"), { type: "number", min: 0 })}</details>${select("level-overlay", "Overlay", [["none", "Terrain only"], ...room.collision ? [["collision", "Collision values"]] : [], ...objects.length ? [["objects", "Named objects"], ["records", "All records (Advanced)"]] : []], ctx2.draft("level-overlay", "objects"))}${select("level-zoom", "Zoom", [["fit", "Fit"], ["1", "1x"], ["2", "2x"], ["3", "3x"]], ctx2.draft("level-zoom", "fit"))}</div><div class="level-brush-panel"><strong>Terrain brushes</strong><p class="subtle">Choose a thumbnail to paint, or use Pick from room to sample an existing cell.</p>${levelBrushPalette(doc, model, ctx2.draft("level-brush", "1"))}</div><div class="level-editor-layout"><div class="level-room-editor"><div class="preview-pair room-comparison"><div><span>Original room</span><div class="hex-scroll"><canvas id="level-original" aria-label="Original declared room"></canvas></div></div><div><span>Editing · highlighted cells changed</span><div class="hex-scroll"><canvas id="level-canvas" tabindex="0" role="application" aria-label="Room editor: arrows select, Space paints"></canvas></div></div></div><p id="level-difference-count" class="preview-caption" role="status" aria-live="polite"></p><p id="level-position">Select an object or choose a terrain brush to begin.</p></div>${objectInspector(ctx2, doc, model, room.id)}</div><div class="actions">${button("Undo stroke", "levels-undo", { disabled: !model.past.length })}${button("Redo stroke", "levels-redo", { disabled: !model.future.length })}${button("Copy rectangle", "levels-copy")}${button("Review level changes", "levels-plan", { primary: !pending, disabled: !model.values().length })}${pending ? button("Create level build", "levels-build", { primary: true }) : ""}</div><p class="subtle">Review changes and create a build to save this in the ROM.</p></section><details class="card"><summary>Metatiles & shared uses</summary><div class="field-row">${field("level-block-index", "Metatile index", ctx2.draft("level-block-index", "0"))}${field("level-block-part", "Part index", ctx2.draft("level-block-part", "0"))}${field("level-block-tile", "Replacement tile index", ctx2.draft("level-block-tile", "1"))}</div>${button("Stage block change", "levels-block")}<p>Selected block is used in ${uses.length} declared cells. Changes affect every use.</p><p>${uses.slice(0, 32).map((u) => esc(u.room_id) + " cell " + u.cell).join(" · ")}</p></details>${setup2}${practiceControls()}${report(state2.results["levels.plan"], "Level review")}${report(state2.results["build.apply"], "Separate build")}`;
  }
  function mount10(ctx2) {
    var _a, _b, _c, _d, _e, _f, _g;
    if (ctx2.state.gameMapRenderScope === selectionKey(ctx2.state)) {
      mountGameMaps(ctx2);
      return;
    }
    if (ctx2.state.levelRoomVisualScope === selectionKey(ctx2.state) && ((_c = (_b = (_a = ctx2.state.gameVisualModel) == null ? void 0 : _a.model) == null ? void 0 : _b.visual) == null ? void 0 : _c.kind) === "room-map") {
      mountGameVisual(ctx2);
      return;
    }
    const doc = ctx2.state.results["levels.inspect"], model = ctx2.state.levelEditor;
    if (!(doc == null ? void 0 : doc.ok) || (model == null ? void 0 : model.scope) !== selectionKey(ctx2.state)) return;
    const id = (_d = document.getElementById("level-room")) == null ? void 0 : _d.value;
    if (!id) return;
    const persist = () => {
      ctx2.setDraft("level-changes", JSON.stringify({ document_id: doc.document_id, changes: model.values() }));
      ctx2.state.pending = null;
    };
    (_e = document.getElementById("level-room")) == null ? void 0 : _e.addEventListener("change", (event) => {
      ctx2.setDraft("level-room", event.target.value);
      ctx2.setDraft("level-object-index", "0");
      ctx2.setDraft("level-layer", "terrain");
      ctx2.state.levelRect = null;
      ctx2.render();
    });
    (_f = document.getElementById("level-object-index")) == null ? void 0 : _f.addEventListener("change", (event) => {
      ctx2.setDraft("level-object-index", event.target.value);
      ctx2.render();
    });
    (_g = document.getElementById("level-overlay")) == null ? void 0 : _g.addEventListener("change", (event) => {
      ctx2.setDraft("level-overlay", event.target.value);
      ctx2.render();
    });
    mountLevel(ctx2, doc, model, id, persist);
    mountRoomNavigation(doc, model);
  }

  // romancer/ui/views/sound.js
  var sound_exports = {};
  __export(sound_exports, {
    mount: () => mount11,
    render: () => render16
  });

  // romancer/ui/sound_preview.js
  var WavPreview = class {
    constructor(urls = { create: (blob) => URL.createObjectURL(blob), revoke: (url) => URL.revokeObjectURL(url) }) {
      this.urls = urls;
      this.audio = null;
      this.url = null;
    }
    attach(audio, encoded) {
      this.close();
      if (typeof encoded !== "string" || encoded.length > 6 * 1024 * 1024) throw Error("Audio preview exceeds its byte budget.");
      const raw = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
      if (String.fromCharCode(...raw.slice(0, 4)) !== "RIFF" || String.fromCharCode(...raw.slice(8, 12)) !== "WAVE") throw Error("Preview is not a WAV file.");
      this.url = this.urls.create(new Blob([raw], { type: "audio/wav" }));
      this.audio = audio;
      audio.src = this.url;
      const prefs = getSettings();
      audio.volume = prefs.volume / 100;
      audio.muted = prefs.startMuted;
      audio.loop = prefs.loopPreview;
    }
    close() {
      if (this.audio) {
        try {
          this.audio.pause();
          this.audio.removeAttribute("src");
          this.audio.load();
        } catch {
        }
        this.audio = null;
      }
      if (this.url) {
        this.urls.revoke(this.url);
        this.url = null;
      }
    }
  };
  function decodedWav(encoded) {
    if (typeof encoded !== "string" || encoded.length > 6 * 1024 * 1024) throw Error("Audio preview exceeds its byte budget.");
    const raw = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)), view = new DataView(raw.buffer), tag = (at) => String.fromCharCode(...raw.slice(at, at + 4));
    if (raw.length < 44 || tag(0) !== "RIFF" || tag(8) !== "WAVE" || view.getUint32(4, true) + 8 !== raw.length) throw Error("Decoded preview is not a complete PCM WAV.");
    let format = null, pcm = null, chunks = 0;
    for (let at = 12; at + 8 <= raw.length; ) {
      if (++chunks > 1024) throw Error("WAV chunk budget exceeded.");
      const size2 = view.getUint32(at + 4, true), start = at + 8, end = start + size2;
      if (end > raw.length) throw Error("Decoded WAV contains a truncated chunk.");
      if (tag(at) === "fmt ") {
        if (size2 < 16) throw Error("Decoded WAV format is incomplete.");
        format = { codec: view.getUint16(start, true), channels: view.getUint16(start + 2, true), sample_rate: view.getUint32(start + 4, true), block: view.getUint16(start + 12, true), bits: view.getUint16(start + 14, true) };
      }
      if (tag(at) === "data") {
        if (pcm) throw Error("Decoded WAV has duplicate audio data.");
        pcm = raw.subarray(start, end);
      }
      at = end + size2 % 2;
    }
    if (!format || format.codec !== 1 || format.bits !== 16 || ![1, 2].includes(format.channels) || !format.sample_rate || format.sample_rate > 384e3 || format.block !== format.channels * 2 || !(pcm == null ? void 0 : pcm.length) || pcm.length % format.block) throw Error("Preview waveform requires decoded 16-bit mono or stereo PCM.");
    return { pcm, channels: format.channels, sample_rate: format.sample_rate, frames: pcm.length / format.block };
  }
  function waveform(decoded) {
    const { pcm, channels, sample_rate, frames } = decoded, view = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength), step = Math.max(1, Math.ceil(frames / 512)), peaks = [];
    for (let first = 0; first < frames; first += step) {
      let low = 32767, high = -32768;
      for (let i = first * channels; i < Math.min(frames, first + step) * channels; i++) {
        const value = view.getInt16(i * 2, true);
        low = Math.min(low, value);
        high = Math.max(high, value);
      }
      peaks.push([low, high]);
    }
    return { peaks, channels, sample_rate, frames };
  }
  function compareWavPreviews(original, edited) {
    const before = decodedWav(original), after = decodedWav(edited), changed2 = before.channels !== after.channels || before.sample_rate !== after.sample_rate || before.pcm.length !== after.pcm.length || before.pcm.some((value, i) => value !== after.pcm[i]);
    return { original: waveform(before), edited: waveform(after), changed: changed2 };
  }
  function drawWaveform(canvas, peaks) {
    if (!canvas) return;
    const c = canvas.getContext("2d"), middle = canvas.height / 2, amplitude = Math.max(0, middle - 5);
    c.fillStyle = "#102127";
    c.fillRect(0, 0, canvas.width, canvas.height);
    c.strokeStyle = "#73d7ba";
    c.beginPath();
    for (const [i, [low, high]] of peaks.entries()) {
      const x = i / (peaks.length - 1 || 1) * canvas.width;
      c.moveTo(x, middle - low / 32768 * amplitude);
      c.lineTo(x, middle - high / 32768 * amplitude);
    }
    c.stroke();
  }
  function stageNote(doc, changes, songId, index, field2, value) {
    const song = doc.songs.find((s) => s.id === songId), bounds2 = { note: [33, 108], duration: [1, 6e3], volume: [0, 127] };
    if (!song || !Number.isInteger(index) || index < 0 || index >= song.events.length || !bounds2[field2] || !Number.isInteger(value) || value < bounds2[field2][0] || value > bounds2[field2][1]) throw Error("Choose a supported song field and an in-range value.");
    const result = changes.filter((c) => !(c.kind === "note" && c.song_id === songId && c.index === index && c.field === field2));
    if (value !== song.events[index][field2]) result.push({ kind: "note", song_id: songId, index, field: field2, value });
    return result;
  }
  function restoreSoundChanges(doc, encoded) {
    if (!doc) return [];
    const saved = JSON.parse(encoded);
    if ((saved == null ? void 0 : saved.document_id) !== doc.document_id) return [];
    if (!Array.isArray(saved.changes) || saved.changes.length > 256) throw Error("Saved audio edits exceed the change budget.");
    let result = [];
    const seen = /* @__PURE__ */ new Set();
    for (const c of saved.changes) {
      if (!c || typeof c !== "object" || Array.isArray(c)) throw Error("Saved audio edits contain an invalid change.");
      const key3 = JSON.stringify([c.kind, c.song_id ?? c.sample_id, c.index, c.field]);
      if (seen.has(key3)) throw Error("Saved audio edits contain duplicate changes.");
      seen.add(key3);
      if (c.kind === "note") result = stageNote(doc, result, c.song_id, c.index, c.field, c.value);
      else if (c.kind === "sample") {
        if (!doc.samples.some((s) => s.id === c.sample_id) || !["gain", "reverse", "silence", "replace_wav"].includes(c.operation)) throw Error("Saved audio edits reference an unsupported sample.");
        if (c.operation === "gain" && (!Number.isInteger(c.value) || c.value < 0 || c.value > 400)) throw Error("Saved audio edits contain an invalid gain.");
        const next = { kind: "sample", sample_id: c.sample_id, operation: c.operation, value: c.operation === "gain" ? c.value : 0, wav_base64: null };
        if (c.operation === "replace_wav") {
          if (typeof c.wav_input_id !== "string" || !/^[a-f0-9]{32}$/.test(c.wav_input_id) || c.wav_base64 !== null) throw Error("Saved audio edits need an owned replacement WAV.");
          next.wav_input_id = c.wav_input_id;
        }
        result.push(next);
      } else throw Error("Saved audio edits contain an unsupported change.");
    }
    return result;
  }

  // romancer/ui/views/sound.js
  var codecNames = { "pcm-u8": "Unsigned8-bit PCM", "pcm-s8": "Signed8-bit PCM", "pcm-s16le": "Signed16-bit PCM (LE)", "pcm-s16be": "Signed16-bit PCM (BE)", "gb-wave4": "Game Boy32-sample wave", "nes-dpcm": "NES DPCM", "snes-brr": "SNES BRR (standalone)" };
  function clearPreview(state2) {
    var _a;
    state2.soundPreviewGeneration = (state2.soundPreviewGeneration || 0) + 1;
    (_a = state2.soundPlayer) == null ? void 0 : _a.close();
    state2.soundPlayer = null;
    state2.soundPreview = null;
    state2.soundPreviewRequest = null;
  }
  function ownsPreview(ctx2, owned) {
    var _a, _b;
    const { state: state2 } = ctx2, doc = state2.results["sound.inspect"];
    if (!owned || owned.selection_scope !== selectionKey(state2) || owned.generation !== state2.soundPreviewGeneration || state2.page && state2.page !== "sound" || (doc == null ? void 0 : doc.document_id) !== owned.document_id || doc.source_sha256 !== ((_a = state2.artifact) == null ? void 0 : _a.sha256)) return false;
    const rows = owned.kind === "sample" ? doc.samples : doc.songs, selected2 = ctx2.draft(owned.kind === "sample" ? "sound-sample" : "sound-song", "") || ((_b = rows[0]) == null ? void 0 : _b.id);
    try {
      return selected2 === owned.resource_id && JSON.stringify(restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}"))) === owned.signature;
    } catch {
      return false;
    }
  }
  function visiblePreview(ctx2) {
    const packet = ctx2.state.soundPreview;
    return (packet == null ? void 0 : packet.selection_scope) === selectionKey(ctx2.state) && (!packet.document_id || ownsPreview(ctx2, packet)) ? packet : null;
  }
  async function previewSound(ctx2, doc, kind, id) {
    var _a, _b, _c;
    const { state: state2 } = ctx2, rows = kind === "sample" ? doc == null ? void 0 : doc.samples : doc == null ? void 0 : doc.songs;
    if (!(doc == null ? void 0 : doc.ok) || ((_a = state2.results["sound.inspect"]) == null ? void 0 : _a.document_id) !== doc.document_id || !(rows == null ? void 0 : rows.some((row) => row.id === id))) throw Error(kind === "song" ? "No supported music driver is identified for this source." : "Select a supported sample first.");
    const changes = restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}")), params = { ...ctx2.sourceParams(), definition: doc.definition, kind, resource_id: id };
    clearPreview(state2);
    const owned = { selection_scope: selectionKey(state2), document_id: doc.document_id, kind, resource_id: id, signature: JSON.stringify(changes), generation: state2.soundPreviewGeneration };
    state2.soundPreviewRequest = { ...owned, status: "loading" };
    await ctx2.render();
    try {
      const [original, edited] = await Promise.all([ctx2.api.call("sound.preview", { ...params, changes: [] }), ctx2.api.call("sound.preview", { ...params, changes })]);
      if (!ownsPreview(ctx2, owned)) return;
      if (original.ok === false || edited.ok === false) throw Error(((_b = original.error) == null ? void 0 : _b.message) || ((_c = edited.error) == null ? void 0 : _c.message) || original.error || edited.error || "Audio decoding failed.");
      if ([original, edited].some((result) => result.source_sha256 && result.source_sha256 !== doc.source_sha256 || result.kind && result.kind !== kind)) throw Error("Decoded audio belongs to a different source or resource.");
      const comparison = compareWavPreviews(original.wav_base64, edited.wav_base64);
      state2.soundPreview = { ...edited, ...owned, comparison };
      state2.soundPreviewRequest = { ...owned, status: "ready" };
    } catch (error) {
      if (!ownsPreview(ctx2, owned)) return;
      state2.soundPreview = null;
      state2.soundPreviewRequest = { ...owned, status: "error", message: error.message };
    }
    if (ownsPreview(ctx2, owned)) await ctx2.render();
  }
  async function render16(ctx2) {
    var _a, _b, _c, _d;
    const { state: state2 } = ctx2;
    if (!state2.project || !state2.artifact) return heading("", "Music & sound", "") + empty("Open a source to inspect audio", "Audio hardware and game music drivers are identified separately.");
    const scope = selectionKey(state2), current2 = () => scope === selectionKey(state2), params = { ...ctx2.sourceParams() }, saved = (_a = state2.artifact.descriptors) == null ? void 0 : _a.sound;
    const system2 = await ctx2.api.call("sound.system", params);
    if (!current2() || ((_b = ctx2.isCurrentRender) == null ? void 0 : _b.call(ctx2)) === false) return "";
    let doc = state2.results["sound.inspect"];
    if ((doc == null ? void 0 : doc.source_sha256) !== state2.artifact.sha256) doc = null;
    if (!doc && (saved == null ? void 0 : saved.source_sha256) === state2.artifact.sha256) {
      doc = await ctx2.api.call("sound.inspect", { ...params, definition: saved });
      if (!current2() || ((_c = ctx2.isCurrentRender) == null ? void 0 : _c.call(ctx2)) === false) return "";
      state2.results["sound.inspect"] = doc;
    }
    let changes = [], draftError = "";
    try {
      changes = restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}"));
    } catch {
      draftError = "Saved audio edits are invalid. Discard them before continuing.";
    }
    const sameDocument = () => {
      var _a2;
      return current2() && ((_a2 = state2.results["sound.inspect"]) == null ? void 0 : _a2.document_id) === (doc == null ? void 0 : doc.document_id);
    };
    const persist = (next) => {
      if (!sameDocument()) return;
      changes = next;
      ctx2.setDraft("sound-changes", JSON.stringify({ document_id: doc.document_id, changes }));
      state2.pending = null;
      clearPreview(state2);
    };
    const sample = (doc == null ? void 0 : doc.samples.find((s) => s.id === ctx2.draft("sound-sample", ""))) || (doc == null ? void 0 : doc.samples[0]), song = (doc == null ? void 0 : doc.songs.find((s) => s.id === ctx2.draft("sound-song", ""))) || (doc == null ? void 0 : doc.songs[0]);
    const preview = (kind, id) => previewSound(ctx2, doc, kind, id);
    ctx2.use({
      "sound-inspect": () => ctx2.run("sound.inspect", { ...params, definition: json("sound-definition") }),
      "sound-save": () => ctx2.run("studio.definition", { ...params, kind: "sound", definition: json("sound-definition") }),
      "sound-declare": () => {
        const definition = { schema_version: 1, source_sha256: state2.artifact.sha256, samples: [{ id: "sample-0", name: read("sound-name"), offset: Number(read("sound-offset")), length: Number(read("sound-length")), codec: read("sound-codec"), sample_rate: Number(read("sound-rate")), initial_level: Number(read("sound-initial")) }], songs: [] };
        ctx2.setDraft("sound-definition", JSON.stringify(definition, null, 2));
        return ctx2.run("sound.inspect", { ...params, definition });
      },
      "sound-select": () => ctx2.render(),
      "sound-sample-stage": async () => {
        var _a2;
        if (!sameDocument() || !sample) throw Error("Select a supported sample first.");
        const sampleBefore = JSON.stringify(restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}")).filter((c) => c.kind === "sample" && c.sample_id === sample.id)), operation = read("sound-operation"), change = { kind: "sample", sample_id: sample.id, operation, value: Number(read("sound-gain")), wav_base64: null };
        if (operation === "replace_wav") {
          const file = (_a2 = document.getElementById("sound-wav")) == null ? void 0 : _a2.files[0];
          if (!file || file.size > 2 * 1024 * 1024) throw Error("Choose a PCM WAV up to2MiB.");
          const input = await ctx2.api.uploadInput(state2.project.project_id, file, "audio");
          if (!sameDocument()) return;
          change.wav_input_id = input.input_id;
        }
        const latest = restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}"));
        if (JSON.stringify(latest.filter((c) => c.kind === "sample" && c.sample_id === sample.id)) !== sampleBefore) {
          ctx2.notify("Your newer sample edit is still staged. Select the WAV again to replace it.");
          return;
        }
        persist([...latest.filter((c) => !(c.kind === "sample" && c.sample_id === sample.id)), change]);
        return preview("sample", sample.id);
      },
      "sound-note-stage": () => {
        if (!song) throw Error("No supported music driver is identified for this source.");
        persist(stageNote(doc, restoreSoundChanges(doc, ctx2.draft("sound-changes", "{}")), song.id, Number(read("sound-event")), read("sound-note-field"), Number(read("sound-note-value"))));
        return preview("song", song.id);
      },
      "sound-transpose": () => {
        var _a2;
        if (!song) throw Error("No supported music driver is identified.");
        const shift = Number(read("sound-transpose"));
        if (!Number.isInteger(shift) || Math.abs(shift) > 24) throw Error("Transpose by at most24semitones.");
        let next = changes;
        for (let i = 0; i < song.events.length; i++) {
          const note = ((_a2 = changes.find((c) => c.kind === "note" && c.song_id === song.id && c.index === i && c.field === "note")) == null ? void 0 : _a2.value) ?? song.events[i].note;
          next = stageNote(doc, next, song.id, i, "note", note + shift);
        }
        persist(next);
        return preview("song", song.id);
      },
      "sound-sample-preview": () => preview("sample", sample == null ? void 0 : sample.id),
      "sound-song-preview": () => preview("song", song == null ? void 0 : song.id),
      "sound-capture": async () => {
        clearPreview(state2);
        const generation = state2.soundPreviewGeneration;
        const result = await ctx2.run("sound.capture", { ...params, frames: Number(read("sound-frames")) }, { render: false });
        if (!current2() || state2.soundPreviewGeneration !== generation) return;
        state2.frame = result.frame;
        delete result.frame;
        delete state2.results["sound.capture"];
        state2.soundPreview = { ...result, selection_scope: scope };
        return ctx2.render();
      },
      "sound-loop": () => {
        const audio = document.getElementById("sound-player");
        if (audio) audio.loop = !audio.loop;
        ctx2.notify((audio == null ? void 0 : audio.loop) ? "Preview loop on." : "Preview loop off.");
      },
      "sound-export-preview": () => {
        const value = state2.soundPreview;
        if ((value == null ? void 0 : value.selection_scope) !== scope) throw Error("Create a preview first.");
        const a = document.createElement("a"), blob = Uint8Array.from(atob(value.wav_base64), (c) => c.charCodeAt(0)), url = URL.createObjectURL(new Blob([blob], { type: "audio/wav" }));
        a.href = url;
        a.download = "sound-preview.wav";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 2e3);
      },
      "sound-plan": async () => {
        var _a2;
        if (!current2() || !doc) throw Error("Inspect supported audio first.");
        const submitted = ctx2.draft("sound-changes", "{}"), result = await ctx2.run("sound.plan", { ...params, definition: doc.definition, document_id: doc.document_id, changes }, { render: false });
        if (!current2() || ((_a2 = state2.results["sound.inspect"]) == null ? void 0 : _a2.document_id) !== doc.document_id || ctx2.draft("sound-changes", "{}") !== submitted) return ctx2.render();
        state2.pending = { kind: "sound", artifact_id: state2.artifact.artifact_id, document_id: doc.document_id, plan_id: result.plan_id, changes: JSON.stringify(changes) };
        return ctx2.render();
      },
      "sound-build": async () => {
        var _a2, _b2, _c2;
        if (!current2() || ((_a2 = state2.pending) == null ? void 0 : _a2.kind) !== "sound" || state2.pending.artifact_id !== state2.artifact.artifact_id || state2.pending.document_id !== (doc == null ? void 0 : doc.document_id) || ((_b2 = state2.results["sound.inspect"]) == null ? void 0 : _b2.document_id) !== (doc == null ? void 0 : doc.document_id) || state2.pending.changes !== JSON.stringify(changes)) throw Error("Review the current sound changes first.");
        const submitted = ctx2.draft("sound-changes", "{}");
        await ctx2.run("build.apply", { ...ctx2.projectParams(), plan_id: state2.pending.plan_id }, { render: false });
        if (!current2()) return;
        const unchanged = ((_c2 = state2.results["sound.inspect"]) == null ? void 0 : _c2.document_id) === doc.document_id && ctx2.draft("sound-changes", "{}") === submitted;
        if (unchanged) persist([]);
        else state2.pending = null;
        await ctx2.render();
        ctx2.notify(unchanged ? "Separate sound build created. Playtest it to verify the result." : "Separate sound build created. Your newer edits are still staged.");
      },
      "sound-discard": () => {
        persist([]);
        return ctx2.render();
      }
    });
    const hardware = system2.hardware, driver = system2.driver, packet = visiblePreview(ctx2), previewRequest = ownsPreview(ctx2, state2.soundPreviewRequest) ? state2.soundPreviewRequest : null, pending = ((_d = state2.pending) == null ? void 0 : _d.kind) === "sound" && state2.pending.document_id === (doc == null ? void 0 : doc.document_id);
    const setup2 = `<details class="card" ${!doc ? "open" : ""}><summary>Supported sample setup</summary><p>Use a verified sample offset and allocation. A valid codec does not identify a sample's location, rate, loop or instrument.</p><div class="field-row">${field("sound-name", "Sample name", ctx2.draft("sound-name", "Sample"))}${field("sound-offset", "File offset", ctx2.draft("sound-offset", "0"))}${field("sound-length", "Allocated bytes", ctx2.draft("sound-length", "16"))}${select("sound-codec", "Sample format", Object.entries(codecNames), ctx2.draft("sound-codec", hardware.sample_formats[0]))}${field("sound-rate", "Preview sample rate (Hz)", ctx2.draft("sound-rate", "16000"))}${field("sound-initial", "DPCM initial level", ctx2.draft("sound-initial", "64"))}</div>${button("Check declared sample", "sound-declare")}${jsonEditor("sound-definition", "Source-bound sound definition", ctx2.draft("sound-definition", JSON.stringify((doc == null ? void 0 : doc.definition) || saved || {}, null, 2)))}<div class="actions">${button("Inspect definition", "sound-inspect")}${button("Save checked definition", "sound-save")}</div></details>`;
    return `${heading("", "Music & sound", "")}<div class="identity"><strong>${esc(state2.artifact.name)}</strong><span>${changes.length} staged changes</span></div>${draftError ? `<p class="notice warm">${esc(draftError)} ${button("Discard saved audio edits", "sound-discard")}</p>` : ""}<div class="grid-two"><section class="card"><h3>${esc(hardware.name)}</h3><p>${hardware.channels.map(esc).join(" · ")}</p><p><strong>Music driver: ${esc(driver.name)}</strong></p><p>${esc(driver.status === "UNKNOWN" ? "Unknown driver: sequence editing unavailable." : driver.evidence)}</p><details><summary>Hardware and driver references</summary><p>${esc(hardware.notes)}</p>${[...hardware.references, ...driver.reference ? [driver.reference] : []].map((url) => `<p><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(new URL(url).hostname)} reference</a></p>`).join("")}</details></section><section class="card"><h3>Native game audio</h3><p>Load this source in Playtest, reach the music or sound you want, then record its mixed output here.</p>${field("sound-frames", "Frames to record (1–300)", ctx2.draft("sound-frames", "120"), { type: "number", min: 1 })}${button("Record native preview", "sound-capture", { primary: !doc, disabled: !state2.runtime || state2.runtime.game_sha256 !== state2.artifact.sha256 })}${button("Open Playtest", "navigate", { id: "playtest" })}</section></div>${(previewRequest == null ? void 0 : previewRequest.status) === "loading" ? '<section class="card"><p class="preview-caption" role="status">Decoding original and edited audio…</p></section>' : (previewRequest == null ? void 0 : previewRequest.status) === "error" ? `<section class="card"><p class="error" role="status">Preview unavailable: ${esc(previewRequest.message)}</p></section>` : ""}${packet ? `<section class="card"><h3>Audio preview</h3>${packet.comparison ? `<div class="preview-pair"><div><span>Original</span><canvas id="original-waveform" width="720" height="140" style="display:block;width:100%;height:auto" aria-label="Original decoded audio waveform"></canvas></div><div><span>Edited</span><canvas id="edited-waveform" width="720" height="140" style="display:block;width:100%;height:auto" aria-label="Edited decoded audio waveform"></canvas></div></div><p class="preview-caption" role="status">${packet.comparison.changed ? "Preview updated · decoded audio changed · not built" : "Unchanged decoded audio preview"} · ${packet.kind === "sample" ? "Sample" : "Song reference"} · ${esc(packet.resource_id)}</p>` : ""}<audio id="sound-player" controls preload="metadata" aria-label="Sound preview play, pause and seek"></audio><div class="actions">${button("Toggle loop", "sound-loop")}${button("Save preview WAV", "sound-export-preview")}</div><p>${esc(packet.preview_scope)}${packet.truncated ? " Preview shortened to20seconds." : ""}</p><p>${packet.sample_frames} frames · ${packet.sample_rate}Hz${packet.channels ? " · " + packet.channels + " channels" : ""}</p></section>` : ""}${doc ? `<div class="grid-two"><section class="card"><h3>Samples</h3>${sample ? `${select("sound-sample", "Sample", doc.samples.map((s) => [s.id, s.name]), sample.id)}<span>Original sample</span><canvas id="sample-waveform" width="720" height="140" aria-label="Original decoded sample waveform"></canvas><p>${sample.sample_count} samples · ${sample.duration_seconds.toFixed(3)}s · ${esc(sample.codec)}</p><div class="field-row">${select("sound-operation", "Edit", [["gain", "Set gain"], ["reverse", "Reverse"], ["silence", "Silence target"], ["replace_wav", "Replace from WAV"]], ctx2.draft("sound-operation", "gain"))}${field("sound-gain", "Gain (%)", ctx2.draft("sound-gain", "100"))}</div><label class="field"><span>Replacement PCM WAV, up to2MiB</span><input type="file" id="sound-wav" accept=".wav,audio/wav"></label><div class="actions">${button("Stage sample edit", "sound-sample-stage")}${button("Preview sample & edits", "sound-sample-preview", { primary: true })}</div><p>${sample.encoding_lossy ? "Re-encoding is lossy; preview and native-test the resulting build." : "Edits preserve the declared byte allocation."}</p>` : "<p>No sample storage declared.</p>"}</section><section class="card"><h3>Music sequences</h3>${song ? `${select("sound-song", "Identified song", doc.songs.map((s) => [s.id, s.name]), song.id)}<p>${esc(song.driver_scope)}</p><div class="field-row">${field("sound-event", "Event index", ctx2.draft("sound-event", "0"))}${select("sound-note-field", "Field", [["note", "Note number"], ["duration", "Duration ticks"], ["volume", "Volume"]], ctx2.draft("sound-note-field", "note"))}${field("sound-note-value", "New value", ctx2.draft("sound-note-value", "64"))}</div>${button("Stage note edit", "sound-note-stage")}<div class="field-row">${field("sound-transpose", "Transpose semitones", ctx2.draft("sound-transpose", "0"))}</div>${button("Transpose song", "sound-transpose")}${button("Preview song & edits", "sound-song-preview", { primary: true })}<div class="table-wrap"><table><thead><tr><th>Event</th><th>Note</th><th>Ticks</th><th>Volume</th></tr></thead><tbody>${song.events.map((event, index) => `<tr><td>${index}</td>${["note", "duration", "volume"].map((field2) => {
      var _a2;
      return `<td>${esc(((_a2 = changes.find((c) => c.kind === "note" && c.song_id === song.id && c.index === index && c.field === field2)) == null ? void 0 : _a2.value) ?? event[field2])}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>` : "<p>No supported sequence driver is identified. Native music recording and supported sample formats remain available.</p>"}</section></div><section class="card"><div class="actions">${button("Review sound changes", "sound-plan", { primary: !pending, disabled: !changes.length })}${pending ? button("Create sound build", "sound-build", { primary: true }) : ""}${button("Discard sound edits", "sound-discard", { disabled: !changes.length })}</div></section>` : ""}${setup2}${report(state2.results["sound.plan"], "Sound review")}`;
  }
  function mount11(ctx2) {
    var _a, _b;
    const packet = visiblePreview(ctx2);
    (_a = ctx2.state.soundPlayer) == null ? void 0 : _a.close();
    ctx2.state.soundPlayer = null;
    if (packet) {
      const audio = document.getElementById("sound-player");
      if (audio) {
        ctx2.state.soundPlayer = new WavPreview();
        ctx2.state.soundPlayer.attach(audio, packet.wav_base64);
      }
      if (packet.comparison) {
        drawWaveform(document.getElementById("original-waveform"), packet.comparison.original.peaks);
        drawWaveform(document.getElementById("edited-waveform"), packet.comparison.edited.peaks);
      }
    }
    const doc = ctx2.state.results["sound.inspect"], sample = doc == null ? void 0 : doc.samples.find((s) => {
      var _a2;
      return s.id === ((_a2 = document.getElementById("sound-sample")) == null ? void 0 : _a2.value);
    });
    if (sample) drawWaveform(document.getElementById("sample-waveform"), sample.peaks || []);
    for (const [id, kind] of [["sound-sample", "sample"], ["sound-song", "song"]]) (_b = document.getElementById(id)) == null ? void 0 : _b.addEventListener("change", (event) => {
      ctx2.setDraft(id, event.target.value);
      previewSound(ctx2, doc, kind, event.target.value).catch((error) => ctx2.notify(error.message, true));
    });
  }

  // romancer/ui/app.js
  var startupReady = false;
  applyInterfaceScale(readPreference("romancer-scale") || 100);
  window.addEventListener("resize", () => applyInterfaceScale(getSettings().scale));
  var views = { tutorials: tutorials_exports, overview: overview_exports, resources: resources_exports, scripts: scripts_exports, assets: assets_exports, levels: levels_exports, sound: sound_exports, tables: tables_exports, automation: automation_exports, playtest: playtest_exports, debug: debug_exports, routes: routes_exports, regression: regression_exports, release: release_exports, help: help_exports, settings: settings_exports };
  var names3 = { tutorials: "Tutorials", automation: "Recipes & definitions", overview: "Overview", resources: "Resources", scripts: "Text & layout", assets: "Graphics & fonts", levels: "Levels", sound: "Music & sound", tables: "Data tables", playtest: "Playtest", debug: "Investigation", routes: "Routes", regression: "Regression", release: "Export", settings: "Settings", help: "Help" };
  var state = { page: "overview", projects: [], project: null, artifact: null, capabilities: null, drafts: {}, results: {}, pending: null, job: null, runtime: null, frame: null, snapshot: null };
  var actions = {};
  var renderRevision = 0;
  var toastTimer;
  var lastRenderedScope = null;
  var workspaceWriteWarning = false;
  var workspaceWrites = new WorkspaceLocationWriter(api, (error) => {
    if (!workspaceWriteWarning) {
      workspaceWriteWarning = true;
      notify("Workspace restore could not be saved. Your editing drafts are separate.", true);
    }
  });
  var draftRevisions = /* @__PURE__ */ new Map();
  var draftWrites = new DraftQueue(() => updateWorkspaceStatus());
  var loadedDrafts = /* @__PURE__ */ new Set();
  var lastDraft = null;
  async function flushDrafts() {
    await draftWrites.flush();
  }
  function updateWorkspaceStatus() {
    const host = document.getElementById("workspace-state-host");
    if (host) host.innerHTML = workspaceStatus(state, draftWrites.snapshot(), false);
    updateHistoryButtons();
  }
  function localHistoryAction(direction) {
    return historyAction(state.page, state.historyEditor || "", direction, (action) => {
      var _a;
      return !!((_a = document.getElementById("main")) == null ? void 0 : _a.querySelector(`[data-action="${action}"]`));
    });
  }
  function historyAvailable(direction) {
    var _a, _b;
    const action = localHistoryAction(direction);
    if (action !== "draft-" + (direction < 0 ? "undo" : "redo")) return !((_b = (_a = document.getElementById("main")) == null ? void 0 : _a.querySelector(`[data-action="${action}"]`)) == null ? void 0 : _b.disabled);
    const record = lastDraft && draftRevisions.get(lastDraft.full);
    return !!(record == null ? void 0 : record[direction < 0 ? "can_undo" : "can_redo"]);
  }
  function updateHistoryButtons() {
    for (const [direction, action] of [[-1, "draft-undo"], [1, "draft-redo"]]) {
      const node = document.querySelector(`.job-tray [data-action="${action}"]`);
      if (node) setUnavailable(node, !historyAvailable(direction), direction < 0 ? "No earlier edit in the active editor." : "No edit to redo in the active editor.");
    }
  }
  async function moveActiveHistory(direction) {
    var _a;
    await flushDrafts();
    const action = localHistoryAction(direction);
    if (!historyAvailable(direction)) throw Error(direction < 0 ? "No earlier edit to undo." : "No edit to redo.");
    if (action === "draft-" + (direction < 0 ? "undo" : "redo")) return moveDraft(direction);
    return (_a = actions[action]) == null ? void 0 : _a.call(actions, document.getElementById("main").querySelector(`[data-action="${action}"]`));
  }
  async function saveNow() {
    await flushDrafts();
    notify(hasStagedChanges(state) ? "Drafts saved. Create a build to playtest these edits." : "Drafts saved.");
  }
  function showShortcuts() {
    modal("Keyboard shortcuts", `<div class="table-wrap"><table><tbody>${SHORTCUTS.map(([keys2, label]) => `<tr><th><kbd>${esc(keys2)}</kbd></th><td>${esc(label)}</td></tr>`).join("")}</tbody></table></div><p>Text fields keep their own undo and redo. Shortcuts pause while a dialog or game controller has focus.</p><p>Saved drafts keep your editing work. Create a separate build before playtesting.</p>`);
  }
  function rememberLocation() {
    var _a, _b;
    if (!getSettings().rememberWorkspace) return;
    const main = document.getElementById("main");
    if (!main || main.dataset.locationScope !== [(_a = state.project) == null ? void 0 : _a.project_id, (_b = state.artifact) == null ? void 0 : _b.artifact_id, state.page].join(":")) return;
    const saved = locationSnapshot(state, main.scrollTop);
    if (saved) {
      writePreference(locationKey(state), JSON.stringify(saved));
      workspaceWrites.enqueue(saved);
    }
  }
  function resumeLocation() {
    if (!getSettings().rememberWorkspace) return false;
    try {
      return restoreLocation(state, JSON.parse(readPreference(locationKey(state)) || "null"));
    } catch {
      return false;
    }
  }
  var locationTimer;
  document.addEventListener("scroll", (event) => {
    if (event.target.id !== "main") return;
    clearTimeout(locationTimer);
    locationTimer = setTimeout(rememberLocation, 150);
  }, true);
  window.addEventListener("beforeunload", (event) => guardClose(event, draftWrites, state));
  function clearDraftCache() {
    draftWrites.clear();
    draftRevisions.clear();
    loadedDrafts.clear();
    state.drafts = {};
    state.historyEditor = null;
    lastDraft = null;
  }
  function saveDraft(id, value) {
    if (!state.project || !state.artifact) return;
    const project_id = state.project.project_id, artifact_id = state.artifact.artifact_id, key3 = draftFieldKey(id), full = [project_id, artifact_id, key3].join(":");
    state.drafts[full] = value;
    lastDraft = { project_id, artifact_id, key: key3, full };
    draftWrites.enqueue(full, async () => {
      let record = draftRevisions.get(full);
      if (!record) record = await api.call("drafts.get", { project_id, artifact_id, key: key3 });
      try {
        record = await api.call("drafts.save", { project_id, artifact_id, key: key3, revision: record.revision, value });
      } catch (error) {
        try {
          const saved = await api.call("drafts.get", { project_id, artifact_id, key: key3 });
          if (JSON.stringify(saved.value) !== JSON.stringify(value)) throw error;
          record = saved;
        } catch {
          throw error;
        }
      }
      draftRevisions.set(full, record);
    }, (error) => notify("Draft not saved: " + error.message, true));
  }
  async function moveDraft(direction) {
    await flushDrafts();
    if (!lastDraft) throw new Error("Edit a field first.");
    const { project_id, artifact_id, key: key3, full } = lastDraft, record = draftRevisions.get(full);
    const result = await api.call("drafts.move", { project_id, artifact_id, key: key3, revision: record.revision, direction });
    draftRevisions.set(full, result);
    state.drafts[full] = result.value;
    state.pending = null;
    if (key3.endsWith(":paint-buffer")) {
      state.paint = null;
      state.pixelHistories = null;
      state.pixelHistoryScope = null;
    }
    if (key3.endsWith(":level-changes")) state.levelEditor = null;
    if (key3.endsWith(":hex-changes")) {
      state.hexDraft = null;
      state.hexReview = null;
    }
    await render17();
  }
  var ctx = {
    state,
    api,
    navigate,
    notify,
    render: render17,
    refreshProject,
    openProject,
    modal,
    closeModal: () => document.getElementById("modal").close(),
    draft: (id, fallback) => state.drafts[draftKey(id)] ?? fallback,
    setDraft: saveDraft,
    use: (handlers) => Object.assign(actions, handlers),
    run,
    projectParams: () => ({ project_id: state.project.project_id }),
    sourceParams: () => ({ project_id: state.project.project_id, artifact_id: state.artifact.artifact_id }),
    setArtifact: async (id) => {
      var _a, _b;
      rememberLocation();
      if (((_a = state.artifact) == null ? void 0 : _a.artifact_id) !== id) selectionTicket(state);
      stopPlayback(state);
      state.animationPlaying = false;
      await flushDrafts();
      if (state.runtime) {
        await api.call("runtime.close", { project_id: state.project.project_id });
        state.runtime = null;
        state.frame = null;
        state.snapshot = null;
      }
      await flushDrafts();
      clearDraftCache();
      state.artifact = chooseArtifact(state.project, id);
      writePreference("romancer-artifact:" + state.project.project_id, ((_b = state.artifact) == null ? void 0 : _b.artifact_id) || "");
      state.profileFamily = null;
      state.profileLoadedFamily = null;
      state.scriptPage = 0;
      state.assetPage = 0;
      state.catalogPage = 0;
      state.catalogQuery = "";
      state.pending = null;
      resumeLocation();
      await render17();
    }
  };
  var tutorial = createTutorial({ ...ctx, openProject, closeProject });
  function draftFieldKey(id) {
    var _a, _b;
    const doc = id.startsWith("script-segment-") ? (_a = state.results["script.inspect"]) == null ? void 0 : _a.document_id : ["paint-buffer", "asset-changes"].includes(id) ? (_b = state.results["assets.inspect"]) == null ? void 0 : _b.document_id : null;
    return [state.page, ...doc ? [doc] : [], id].join(":");
  }
  function draftKey(id) {
    var _a, _b;
    return [(_a = state.project) == null ? void 0 : _a.project_id, (_b = state.artifact) == null ? void 0 : _b.artifact_id, draftFieldKey(id)].join(":");
  }
  function errorNotice() {
    if (!state.lastError) return "";
    const advice = helpForError(state.lastError);
    return `<div class="notice warm actionable-error" role="alert"><p>${esc(state.lastError)}</p><div class="actions">${button(advice.label, "help-topic", { id: advice.topic })}${button("Dismiss", "error-dismiss")}</div></div>`;
  }
  function notify(message, error = false) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    if (error) {
      state.lastError = String(message);
      const panel2 = document.getElementById("error-panel");
      if (panel2) panel2.innerHTML = errorNotice();
      const advice = helpForError(message), link = document.createElement("button");
      link.type = "button";
      link.dataset.action = "help-topic";
      link.dataset.id = advice.topic;
      link.textContent = advice.label;
      toast.append(document.createElement("br"), link);
    }
    toast.className = error ? "error" : "";
    toast.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.style.display = "none", error ? 1e4 : 4500);
  }
  function modal(title, body) {
    const node = document.getElementById("modal");
    node.innerHTML = `<div class="dialog-heading"><h2 id="modal-title">${esc(title)}</h2>${button("Close", "close-modal", { icon: "close" })}</div>${body}`;
    if (!node.open) node.showModal();
  }
  async function refreshProject() {
    var _a, _b, _c, _d;
    const id = (_a = state.project) == null ? void 0 : _a.project_id;
    state.projects = (await api.call("projects.list")).projects;
    if (!id || ((_b = state.project) == null ? void 0 : _b.project_id) !== id) return;
    const opened = await api.call("project.open", { project_id: id });
    if (((_c = state.project) == null ? void 0 : _c.project_id) !== id) return;
    state.project = opened;
    state.artifact = chooseArtifact(opened, (_d = state.artifact) == null ? void 0 : _d.artifact_id);
  }
  function jobTray() {
    var _a;
    const job = state.job, active = job && !["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(job.status);
    return `<div class="job-tray ${active ? "working" : ""}"><div><span class="pulse"></span><strong>${active ? "Working" : (job == null ? void 0 : job.status) === "FAILED" ? "Action failed" : (job == null ? void 0 : job.status) === "CANCELLED" ? "Cancelled" : "Ready"}</strong><span> ${active ? " — " + esc(job.message) : ""}</span></div><div id="workspace-state-host">${workspaceStatus(state, draftWrites.snapshot(), false)}</div>${active ? button("Cancel job", "cancel-job") : `<div class="actions">${((_a = state.tutorial) == null ? void 0 : _a.minimized) ? button("Resume lesson", "tutorial-toggle") : ""}${button("Undo", "draft-undo", { disabled: !historyAvailable(-1), reason: "No earlier edit in the active editor." })}${button("Redo", "draft-redo", { disabled: !historyAvailable(1), reason: "No edit to redo in the active editor." })}</div>`}</div>`;
  }
  function updateJob(job) {
    state.job = job;
    const tray = document.querySelector(".job-tray");
    if (tray) tray.outerHTML = jobTray();
  }
  async function run(operation, parameters, options = {}) {
    return runScoped(ctx, operation, parameters, options, updateJob);
  }
  async function openProject(id) {
    rememberLocation();
    stopPlayback(state);
    const ticket = selectionTicket(state);
    await flushDrafts();
    if (!selectionCurrent(state, ticket)) return;
    if (state.runtime && state.project) {
      await api.call("runtime.close", { project_id: state.project.project_id });
      state.runtime = null;
      state.frame = null;
      state.snapshot = null;
    }
    state.profileFamily = null;
    state.profileLoadedFamily = null;
    state.scriptPage = 0;
    state.catalogPage = 0;
    state.catalogQuery = "";
    const opened = await api.call("project.open", { project_id: id });
    if (!selectionCurrent(state, ticket)) return;
    await flushDrafts();
    if (!selectionCurrent(state, ticket)) return;
    clearDraftCache();
    releaseProjectResources(state);
    state.project = opened;
    state.artifact = chooseArtifact(state.project, readPreference("romancer-artifact:" + state.project.project_id));
    state.results = {};
    state.pending = null;
    writePreference("romancer-project", id);
    state.page = "overview";
    await refreshProject();
    resumeLocation();
    await render17();
  }
  async function closeProject() {
    rememberLocation();
    stopPlayback(state);
    state.animationPlaying = false;
    await flushDrafts();
    if (state.runtime && state.project) await api.call("runtime.close", { project_id: state.project.project_id });
    await flushDrafts();
    clearDraftCache();
    clearProjectState(state);
    lastDraft = null;
    removePreference("romancer-project");
    workspaceWrites.enqueue(null);
    await render17();
  }
  async function navigate(page) {
    var _a;
    rememberLocation();
    stopPlayback(state);
    state.animationPlaying = false;
    await flushDrafts();
    if (!views[page]) return;
    if (page === "settings" && state.page !== "settings") state.settingsReturnPage = state.page;
    state.page = page;
    await render17();
    (_a = document.getElementById("main")) == null ? void 0 : _a.focus({ preventScroll: true });
  }
  async function importDialog() {
    const dropped = state.droppedImportFile;
    modal(state.project ? "Import ROM" : "New ROM project", `${!state.project ? field("new-project-name", "Project name", dropped ? dropped.name.replace(/\.[^.]+$/, "") : "My ROM project") : ""}<p>Your original file stays unchanged.</p>${dropped ? `<p class="notice">Selected: <strong>${esc(dropped.name)}</strong></p>` : ""}<label class="field"><span>Choose a ROM file</span><input type="file" id="import-file" accept=".nes,.sfc,.smc,.md,.gen,.bin,.gb,.gbc,.gba,.rom"></label><details class="config"><summary>Advanced path import</summary>${field("import-path", "Absolute file path", "", { placeholder: "C:\\Games\\My game.sfc" })}${button("Browse this computer", "choose-input", { icon: "folder" })}<p>Use a path for files larger than64MiB.</p></details><div class="actions">${button("Import ROM", "import-confirm", { primary: true, icon: "plus" })}${button("Import help", "help-topic", { id: "import" }) + button("Start a new project", "new-project")}</div>`);
  }
  function showSearch() {
    const query = document.getElementById("global-search").value.toLowerCase().trim();
    const matches = Object.entries(names3).filter(([key3, value]) => value.toLowerCase().includes(query));
    modal("Workspace search", `<div class="search-results">${matches.map(([key3, value]) => button(value, "search-open", { id: key3, class: "search-result", icon: key3 })).join("") || '<p class="subtle">No matching views.</p>'}${state.project ? [...state.project.sources, ...state.project.builds].filter((a) => a.name.toLowerCase().includes(query)).map((a) => `<p class="subtle">${esc(a.name)} · ${esc(a.system)}<br>${esc(a.sha256)}</p>`).join("") : ""}</div>`);
  }
  function baseActions() {
    return {
      "error-dismiss": () => {
        state.lastError = null;
        document.getElementById("error-panel").innerHTML = "";
        document.getElementById("toast").style.display = "none";
      },
      "draft-retry": async () => {
        await draftWrites.retry();
        updateWorkspaceStatus();
        notify("Draft saved.");
      },
      "draft-undo": () => moveActiveHistory(-1),
      "draft-redo": () => moveActiveHistory(1),
      "draft-save-now": saveNow,
      "shortcut-help": showShortcuts,
      "navigate": (node) => {
        document.getElementById("modal").close();
        return navigate(node.dataset.id);
      },
      "close-modal": () => document.getElementById("tutorial-never") ? tutorial.dismissPrompt(false) : document.getElementById("modal").close(),
      "import": () => {
        state.droppedImportFile = null;
        return importDialog();
      },
      "candidate-cancel": () => {
        state.candidateReview = null;
        state.resourcePrefill = null;
        state.openDeclaration = null;
        return render17();
      },
      "help-topic": (node) => {
        state.helpTopic = node.dataset.id || ({ assets: "graphics", scripts: "text", resources: "discovery", release: "export", settings: "recovery", overview: "start", help: "start" }[state.page] || state.page);
        document.getElementById("modal").close();
        return navigate("help");
      },
      "workspace-search": showSearch,
      "demo-system": async (node) => {
        const result = await run("project.demo_system", { system_id: node.dataset.id }, { render: false });
        await openProject(result.project_id);
        notify("Workshop opened.");
      },
      "demo-nes": async () => {
        const result = await run("project.demo_nes", {}, { render: false });
        await openProject(result.project_id);
        notify("NES workshop opened.");
      },
      "demo": async () => {
        const result = await run("project.demo", {}, { render: false });
        await openProject(result.project_id);
        notify("Harbor workshop opened.");
      },
      "open-project": (node) => openProject(node.dataset.id),
      "choose-input": async () => {
        const result = await run("system.pick_file", {}, { refresh: false, render: false });
        if (result.path) document.getElementById("import-path").value = result.path;
      },
      "import-confirm": async () => {
        const file = document.getElementById("import-file").files[0] || state.droppedImportFile, path = read("import-path").trim();
        if (!file && !path) throw new Error("Select a source file or enter its absolute path.");
        if (!state.project) {
          state.project = await api.call("project.create", { name: read("new-project-name") });
          writePreference("romancer-project", state.project.project_id);
        }
        if (file) await api.upload(state.project.project_id, file);
        else await run("source.import", { project_id: state.project.project_id, path, system: null }, { render: false });
        document.getElementById("modal").close();
        state.droppedImportFile = null;
        await refreshProject();
        state.artifact = state.project.sources.at(-1);
        state.page = "resources";
        await render17();
        notify("Source copied into the project. Original preserved.");
      },
      "cancel-job": async () => {
        if (state.job) updateJob(await api.call("jobs.cancel", { job_id: state.job.job_id }));
      },
      "about": () => {
        var _a, _b, _c, _d;
        return modal("About ROMancer", `<div class="brand"><img src="/mark.svg" alt=""><div><strong>ROMancer</strong><small>By RetchEWretched</small></div></div><p>A local workbench for investigating, editing, and testing retro game resources.</p><div class="notice">Version ${esc(((_a = state.capabilities) == null ? void 0 : _a.display_version) || ((_b = state.capabilities) == null ? void 0 : _b.version))} · NES · SNES · GEN · Game Boy · Game Boy Color · GBA</div><p class="subtle">Python ${esc((_c = state.capabilities) == null ? void 0 : _c.python)} · ${esc((_d = state.capabilities) == null ? void 0 : _d.platform)}<br>Local projects · Content-bound builds · Independent BPS verification</p>${button("Capabilities & settings", "navigate", { id: "settings" })}`);
      },
      "download": async (node) => api.download(state.project.project_id, node.dataset.id, node.dataset.name || "romancer-export"),
      "search-open": (node) => {
        document.getElementById("modal").close();
        navigate(node.dataset.id);
      },
      ...projectActions({ ...ctx, closeProject, flushDrafts, importDialog })
    };
  }
  async function render17() {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l;
    if (((_a = document.getElementById("app")) == null ? void 0 : _a.dataset.startupRecovered) === "true") return;
    rememberLocation();
    disposeAudio();
    (_b = state.soundPlayer) == null ? void 0 : _b.close();
    state.soundPlayer = null;
    (_c = state.animationClock) == null ? void 0 : _c.stop();
    state.animationClock = null;
    const revision = ++renderRevision, previousScroll = ((_d = document.getElementById("main")) == null ? void 0 : _d.scrollTop) || 0, renderScope = [(_e = state.project) == null ? void 0 : _e.project_id, (_f = state.artifact) == null ? void 0 : _f.artifact_id, state.page].join(":"), details = rememberDetails(document.getElementById("main"));
    actions = baseActions();
    tutorial.bind();
    const project = state.project, artifacts = project ? [...project.sources, ...project.builds] : [];
    document.getElementById("app").innerHTML = `<div class="shell"><aside class="sidebar"><a class="brand" href="#" data-action="navigate" data-id="overview"><img src="/mark.svg" alt=""><div><strong>ROMancer</strong><small>By RetchEWretched</small></div></a><div class="nav-label">Workspace</div><nav aria-label="Workbench">${["overview", "resources", "debug", "scripts", "assets", "levels", "sound", "playtest", "release"].map((k) => `<button class="nav-item ${state.page === k ? "active" : ""}" data-action="navigate" data-id="${k}" title="${names3[k]}" ${state.page === k ? 'aria-current="page"' : ""}>${icon(k)}<span>${names3[k]}</span></button>`).join("")}<details class="more-tools" ${getSettings().advancedTools || ["tables", "automation", "routes", "regression"].includes(state.page) ? "open" : ""}><summary title="More tools">More tools</summary>${["tables", "automation", "routes", "regression"].map((k) => `<button class="nav-item ${state.page === k ? "active" : ""}" data-action="navigate" data-id="${k}" title="${names3[k]}">${icon(k)}<span>${names3[k]}</span></button>`).join("")}</details></nav><div class="sidebar-bottom"><button class="nav-item" data-action="navigate" data-id="help" title="Help">${icon("shield")}<span>Help</span></button><button class="nav-item" data-action="projects-manage" title="Projects">${icon("folder")}<span>Projects</span></button><button class="nav-item ${state.page === "settings" ? "active" : ""}" data-action="navigate" data-id="settings" title="Settings">${icon("settings")}<span>Settings</span></button><button class="nav-item" data-action="about" title="About ROMancer">${icon("shield")}<span>About</span></button><div class="local-label"><span class="dot"></span>Runs on your computer</div></div></aside><header class="topbar"><div class="project-control">${icon("folder")}<div><small>ACTIVE PROJECT</small><br><select id="project-select" aria-label="Active project"><option value="">Choose a project</option>${state.projects.map((p) => `<option value="${p.project_id}" ${(project == null ? void 0 : project.project_id) === p.project_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>${button("New project", "new-project", { icon: "plus", class: "compact" })}</div>${artifacts.length ? `<div class="project-control source-selector"><div><small>${((_g = state.artifact) == null ? void 0 : _g.kind) === "source" ? "ORIGINAL ROM" : "BUILD"}</small><br><select id="artifact-select" aria-label="Selected source or build">${[["Original ROMs", project.sources], ["Builds", project.builds]].filter(([, rows]) => rows.length).map(([label, rows]) => `<optgroup label="${label}">${rows.map((a) => {
      var _a2;
      return `<option value="${a.artifact_id}" ${((_a2 = state.artifact) == null ? void 0 : _a2.artifact_id) === a.artifact_id ? "selected" : ""}>${esc(a.name)}</option>`;
    }).join("")}</optgroup>`).join("")}</select></div></div>` : ""}<label class="search">${icon("search")}<input id="global-search" placeholder="Search workspace" aria-label="Search workspace"><kbd>Ctrl K</kbd><button type="button" data-action="workspace-search" aria-label="Run workspace search" class="search-go">Go</button></label></header><main id="main" tabindex="-1"><div class="loading">Opening ${names3[state.page]}…</div></main>${jobTray()}${tutorial.panel()}</div>`;
    const view = views[state.page];
    let html;
    if (project && state.artifact) {
      const scope = project.project_id + ":" + state.artifact.artifact_id;
      if (!loadedDrafts.has(scope)) {
        try {
          const saved = await api.call("drafts.list", ctx.sourceParams());
          for (const d of saved.drafts) {
            const full = scope + ":" + d.key;
            if (!(full in state.drafts)) state.drafts[full] = d.value;
            draftRevisions.set(full, d);
          }
          loadedDrafts.add(scope);
        } catch (error) {
          notify(error.message, true);
        }
      }
    }
    try {
      if (revision !== renderRevision) return;
      html = await view.render({ ...ctx, isCurrentRender: () => revision === renderRevision, use: (handlers) => {
        if (revision === renderRevision) ctx.use(handlers);
      } });
    } catch (error) {
      html = `${heading("Workspace", names3[state.page], "")}<div class="card"><p class="error">${esc(error.message)}</p>${button("Return to overview", "navigate", { id: "overview" })}</div>`;
    }
    if (revision !== renderRevision) return;
    if (((_h = document.getElementById("app")) == null ? void 0 : _h.dataset.startupRecovered) === "true") return;
    document.getElementById("main").innerHTML = `<div id="error-panel">${errorNotice()}</div>` + html;
    if (lastRenderedScope === renderScope) restoreDetails(document.getElementById("main"), details);
    await ((_i = view.mount) == null ? void 0 : _i.call(view, ctx));
    tutorial.mount();
    updateWorkspaceStatus();
    document.getElementById("main").scrollTop = retainedScroll(lastRenderedScope, renderScope, previousScroll);
    lastRenderedScope = renderScope;
    const main = document.getElementById("main");
    main.dataset.locationScope = renderScope;
    const identity = [(_j = state.project) == null ? void 0 : _j.project_id, (_k = state.artifact) == null ? void 0 : _k.artifact_id, (_l = state.artifact) == null ? void 0 : _l.sha256].join(":");
    if (state.resumeIdentity === identity && state.resumeScroll !== void 0) {
      main.scrollTop = state.resumeScroll;
      delete state.resumeScroll;
      delete state.resumeIdentity;
    }
    rememberLocation();
    void ensureRomScan(ctx);
    void ensureGraphicsObservation(ctx);
  }
  document.addEventListener("click", async (event) => {
    const node = event.target.closest("[data-action]");
    if (!node || node.disabled) return;
    event.preventDefault();
    const handler = actions[node.dataset.action];
    if (!handler) return;
    node.disabled = true;
    try {
      await handler(node, event);
    } catch (error) {
      notify(error.message, true);
    } finally {
      if (node.isConnected) node.disabled = false;
    }
  });
  document.addEventListener("input", (event) => {
    if (shouldSaveField(event.target)) {
      state.pending = null;
      saveDraft(event.target.id, event.target.value);
    }
  });
  document.addEventListener("change", async (event) => {
    try {
      if (event.target.id === "project-select") {
        if (event.target.value) await openProject(event.target.value);
        else await closeProject();
      }
      if (event.target.id === "import-file") state.droppedImportFile = null;
      if (event.target.id === "artifact-select") await ctx.setArtifact(event.target.value);
    } catch (error) {
      notify(error.message, true);
    }
  });
  for (const kind of ["focusin", "pointerdown"]) document.addEventListener(kind, (event) => rememberEditor(state, event, updateHistoryButtons));
  document.addEventListener("keydown", (event) => {
    var _a, _b, _c;
    const command = shortcutFor(event, { modalOpen: !!((_a = document.getElementById("modal")) == null ? void 0 : _a.open), gameFocused: !!((_c = (_b = event.target).closest) == null ? void 0 : _c.call(_b, "#runtime-controller")) });
    if (command) {
      event.preventDefault();
      const perform = { save: saveNow, undo: () => moveActiveHistory(-1), redo: () => moveActiveHistory(1), search: () => {
        var _a2;
        return (_a2 = document.getElementById("global-search")) == null ? void 0 : _a2.focus();
      }, help: showShortcuts };
      Promise.resolve().then(perform[command]).catch((error) => notify(error.message, true));
    }
    if (event.key === "Enter" && event.target.id === "global-search") {
      showSearch();
    }
  });
  async function initialize() {
    var _a, _b;
    try {
      let settingsWarning = "";
      try {
        await loadSettings(api);
      } catch (error) {
        settingsWarning = "Saved settings could not be read. Defaults are active; workspace files were preserved.";
        hydrateSettings({ revision: 0, values: DEFAULT_SETTINGS });
      }
      if (getSettings().rememberWorkspace) {
        try {
          const remembered = await api.call("settings.workspace.get", {});
          seedWorkspaceLocation(remembered.location);
        } catch {
        }
      }
      state.capabilities = await api.call("system.capabilities");
      state.projects = (await api.call("projects.list")).projects;
      const last = getSettings().rememberWorkspace ? readPreference("romancer-project") : null;
      if (state.projects.some((p) => p.project_id === last)) {
        state.project = await api.call("project.open", { project_id: last });
        state.artifact = chooseArtifact(state.project, readPreference("romancer-artifact:" + state.project.project_id));
        resumeLocation();
      }
      await render17();
      if (((_a = document.getElementById("app")) == null ? void 0 : _a.dataset.startupRecovered) !== "true") {
        startupReady = true;
        if (settingsWarning) notify(settingsWarning, true);
        void tutorial.init();
      }
    } catch (error) {
      if (((_b = document.getElementById("app")) == null ? void 0 : _b.dataset.startupRecovered) !== "true") document.getElementById("app").innerHTML = `<div class="boot"><img src="/mark.svg" alt=""><h1>Open ROMancer from its launcher</h1><p>${esc(error.message)}</p><small>By RetchEWretched</small></div>`;
    }
  }
  var startup = initialize();
  document.addEventListener("dragover", (event) => {
    var _a;
    if ([...((_a = event.dataTransfer) == null ? void 0 : _a.types) || []].includes("Files")) {
      event.preventDefault();
      document.body.classList.add("file-drag");
    }
  });
  document.addEventListener("dragleave", (event) => {
    if (!event.relatedTarget) document.body.classList.remove("file-drag");
  });
  document.addEventListener("drop", (event) => {
    var _a;
    if (![...((_a = event.dataTransfer) == null ? void 0 : _a.types) || []].includes("Files")) return;
    event.preventDefault();
    document.body.classList.remove("file-drag");
    try {
      state.droppedImportFile = droppedSource(event.dataTransfer.files);
      importDialog();
    } catch (error) {
      notify(error.message, true);
    }
  });
  window.addEventListener("pagehide", () => {
    var _a, _b;
    clearTimeout(locationTimer);
    rememberLocation();
    stopPlayback(state);
    disposeAudio();
    (_a = state.soundPlayer) == null ? void 0 : _a.close();
    (_b = state.animationClock) == null ? void 0 : _b.stop();
  });
  document.getElementById("modal").addEventListener("cancel", (event) => {
    if (document.getElementById("tutorial-never")) {
      event.preventDefault();
      tutorial.dismissPrompt(false).catch((error) => notify(error.message, true));
    }
  });

  // romancer/ui/desktop_entry.js
  startup.then(() => window.dispatchEvent(new Event(startupReady ? "romancer-ready" : "romancer-startup-error"))).catch(() => window.dispatchEvent(new Event("romancer-startup-error")));
})();
