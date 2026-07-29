/* Consilium Chat — minimal no-build SPA client for the local free-LLM council.
 * Codes against the documented FastAPI JSON/SSE API. No framework, no build.
 */
"use strict";

/* ---------------- tiny DOM + fetch helpers ---------------- */

const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
  }
  for (const c of children) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

let errorTimer = null;
function showError(msg) {
  const area = $("error-area");
  if (!area) return;
  area.textContent = "";
  area.append(
    el("span", { text: String(msg) }),
    el("button", { type: "button", text: "✕", onclick: () => { area.hidden = true; } })
  );
  area.hidden = false;
  if (errorTimer) clearTimeout(errorTimer);
  errorTimer = setTimeout(() => { area.hidden = true; }, 8000);
}

async function api(path, opts) {
  // Returns parsed JSON. Throws on network error / non-2xx (caller wraps in try/catch).
  const res = await fetch(path, opts);
  let body = null;
  const text = await res.text();
  if (text) {
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (!res.ok) {
    const detail = body && typeof body === "object" ? (body.error || body.detail || JSON.stringify(body)) : body;
    const err = new Error(detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

const jsonHeaders = { "Content-Type": "application/json" };

/* ---------------- app state ---------------- */

const state = {
  threads: [],
  activeId: null,
  sending: false,
};

/* ---------------- thread list (LEFT) ---------------- */

async function loadThreads() {
  try {
    const threads = await api("/api/threads");
    state.threads = Array.isArray(threads) ? threads : [];
    renderThreadList();
  } catch (e) {
    showError("Could not load threads: " + e.message);
  }
}

function renderThreadList() {
  const list = $("thread-list");
  if (!list) return;
  list.textContent = "";
  if (state.threads.length === 0) {
    list.append(el("li", { class: "empty-hint", text: "No threads yet." }));
    return;
  }
  for (const t of state.threads) {
    const active = t.id === state.activeId;
    const item = el("li", { class: "thread-item" + (active ? " active" : "") });

    const titleSpan = el("span", { class: "thread-title", text: t.title || "(untitled)", title: t.title || "" });
    titleSpan.addEventListener("click", () => selectThread(t.id));

    const actions = el("div", { class: "thread-actions" });
    actions.append(
      el("button", { type: "button", title: "Rename", text: "✎", onclick: (ev) => { ev.stopPropagation(); startRename(item, t); } }),
      el("button", { type: "button", title: "Delete", text: "🗑", onclick: (ev) => { ev.stopPropagation(); deleteThread(t); } })
    );

    item.append(titleSpan, actions);
    list.append(item);
  }
}

function startRename(item, thread) {
  // Inline rename input (no prompt()).
  item.textContent = "";
  const input = el("input", { class: "rename-input", type: "text", value: thread.title || "" });
  const commit = async () => {
    const title = input.value.trim();
    if (title && title !== thread.title) {
      try {
        await api(`/api/threads/${thread.id}`, { method: "PATCH", headers: jsonHeaders, body: JSON.stringify({ title }) });
      } catch (e) {
        showError("Rename failed: " + e.message);
      }
    }
    await loadThreads();
  };
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); commit(); }
    else if (ev.key === "Escape") { renderThreadList(); }
  });
  input.addEventListener("blur", commit);
  item.append(input);
  input.focus();
  input.select();
}

async function deleteThread(thread) {
  try {
    await api(`/api/threads/${thread.id}`, { method: "DELETE" });
  } catch (e) {
    showError("Delete failed: " + e.message);
    return;
  }
  if (state.activeId === thread.id) {
    state.activeId = null;
    clearTranscript();
  }
  await loadThreads();
}

/* ---------------- transcript (CENTER) ---------------- */

function clearTranscript() {
  const t = $("transcript");
  if (t) {
    t.textContent = "";
    t.append(el("p", { class: "empty-hint", text: "Select a thread, or start a new chat, then ask the council." }));
  }
}

async function selectThread(id) {
  state.activeId = id;
  renderThreadList();
  const transcript = $("transcript");
  if (!transcript) return;
  transcript.textContent = "";
  transcript.append(el("p", { class: "empty-hint", text: "Loading…" }));
  try {
    const messages = await api(`/api/threads/${id}`);
    transcript.textContent = "";
    if (!Array.isArray(messages) || messages.length === 0) {
      transcript.append(el("p", { class: "empty-hint", text: "No messages yet — say something below." }));
    } else {
      for (const m of messages) transcript.append(renderMessage(m));
    }
    scrollTranscript();
  } catch (e) {
    transcript.textContent = "";
    transcript.append(el("p", { class: "empty-hint", text: "Failed to load messages." }));
    showError("Load messages failed: " + e.message);
  }
}

