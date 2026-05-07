// I18n
const i18n = {
  zh: {
    title: "CC Adapter 管理面板",
    loginTitle: "管理员登录",
    loginBtn: "登录",
    loginError: "密码错误",
    loginPlaceholder: "请输入密码",
    dashboard: "状态面板",
    config: "配置编辑",
    playground: "测试面板",
    serverStatus: "服务状态",
    running: "运行中",
    stopped: "未运行",
    apiKey: "API Key",
    configured: "已配置",
    notConfigured: "未配置",
    verify: "验证",
    verifying: "验证中...",
    valid: "有效",
    invalid: "无效",
    save: "保存",
    cancel: "取消",
    saved: "保存成功",
    saveFailed: "保存失败",
    model: "模型",
    messages: "消息",
    stream: "流式输出",
    send: "发送",
    clear: "清空",
    response: "响应",
    configKey: "API Key",
    configBaseUrl: "Base URL",
    configHost: "监听地址",
    configPort: "监听端口",
    configLogLevel: "日志级别",
    rawMode: "源文件编辑",
    formMode: "表单编辑",
    rawSave: "保存源文件",
    rawSaved: "源文件保存成功",
    themeDark: "Dark",
    themeLight: "Light",
    tokenUsage: "Token 用量",
    manage: "管理",
    refresh: "刷新",
    noTokens: "暂未配置 Token",
    addToken: "添加 Token",
    tokenLabel: "标签",
    tokenKey: "API Key",
    tokenAccount: "用户名",
    tokenPlan: "套餐",
    tokenPeriod: "结算周期",
    tokenUsed: "已用量",
    tokenTotal: "总额度",
    tokenModels: "模型分布",
    tokenNormal: "正常",
    tokenInvalid: "无效",
    tokenNetworkError: "网络错误",
    tokenManageTitle: "管理 Token",
    tokenRemove: "删除",
    tokenSave: "保存",
    tokenCancel: "取消",
  },
  en: {
    title: "CC Adapter Admin",
    loginTitle: "Admin Login",
    loginBtn: "Login",
    loginError: "Invalid password",
    loginPlaceholder: "Enter password",
    dashboard: "Dashboard",
    config: "Configuration",
    playground: "Playground",
    serverStatus: "Server Status",
    running: "Running",
    stopped: "Stopped",
    apiKey: "API Key",
    configured: "Configured",
    notConfigured: "Not Configured",
    verify: "Verify",
    verifying: "Verifying...",
    valid: "Valid",
    invalid: "Invalid",
    save: "Save",
    cancel: "Cancel",
    saved: "Saved successfully",
    saveFailed: "Save failed",
    model: "Model",
    messages: "Messages",
    stream: "Stream",
    send: "Send",
    clear: "Clear",
    response: "Response",
    configKey: "API Key",
    configBaseUrl: "Base URL",
    configHost: "Host",
    configPort: "Port",
    configLogLevel: "Log Level",
    rawMode: "Raw Edit",
    formMode: "Form Edit",
    rawSave: "Save Raw",
    rawSaved: "Raw file saved",
    themeDark: "Dark",
    themeLight: "Light",
    tokenUsage: "Token Usage",
    manage: "Manage",
    refresh: "Refresh",
    noTokens: "No tokens configured",
    addToken: "Add Token",
    tokenLabel: "Label",
    tokenKey: "API Key",
    tokenAccount: "User",
    tokenPlan: "Plan",
    tokenPeriod: "Period",
    tokenUsed: "Used",
    tokenTotal: "Total",
    tokenModels: "Models",
    tokenNormal: "Normal",
    tokenInvalid: "Invalid",
    tokenNetworkError: "Network Error",
    tokenManageTitle: "Manage Tokens",
    tokenRemove: "Remove",
    tokenSave: "Save",
    tokenCancel: "Cancel",
  },
};

let lang = localStorage.getItem("cc-admin-lang") || "zh";
let theme = localStorage.getItem("cc-admin-theme") || "light";
let token = localStorage.getItem("cc-admin-token") || null;
let defaultModel = "deepseek/deepseek-v4-flash";

function t(key) { return i18n[lang][key] || key; }