function scrollTranscript() {
  const t = $("transcript");
  if (t) t.scrollTop = t.scrollHeight;
}

function renderMessage(m) {
  const role = m.role || "assistant";
  const wrap = el("div", { class: `msg msg-${role}` });
  wrap.append(el("div", { class: "msg-role", text: role }));
  const bubble = el("div", { class: "msg-bubble", text: m.content || "" });
  wrap.append(bubble);
  if (role === "assistant" && m.meta && typeof m.meta === "object") {
    const chip = renderChips(m.meta);
    if (chip) wrap.append(chip);
    const pm = renderPerMember(m.meta.per_member);
    if (pm) wrap.append(pm);
  }
  return wrap;
}

function fmtCost(c) {
  if (c == null || isNaN(c)) return null;
  const n = Number(c);
  return "$" + (n < 0.01 ? n.toFixed(4) : n.toFixed(3));
}

function renderChips(meta) {
  const parts = [];
  if (meta.mode) parts.push(el("span", { class: "chip", text: String(meta.mode) }));
  if (meta.confidence) parts.push(el("span", { class: "chip", text: "conf: " + meta.confidence }));
  const cost = fmtCost(meta.cost_usd);
  if (cost) parts.push(el("span", { class: "chip", text: cost }));
  if (meta.model) parts.push(el("span", { class: "chip", text: String(meta.model) }));
  if (parts.length === 0 && !meta.note) return null;
  const line = el("div", { class: "chip-line" }, ...parts);
  if (meta.note) line.append(el("span", { class: "chip-note", text: meta.note }));
  return line;
}

function renderPerMember(perMember) {
  if (!Array.isArray(perMember) || perMember.length === 0) return null;
  const det = el("details", { class: "per-member" });
  det.append(el("summary", { text: `per-member (${perMember.length})` }));
  for (const pm of perMember) {
    const ok = pm.ok !== false;
    det.append(el("div", { class: "pm-item" },
      el("span", { class: "pm-alias", text: (ok ? "✓ " : "✗ ") + (pm.alias || "?") + ": " }),
      el("span", { text: (pm.answer || pm.content || (ok ? "" : "(no answer)")) })
    ));
  }
  return det;
}

/* ---------------- sending ---------------- */

function readComposer() {
  const content = ($("input")?.value || "").trim();
  const tool = $("tool")?.value || "ask";
  const modeVal = $("mode")?.value || "";
  const sensitivity = $("sensitivity")?.value || "sensitive";
  const model = $("model")?.value || "";
  const sizeVal = $("size")?.value || "";
  return { content, tool, modeVal, sensitivity, model, sizeVal };
}

async function ensureThread() {
  if (state.activeId != null) return state.activeId;
  const t = await api("/api/threads", { method: "POST", headers: jsonHeaders, body: JSON.stringify({}) });
  state.activeId = t.id;
  return t.id;
}

async function onSubmit(ev) {
  ev.preventDefault();
  if (state.sending) return;
  const { content, tool, modeVal, sensitivity, model, sizeVal } = readComposer();
  if (!content) return;

  state.sending = true;
  const sendBtn = $("send");
  if (sendBtn) sendBtn.setAttribute("aria-busy", "true");

  try {
    const threadId = await ensureThread();
    // Optimistically show the user's message.
    const transcript = $("transcript");
    const hint = transcript?.querySelector(".empty-hint");
    if (hint) hint.remove();
    transcript?.append(renderMessage({ role: "user", content }));
    scrollTranscript();
    if ($("input")) $("input").value = "";

    if (tool === "council") {
      await sendCouncil(threadId, { content, modeVal, sensitivity, model, sizeVal });
    } else {
      await sendAsk(threadId, { content, sensitivity, model });
    }
    await loadThreads(); // pick up auto-title
    renderThreadList();
  } catch (e) {
    showError("Send failed: " + e.message);
  } finally {
    state.sending = false;
    if (sendBtn) sendBtn.removeAttribute("aria-busy");
  }
}

async function sendAsk(threadId, { content, sensitivity, model }) {
  const body = { content, tool: "ask", sensitivity };
  if (model) body.model = model;
  const reply = await api(`/api/threads/${threadId}/messages`, {
    method: "POST", headers: jsonHeaders, body: JSON.stringify(body),
  });
  if (reply && reply.event === "error") {
    showError("Council error: " + (reply.error || "unknown") + (reply.note ? ` (${reply.note})` : ""));
    return;
  }
  const transcript = $("transcript");
  const node = renderMessage(reply || { role: "assistant", content: "(empty response)" });
  transcript?.append(node);
  scrollTranscript();
  typeReveal(node.querySelector(".msg-bubble"), reply?.content || "");
}

/* Cosmetic word-by-word reveal (purely client-side). */
function typeReveal(bubble, fullText) {
  if (!bubble || !fullText) return;
  const words = fullText.split(/(\s+)/); // keep whitespace tokens
  bubble.textContent = "";
  let i = 0;
  const step = () => {
    if (i >= words.length) return;
    bubble.textContent += words[i++];
    scrollTranscript();
    setTimeout(step, 18);
  };
  step();
}

/* ---------------- council SSE ---------------- */

function sendCouncil(threadId, { content, modeVal, sensitivity, model, sizeVal }) {
  return new Promise((resolve) => {
    const params = new URLSearchParams({ content, sensitivity });
    if (modeVal) params.set("mode", modeVal);
    if (model) params.set("model", model);
    if (sizeVal) params.set("size", sizeVal);

    const transcript = $("transcript");
    const wrap = el("div", { class: "msg msg-assistant" });
    wrap.append(el("div", { class: "msg-role", text: "assistant (council)" }));
    const bubble = el("div", { class: "msg-bubble", text: "convening council…" });
    const roster = el("div", { class: "roster" });
    const synth = el("div", { class: "synth-note", text: "" });
    synth.hidden = true;
    wrap.append(bubble, roster, synth);
    transcript?.append(wrap);
    scrollTranscript();

    const rosterItems = new Map(); // alias -> li element

    let es;
    try {
      es = new EventSource(`/api/threads/${threadId}/stream?` + params.toString());
    } catch (e) {
      bubble.textContent = "";
      showError("Could not open council stream: " + e.message);
      resolve();
      return;
    }

    const done = (fn) => {
      try { es.close(); } catch { /* ignore */ }
      fn && fn();
      resolve();
    };

    es.onmessage = (evt) => {
      let data;
      try { data = JSON.parse(evt.data); } catch { return; }
      const kind = data.event;

      if (kind === "roster") {
        bubble.textContent = "gathering answers…";
        roster.textContent = "";
        rosterItems.clear();
        for (const alias of data.members || []) {
          const item = el("div", { class: "roster-item" },
            el("span", { class: "state", text: "…" }),
            el("span", { class: "alias", text: alias }),
            el("span", { class: "roster-bar" }, el("span"))
          );
          rosterItems.set(alias, item);
          roster.append(item);
        }
        scrollTranscript();
      } else if (kind === "member") {
        const item = rosterItems.get(data.alias);
        if (item) {
          item.classList.remove("ok", "fail");
          item.classList.add(data.ok ? "ok" : "fail");
          const st = item.querySelector(".state");
          if (st) st.textContent = data.ok ? "✓" : "✗";
        }
      } else if (kind === "aggregating") {
        synth.hidden = false;
        synth.textContent = "synthesizing…";
      } else if (kind === "final") {
        synth.hidden = true;
        const answer = data.answer ?? data.content ?? "";
        bubble.textContent = answer || "(no answer)";
        const meta = {
          mode: data.mode,
          confidence: data.confidence,
          note: data.note,
          cost_usd: data.cost_usd,
          per_member: data.per_member,
        };
        const chip = renderChips(meta);
        if (chip) wrap.append(chip);
        const pm = renderPerMember(data.per_member);
        if (pm) wrap.append(pm);
        scrollTranscript();
        // Re-fetch to align with the server-persisted message.
        done(() => selectThread(threadId));
      } else if (kind === "error") {
        synth.hidden = true;
        bubble.textContent = "";
        showError("Council error: " + (data.error || "unknown") + (data.note ? ` (${data.note})` : ""));
        done();
      }
    };

    es.onerror = () => {
      // EventSource fires error on close too; only surface if we never finished.
      if (es.readyState === EventSource.CLOSED) {
        resolve();
        return;
      }
      showError("Council stream interrupted.");
      done();
    };
  });
}

/* ---------------- model picker ---------------- */

async function loadModels() {
  const sel = $("model");
  if (!sel) return;
  let models;
  try {
    models = await api("/api/models");
  } catch {
    return; // leave just the "auto (best-fit)" option
  }
  if (!Array.isArray(models) || models.length === 0) return;
  for (const m of models) {
    const alias = m && m.alias;
    if (!alias) continue;
    const label = m.tier ? `${alias} (${m.tier})` : String(alias);
    sel.append(el("option", { value: alias, text: label }));
  }
}