function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.title = t("title");
}

function applyTheme() {
  document.documentElement.dataset.theme = theme;
  document.getElementById("theme-toggle").textContent =
    theme === "dark" ? t("themeLight") : t("themeDark");
}

function toggleTheme() {
  theme = theme === "dark" ? "light" : "dark";
  localStorage.setItem("cc-admin-theme", theme);
  applyTheme();
}

function switchLang(newLang) {
  lang = newLang;
  localStorage.setItem("cc-admin-lang", lang);
  applyLang();
  renderAll();
}

// Toast
let toastTimer = null;
function showToast(msg, type) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3000);
}

// API helpers
async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (resp.status === 401 && path !== "/admin/api/login") {
    showLogin();
    throw new Error("Unauthorized");
  }
  return resp;
}

// Auth
function showLogin() {
  token = null;
  localStorage.removeItem("cc-admin-token");
  document.getElementById("login-overlay").classList.remove("hidden");
  document.getElementById("login-error").classList.add("hidden");
}

async function doLogin() {
  const pw = document.getElementById("login-password").value;
  const resp = await api("POST", "/admin/api/login", { password: pw });
  if (resp.status === 401) {
    document.getElementById("login-error").classList.remove("hidden");
    return;
  }
  const data = await resp.json();
  token = data.token;
  localStorage.setItem("cc-admin-token", token);
  document.getElementById("login-overlay").classList.add("hidden");
  renderAll();
}

// Navigation
function switchTab(name) {
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelector(`.nav-item[data-tab="${name}"]`).classList.add("active");
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.getElementById(`tab-${name}`).classList.add("active");
  renderTab(name);
}

// Render by tab
function renderAll() {
  applyLang();
  applyTheme();
  const active = document.querySelector(".nav-item.active");
  if (active) renderTab(active.dataset.tab);
}

function renderTab(name) {
  if (name === "dashboard") renderDashboard();
  else if (name === "config") renderConfig();
  else if (name === "playground") renderPlayground();
}

// Dashboard
async function renderDashboard() {
  const el = document.getElementById("tab-dashboard");
  el.innerHTML = `
    <h2 data-i18n="dashboard">${t("dashboard")}</h2>
    <div class="card-grid" style="margin-top:16px">
      <div class="card">
        <div class="status-dot" id="health-dot"></div>
        <strong data-i18n="serverStatus">${t("serverStatus")}</strong>
        <p id="health-text" style="margin-top:8px;font-size:13px;color:var(--text-secondary)">Loading...</p>
      </div>
      <div class="card">
        <div class="status-dot" id="key-dot"></div>
        <strong data-i18n="apiKey">${t("apiKey")}</strong>
        <p id="key-text" style="margin-top:8px;font-size:13px;color:var(--text-secondary)">Loading...</p>
        <button class="btn btn-secondary" id="verify-key-btn" style="margin-top:12px">${t("verify")}</button>
      </div>
    </div>`;
  loadDashboard();
  document.getElementById("verify-key-btn").onclick = verifyKey;
  renderUsageSection();
}

async function loadDashboard() {
  try {
    const resp = await api("GET", "/admin/api/health");
    const data = await resp.json();
    document.getElementById("health-dot").className = "status-dot ok";
    document.getElementById("health-text").textContent =
      `${t("running")} | uptime ${Math.floor(data.uptime / 60)}m`;
    document.getElementById("key-dot").className =
      data.cc_api_key_configured ? "status-dot ok" : "status-dot err";
    document.getElementById("key-text").textContent =
      data.cc_api_key_configured ? t("configured") : t("notConfigured");
  } catch {
    document.getElementById("health-dot").className = "status-dot err";
    document.getElementById("health-text").textContent = t("stopped");
  }
}

async function verifyKey() {
  const btn = document.getElementById("verify-key-btn");
  btn.textContent = t("verifying");
  btn.disabled = true;
  try {
    const resp = await api("POST", "/admin/api/verify-key");
    const data = await resp.json();
    showToast(data.valid ? `${t("apiKey")}: ${t("valid")}` : `${t("apiKey")}: ${t("invalid")} - ${data.message}`,
      data.valid ? "success" : "error");
    loadDashboard();
  } catch { showToast(t("saveFailed"), "error"); }
  btn.textContent = t("verify");
  btn.disabled = false;
}