/* ---------------- view routing ---------------- */
function showView(name) {
  const isSettings = name === "settings";
  const chat = $("chat-view"), settings = $("settings-view");
  if (chat) chat.hidden = isSettings;
  if (settings) settings.hidden = !isSettings;
  $("nav-chat")?.classList.toggle("active", !isSettings);
  $("nav-settings")?.classList.toggle("active", isSettings);
}

/* ---------------- settings render (from registry via /api/status) ---------------- */
function renderSettings(status) {
  const provs = Array.isArray(status.providers) ? status.providers : [];
  const heads = {
    A: ["keys-tier-a", "Tier A — safe for any prompt"],
    B: ["keys-tier-b", "Tier B — public prompts only"],
  };
  for (const [tier, [id, title]] of Object.entries(heads)) {
    const box = $(id);
    if (!box) continue;
    box.innerHTML = `<h6>${title}</h6>`;
    for (const p of provs.filter((x) => x.tier === tier)) {
      const badge = p.ready ? "✓ ready" : "✗ not set";
      const inputs = (p.env_vars || [])
        .map((v) => `<label class="key-row">${v}<input type="password" name="${v}" autocomplete="off" /></label>`)
        .join("");
      const hint = p.signup ? `<small class="signup">${p.signup}</small>` : "";
      // Safe: p.name/p.tier/p.env_vars/p.signup come from the trusted server-side
      // provider registry (consilium/providers.py), not user input — no XSS via innerHTML.
      box.insertAdjacentHTML(
        "beforeend",
        `<div class="provider-block"><div class="provider-head"><span>${p.name}</span><span class="rd">${badge}</span></div>${inputs}${hint}</div>`,
      );
    }
  }
}

function setSettingsProxy(status) {
  const dot = $("set-proxy-dot"), lbl = $("set-proxy-label");
  if (!dot || !lbl) return;
  const up = !!status.proxy_up;
  dot.className = "dot " + (up ? "dot-green" : "dot-red");
  lbl.textContent = "proxy: " + (up ? "up" : "down");
}

/* ---------------- status sidebar (RIGHT) ---------------- */

let statusTimer = null;

async function refreshStatus() {
  let s;
  try {
    s = await api("/api/status");
  } catch (e) {
    setProxyDot("unknown", "proxy: unreachable");
    return;
  }
  renderProxy(s);
  renderProviders(s.providers || []);
  renderUsage(s.usage || []);
  const cost = fmtCost(s.total_cost_usd);
  const tc = $("total-cost");
  if (tc) tc.textContent = "today: " + (cost || "$0.000");
  renderSettings(s);
  setSettingsProxy(s);
  if (!window.__bootedView) {
    window.__bootedView = true;
    showView(s.configured ? "chat" : "settings");
  }
}

function setProxyDot(kind, label) {
  const dot = $("proxy-dot");
  const lbl = $("proxy-label");
  if (dot) dot.className = "dot dot-" + kind;
  if (lbl) lbl.textContent = label;
}

function renderProxy(s) {
  const up = !!s.proxy_up;
  const host = s.proxy_host && s.proxy_port ? ` ${s.proxy_host}:${s.proxy_port}` : "";
  setProxyDot(up ? "green" : "red", `proxy: ${up ? "up" : "down"}${host}`);
}

function renderProviders(providers) {
  const ul = $("providers");
  if (!ul) return;
  ul.textContent = "";
  if (providers.length === 0) {
    ul.append(el("li", { class: "empty-hint", text: "no providers" }));
    return;
  }
  for (const p of providers) {
    const ready = !!p.ready;
    ul.append(el("li", null,
      el("span", { class: "dot dot-" + (ready ? "green" : "red") }),
      el("span", { text: p.name || "?" }),
      el("span", { class: "tier", text: p.tier ? `(${p.tier})` : "" })
    ));
  }
}

function renderUsage(usage) {
  const ul = $("usage");
  if (!ul) return;
  ul.textContent = "";
  if (usage.length === 0) {
    ul.append(el("li", { class: "empty-hint", text: "no usage yet" }));
    return;
  }
  for (const u of usage) {
    const li = el("li");
    const alias = el("span", { class: "u-alias" + (u.exhausted ? " u-exhausted" : ""), text: (u.alias || "?") + (u.tier ? ` (${u.tier})` : "") + (u.exhausted ? " · exhausted" : "") });
    const reqLimit = u.rpd != null ? `/${u.rpd}` : "";
    const tokLimit = u.tpd != null ? `/${u.tpd}` : "";
    const stats = el("span", { class: "u-stats", text: `req ${u.requests ?? 0}${reqLimit} · tok ${u.tokens ?? 0}${tokLimit}${u.cost_usd != null ? " · " + (fmtCost(u.cost_usd) || "$0") : ""}` });
    li.append(alias, stats);
    ul.append(li);
  }
}

async function proxyControl(action) {
  try {
    const s = await api(`/api/proxy/${action}`, { method: "POST" });
    if (s && typeof s === "object") renderProxy(s);
  } catch (e) {
    showError(`Proxy ${action} failed: ` + e.message);
  }
  refreshStatus();
}

/* ---------------- keys form ---------------- */

async function onSaveKeys(ev) {
  ev.preventDefault();
  const form = ev.target;
  const payload = {};
  for (const input of form.querySelectorAll("input")) {
    if (input.value) payload[input.name] = input.value; // only send filled fields
  }
  if (Object.keys(payload).length === 0) {
    showError("No key values entered.");
    return;
  }
  try {
    const readiness = await api("/api/keys", { method: "POST", headers: jsonHeaders, body: JSON.stringify(payload) });
    // Clear inputs so secrets don't linger in the DOM.
    for (const input of form.querySelectorAll("input")) input.value = "";
    renderKeysReadiness(readiness);
    refreshStatus();
  } catch (e) {
    showError("Save keys failed: " + e.message);
  }
}

function renderKeysReadiness(result) {
  const ul = $("keys-readiness");
  if (!ul || !result || typeof result !== "object") return;
  ul.textContent = "";

  // New shape: { keys: {VAR: maskedString}, readiness: [{name, tier, ok, detail}] }.
  const keys = result.keys && typeof result.keys === "object" ? result.keys : null;
  const readiness = Array.isArray(result.readiness) ? result.readiness : null;

  if (keys || readiness) {
    for (const [k, v] of Object.entries(keys || {})) {
      const masked = typeof v === "string" ? v : String(v);
      ul.append(el("li", null,
        el("span", { class: "dot dot-green" }),
        el("span", { text: ` ${k}: ${masked}` })
      ));
    }
    for (const r of readiness || []) {
      const ok = !!r.ok;
      const name = (r.name || "?") + (r.tier ? ` (${r.tier})` : "");
      ul.append(el("li", null,
        el("span", { class: "dot dot-" + (ok ? "green" : "red") }),
        el("span", { text: ` ${name}: ${r.detail || (ok ? "ok" : "not ready")}` })
      ));
    }
    return;
  }

  // Legacy flat-map fallback: { VAR: maskedString | bool | {masked, ready} }.
  for (const [k, v] of Object.entries(result)) {
    const ready = v === true || (v && typeof v === "object" && v.ready) || (typeof v === "string" && v);
    const masked = typeof v === "string" ? v : (v && v.masked) || (ready ? "set" : "unset");
    ul.append(el("li", null,
      el("span", { class: "dot dot-" + (ready ? "green" : "red") }),
      el("span", { text: ` ${k}: ${masked}` })
    ));
  }
}

/* ---------------- wiring ---------------- */

function wireUp() {
  $("new-chat")?.addEventListener("click", async () => {
    try {
      const t = await api("/api/threads", { method: "POST", headers: jsonHeaders, body: JSON.stringify({}) });
      await loadThreads();
      selectThread(t.id);
    } catch (e) {
      showError("New chat failed: " + e.message);
    }
  });

  $("composer")?.addEventListener("submit", onSubmit);

  // Enter to send, Shift+Enter for newline.
  $("input")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      $("composer")?.requestSubmit();
    }
  });

  // Council-only controls dim for ask.
  const syncCouncilControls = () => {
    const isCouncil = $("tool")?.value === "council";
    for (const id of ["mode", "size"]) {
      const c = $(id);
      if (c) c.disabled = !isCouncil;
    }
  };
  $("tool")?.addEventListener("change", syncCouncilControls);
  syncCouncilControls();

  $("refresh-status")?.addEventListener("click", refreshStatus);
  $("nav-chat")?.addEventListener("click", () => showView("chat"));
  $("nav-settings")?.addEventListener("click", () => showView("settings"));
  $("proxy-start")?.addEventListener("click", () => proxyControl("start"));
  $("proxy-restart")?.addEventListener("click", () => proxyControl("restart"));
  $("keys-form")?.addEventListener("submit", onSaveKeys);
}

function init() {
  wireUp();
  loadModels();
  loadThreads();
  refreshStatus();
  statusTimer = setInterval(refreshStatus, 5000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