// Token Usage
function renderUsageSection() {
  const container = document.getElementById("tab-dashboard");
  const section = document.createElement("div");
  section.className = "token-usage-section";
  section.innerHTML = `
    <div class="token-usage-header">
      <h3>${t("tokenUsage")}</h3>
      <div class="token-actions">
        <button class="btn btn-secondary" id="usage-manage-btn">${t("manage")}</button>
        <button class="btn btn-primary" id="usage-refresh-btn">${t("refresh")}</button>
      </div>
    </div>
    <div id="usage-cards-container">
      <div class="token-empty">Loading...</div>
    </div>`;
  container.appendChild(section);
  document.getElementById("usage-refresh-btn").onclick = loadUsageData;
  document.getElementById("usage-manage-btn").onclick = showTokenManager;
  loadUsageData();
}

async function loadUsageData() {
  const container = document.getElementById("usage-cards-container");
  if (!container) return;
  container.innerHTML = '<div class="token-empty">Loading...</div>';
  try {
    const resp = await api("POST", "/admin/api/usage/query");
    const data = await resp.json();
    if (!data || data.length === 0) {
      container.innerHTML = `<div class="token-empty">${t("noTokens")}</div>`;
      return;
    }
    container.innerHTML = "";
    for (const item of data) {
      container.appendChild(renderTokenCard(item));
    }
  } catch {
    container.innerHTML = `<div class="token-empty">Error loading usage data</div>`;
  }
}

function renderTokenCard(item) {
  const card = document.createElement("div");
  card.className = "token-card" + (item.ok ? "" : " error");
  const labelKey = localStorage.getItem("cc-token-label-" + item.token) || item.label || "";

  if (item.ok) {
    const usage = item.usage || { total_cost: 0, total_count: 0, models: [] };
    const credits = item.credits || { total: 0, monthly: 0, purchased: 0, free: 0 };
    const sub = item.subscription || { plan_name: "", status: "", period_start: "", period_end: "" };
    const user = item.user || { name: "", email: "" };
    const pct = credits.total > 0 ? Math.min(100, Math.round((usage.total_cost / credits.total) * 100)) : 0;
    let barClass = "token-usage-bar-fill";
    if (pct >= 90) barClass += " danger";
    else if (pct >= 75) barClass += " warning";
    const periodStr = sub.period_start ? `${sub.period_start.slice(0, 10)} ~ ${sub.period_end.slice(0, 10)}` : "";
    const modelsHtml = usage.models && usage.models.length > 0
      ? usage.models.map(m => `${m.model_id.split("/").pop()} $${m.total_cost} (${m.total_count})`).join(" · ")
      : "";
    card.innerHTML = `
      <div class="token-card-header">
        <div>
          <span class="status-dot ok"></span>
          <strong title="${item.token}">${item.token.slice(0, 10)}...${item.token.slice(-6)}</strong>
          ${labelKey ? `<span class="token-label-badge">${labelKey}</span>` : ""}
        </div>
        <span style="font-size:12px;color:var(--success)">${t("tokenNormal")}</span>
      </div>
      <div class="token-card-info">
        ${user.name ? `<div><div class="label">${t("tokenAccount")}</div><div class="value">${user.name}</div></div>` : ""}
        ${sub.plan_name ? `<div><div class="label">${t("tokenPlan")}</div><div class="value">${sub.plan_name} <span style="color:var(--text-muted);font-size:11px">(${sub.status})</span></div></div>` : ""}
        ${user.email ? `<div><div class="label">Email</div><div class="value">${user.email}</div></div>` : ""}
        ${periodStr ? `<div><div class="label">${t("tokenPeriod")}</div><div class="value">${periodStr}</div></div>` : ""}
      </div>
      <div class="token-usage-bar">
        <div class="token-usage-bar-header">
          <span>${t("tokenUsed")} / ${t("tokenTotal")}</span>
          <span><strong>$${usage.total_cost.toFixed(2)}</strong> / $${credits.total.toFixed(2)}</span>
        </div>
        <div class="token-usage-bar-track">
          <div class="${barClass}" style="width:${pct}%"></div>
        </div>
      </div>
      ${modelsHtml ? `<div class="token-models">${t("tokenModels")}: ${modelsHtml}</div>` : ""}`;
  } else {
    const errMsg = item.error || "Unknown error";
    card.innerHTML = `
      <div class="token-card-header">
        <div>
          <span class="status-dot err"></span>
          <strong title="${item.token}">${item.token.slice(0, 10)}...${item.token.slice(-6)}</strong>
          ${labelKey ? `<span class="token-label-badge">${labelKey}</span>` : ""}
        </div>
        <span style="font-size:12px;color:var(--error)">${t("tokenInvalid")}</span>
      </div>
      <div class="token-error-text">${errMsg}</div>`;
  }
  return card;
}

function showTokenManager() {
  const overlay = document.createElement("div");
  overlay.id = "token-manager-overlay";
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:300;";
  overlay.innerHTML = `
    <div class="card" style="width:520px;max-width:90vw;max-height:80vh;overflow-y:auto;">
      <h3 style="margin-bottom:16px">${t("tokenManageTitle")}</h3>
      <div style="margin-bottom:12px;display:flex;gap:8px;">
        <input id="tm-label" placeholder="${t("tokenLabel")}" style="width:100px;padding:6px 10px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);font-size:13px;">
        <input id="tm-key" placeholder="${t("tokenKey")}" style="flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);font-size:13px;font-family:monospace;">
        <button id="tm-add" class="btn btn-primary" style="padding:6px 14px;font-size:13px;">${t("addToken")}</button>
      </div>
      <div id="tm-list"></div>
      <div class="form-actions" style="margin-top:16px;">
        <button id="tm-save" class="btn btn-primary">${t("tokenSave")}</button>
        <button class="btn btn-secondary" onclick="this.closest('#token-manager-overlay').remove()">${t("tokenCancel")}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const listEl = overlay.querySelector("#tm-list");

  document.getElementById("tm-add").onclick = () => {
    const keyInput = document.getElementById("tm-key");
    const labelInput = document.getElementById("tm-label");
    const keyVal = keyInput.value.trim();
    if (!keyVal) return;
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid var(--border);";
    row.innerHTML = `
      <input class="tm-item-label" value="${labelInput.value.trim()}" placeholder="${t("tokenLabel")}" style="width:80px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--text);font-size:12px;">
      <code style="flex:1;font-size:12px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${keyVal.slice(0, 12)}...${keyVal.slice(-8)}</code>
      <button style="color:var(--error);background:none;border:none;cursor:pointer;font-size:16px;" onclick="this.parentElement.remove()">&times;</button>`;
    listEl.appendChild(row);
    keyInput.value = "";
    labelInput.value = "";
  };

  document.getElementById("tm-save").onclick = async () => {
    const items = listEl.querySelectorAll(".tm-item-label");
    const tokens = [];
    // Reconstruct from DOM: each row has a label input and a code element
    const rows = listEl.children;
    for (const row of rows) {
      const labelInput = row.querySelector(".tm-item-label");
      const codeEl = row.querySelector("code");
      if (codeEl) {
        const keyVal = codeEl.textContent.replace("...", "");
        tokens.push(keyVal);
        if (labelInput && labelInput.value) {
          localStorage.setItem("cc-token-label-" + keyVal, labelInput.value);
        }
      }
    }
    const body = { cc_api_key: JSON.stringify(tokens) };
    try {
      const resp = await api("PUT", "/admin/api/config", body);
      if (!resp.ok) throw new Error(await resp.text());
      showToast(t("saved"), "success");
      overlay.remove();
      loadUsageData();
    } catch { showToast(t("saveFailed"), "error"); }
  };
}

// Config
let configData = null;
let configRawMode = false;

async function renderConfig() {
  const el = document.getElementById("tab-config");
  el.innerHTML = `
    <h2 data-i18n="config">${t("config")}</h2>
    <div style="margin-bottom:12px">
      <button class="btn ${configRawMode ? 'btn-primary' : 'btn-secondary'}" id="cfg-toggle-raw">${t("rawMode")}</button>
      <button class="btn ${configRawMode ? 'btn-secondary' : 'btn-primary'}" id="cfg-toggle-form">${t("formMode")}</button>
    </div>
    <div id="cfg-form-view" class="${configRawMode ? 'hidden' : ''}">
      <div class="card">
        <div class="form-group">
          <label>CC_API_KEY</label>
          <input type="password" id="cfg-key" autocomplete="new-password">
        </div>
        <div class="form-group">
          <label>CC_BASE_URL</label>
          <input type="text" id="cfg-base-url">
        </div>
        <div class="form-group">
          <label>CC_ADAPTER_HOST</label>
          <input type="text" id="cfg-host">
        </div>
        <div class="form-group">
          <label>CC_ADAPTER_PORT</label>
          <input type="number" id="cfg-port">
        </div>
        <div class="form-group">
          <label>CC_ADAPTER_LOG_LEVEL</label>
          <select id="cfg-log-level">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
        <div class="form-group">
          <label>CC_ADAPTER_DEFAULT_MODEL</label>
          <input type="text" id="cfg-default-model">
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="cfg-save">${t("save")}</button>
          <button class="btn btn-secondary" id="cfg-cancel">${t("cancel")}</button>
        </div>
      </div>
    </div>
    <div id="cfg-raw-view" class="${configRawMode ? '' : 'hidden'}">
      <div class="card">
        <div class="form-group">
          <label>.env</label>
          <textarea id="cfg-raw-content" style="width:100%;min-height:300px;font-family:monospace;font-size:13px;padding:12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);resize:vertical"></textarea>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="cfg-raw-save">${t("rawSave")}</button>
        </div>
      </div>
    </div>`;
  document.getElementById("cfg-toggle-raw").onclick = () => { configRawMode = true; renderConfig(); };
  document.getElementById("cfg-toggle-form").onclick = () => { configRawMode = false; renderConfig(); };
  if (configRawMode) {
    loadRawConfig();
    document.getElementById("cfg-raw-save").onclick = saveRawConfig;
  } else {
    loadConfig();
    document.getElementById("cfg-save").onclick = saveConfig;
    document.getElementById("cfg-cancel").onclick = loadConfig;
  }
}

async function loadConfig() {
  try {
    const resp = await api("GET", "/admin/api/config");
    configData = await resp.json();
    document.getElementById("cfg-key").value = configData.cc_api_key;
    document.getElementById("cfg-base-url").value = configData.cc_base_url;
    document.getElementById("cfg-host").value = configData.host;
    document.getElementById("cfg-port").value = configData.port;
    document.getElementById("cfg-log-level").value = configData.log_level;
    document.getElementById("cfg-default-model").value = configData.default_model;
  } catch { showToast(t("saveFailed"), "error"); }
}

async function saveConfig() {
  const body = {};
  const key = document.getElementById("cfg-key").value;
  if (key) body.cc_api_key = key;
  const baseUrl = document.getElementById("cfg-base-url").value;
  if (baseUrl !== configData.cc_base_url) body.cc_base_url = baseUrl;
  const host = document.getElementById("cfg-host").value;
  if (host !== configData.host) body.host = host;
  const port = parseInt(document.getElementById("cfg-port").value);
  if (port !== configData.port) body.port = port;
  const logLevel = document.getElementById("cfg-log-level").value;
  if (logLevel !== configData.log_level) body.log_level = logLevel;
  const defaultModelVal = document.getElementById("cfg-default-model").value;
  if (defaultModelVal !== configData.default_model) body.default_model = defaultModelVal;
  if (Object.keys(body).length === 0) { showToast("No changes", "success"); return; }
  try {
    const resp = await api("PUT", "/admin/api/config", body);
    if (!resp.ok) throw new Error(await resp.text());
    configData = await resp.json();
    showToast(t("saved"), "success");
  } catch { showToast(t("saveFailed"), "error"); }
}

async function loadRawConfig() {
  try {
    const resp = await api("GET", "/admin/api/config/raw");
    const data = await resp.json();
    document.getElementById("cfg-raw-content").value = data.content;
  } catch { showToast(t("saveFailed"), "error"); }
}

async function saveRawConfig() {
  const content = document.getElementById("cfg-raw-content").value;
  try {
    const resp = await api("PUT", "/admin/api/config/raw", { content });
    if (!resp.ok) throw new Error(await resp.text());
    showToast(t("rawSaved"), "success");
  } catch { showToast(t("saveFailed"), "error"); }
}

// Playground
async function renderPlayground() {
  try {
    const resp = await fetch("/admin/api/ui-config");
    const cfg = await resp.json();
    if (cfg.default_model) defaultModel = cfg.default_model;
  } catch {}
  const el = document.getElementById("tab-playground");
  el.innerHTML = `
    <h2 data-i18n="playground">${t("playground")}</h2>
    <div class="card playground-form" style="margin-top:16px">
      <div class="form-group">
        <label data-i18n="model">${t("model")}</label>
        <input type="text" id="pg-model" value="${defaultModel}" placeholder="${defaultModel}">
      </div>
      <div class="form-group">
        <label data-i18n="messages">${t("messages")}</label>
        <textarea id="pg-messages" placeholder='[{"role":"user","content":"Hello"}]'>[{"role":"user","content":"ping"}]</textarea>
      </div>
      <div class="checkbox-row">
        <input type="checkbox" id="pg-stream" checked>
        <label for="pg-stream" data-i18n="stream">${t("stream")}</label>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="pg-send">${t("send")}</button>
        <button class="btn btn-secondary" id="pg-clear">${t("clear")}</button>
      </div>
    </div>
    <div class="response-area" id="pg-response"></div>`;
  document.getElementById("pg-send").onclick = sendPlayground;
  document.getElementById("pg-clear").onclick = () => {
    document.getElementById("pg-response").textContent = "";
  };
}

async function sendPlayground() {
  const model = document.getElementById("pg-model").value || defaultModel;
  const messagesText = document.getElementById("pg-messages").value;
  const stream = document.getElementById("pg-stream").checked;
  let messages;
  try { messages = JSON.parse(messagesText); }
  catch { showToast("Invalid JSON in messages", "error"); return; }

  const respArea = document.getElementById("pg-response");
  respArea.textContent = "Sending...";

  if (stream) {
    const response = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true }),
    });
    if (!response.ok) {
      const err = await response.json();
      respArea.textContent = JSON.stringify(err, null, 2);
      return;
    }
    respArea.textContent = "";
    respArea.classList.add("streaming");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ") && line !== "data: [DONE]") {
          try {
            const json = JSON.parse(line.slice(6));
            const content = json.choices?.[0]?.delta?.content || "";
            const reasoning = json.choices?.[0]?.delta?.reasoning_content || "";
            if (content) {
              const div = document.createElement("div");
              div.className = "line";
              div.textContent = content;
              respArea.appendChild(div);
              respArea.scrollTop = respArea.scrollHeight;
            }
            if (reasoning) {
              const div = document.createElement("div");
              div.className = "line thinking";
              div.textContent = "🤔 " + reasoning;
              respArea.appendChild(div);
              respArea.scrollTop = respArea.scrollHeight;
            }
          } catch {}
        }
      }
    }
    respArea.classList.remove("streaming");
  } else {
    try {
      const response = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages, stream: false }),
      });
      const data = await response.json();
      respArea.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      respArea.textContent = `Error: ${e.message}`;
    }
  }
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  // Theme
  applyTheme();
  document.getElementById("theme-toggle").onclick = toggleTheme;

  // Lang
  document.getElementById("lang-switch").value = lang;
  document.getElementById("lang-switch").onchange = (e) => switchLang(e.target.value);

  // Login
  document.getElementById("login-btn").onclick = doLogin;
  document.getElementById("login-password").onkeydown = (e) => {
    if (e.key === "Enter") doLogin();
  };

  // Nav
  document.querySelectorAll(".nav-item").forEach(el => {
    el.onclick = () => switchTab(el.dataset.tab);
  });

  // Check auth on load
  (async () => {
    const resp = await fetch("/admin/api/health", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (resp.status === 401) showLogin();
    else { renderAll(); }
  })();
});
