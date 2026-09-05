const state = {
  user: null,
  images: [],
  keys: [],
  instances: [],
  overview: null,
  users: [],
  selectedInstance: null,
  activeView: "overview",
  refreshing: false,
};

const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["SCHEDULING", "PROVISIONING", "WAITING_FOR_IP", "ACTIVE", "DELETE_REQUESTED", "DELETING"]);
const PAGE_META = {
  overview: ["OVERVIEW", "개요"],
  instances: ["INSTANCE CATALOG", "인스턴스"],
  "instance-detail": ["INSTANCE DETAIL", "인스턴스 상세"],
  create: ["CREATE INSTANCE", "VM 생성"],
  keys: ["ACCESS MANAGEMENT", "SSH 키"],
  operations: ["ADMIN OPERATIONS", "운영 센터"],
  users: ["ADMINISTRATION", "사용자 관리"],
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `요청 실패 (${response.status})`);
  return body;
}

function message(text = "", type = "") {
  const target = $("#app-message");
  target.textContent = text;
  target.className = `message ${type}`;
}

function make(tag, options = {}) {
  const element = document.createElement(tag);
  if (options.className) element.className = options.className;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (options.type) element.type = options.type;
  if (options.title) element.title = options.title;
  return element;
}

function isAdmin() { return state.user?.role === "admin"; }
function formatDate(value) { return value ? new Date(value).toLocaleString("ko-KR") : "–"; }
function formatGbFromMb(value) { return `${(Number(value) / 1024).toFixed(Number(value) % 1024 === 0 ? 0 : 1)} GB`; }
function formatPercent(value) { return value === null || value === undefined ? "수집 대기" : `${value.toFixed(1)}%`; }
function formatRate(value) {
  if (value === null || value === undefined) return "수집 대기";
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB/s`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB/s`;
  return `${value.toFixed(0)} B/s`;
}
function imageLabel(instance) {
  const image = state.images.find((item) => item.id === instance.image_id);
  return image ? image.display_name : instance.image_id;
}
function resourceLabel(instance) { return `${instance.requested_vcpus} vCPU · ${formatGbFromMb(instance.requested_memory_mb)} · ${instance.requested_disk_gb} GB`; }
function statusLabel(status) {
  return ({
    REQUESTED: "요청됨", SCHEDULING: "배치 중", PROVISIONING: "생성 중", WAITING_FOR_IP: "IP 대기",
    ACTIVE: "실행 중", ERROR: "오류", DELETE_REQUESTED: "삭제 요청", DELETING: "삭제 중", DELETED: "삭제됨",
    PENDING: "대기", RUNNING: "실행 중", SUCCEEDED: "완료", FAILED: "실패",
    UP: "정상 수집", DOWN: "수집 실패", WAITING_FOR_METRICS: "수집 대기", WAITING_FOR_INSTANCE: "VM 기동 대기", DISABLED: "비활성",
  })[status] || status;
}
function statusBadge(status) {
  const badge = make("span", { className: `status status-${status}`, text: statusLabel(status) });
  badge.title = status;
  return badge;
}
function monitoringStateLabel(value) { return statusLabel(value); }

function setText(selector, value) { $(selector).textContent = value; }
function fillSelect(select, values, valueKey, label) {
  const selectedValue = select.value;
  select.replaceChildren();
  for (const value of values) {
    const option = make("option", { text: label(value) });
    option.value = value[valueKey];
    select.append(option);
  }
  if (values.some((value) => value[valueKey] === selectedValue)) select.value = selectedValue;
}
function setDefinitionList(selector, rows) {
  const target = $(selector);
  target.replaceChildren();
  for (const [term, description] of rows) {
    const row = document.createElement("div");
    row.append(make("dt", { text: term }), make("dd", { text: description }));
    target.append(row);
  }
}
function addEmptyState(target, text) { target.append(make("p", { className: "empty-state", text })); }

function applyRoleVisibility() {
  const admin = isAdmin();
  document.querySelectorAll(".admin-nav").forEach((item) => { item.hidden = !admin; });
  $("#owner-column-heading").hidden = !admin;
  $("#sidebar-role").textContent = admin ? "ADMIN" : "MEMBER";
  $("#current-user").textContent = `${state.user.username} · ${admin ? "관리자" : "사용자"}`;
  $("#instance-heading").textContent = admin ? "전체 인스턴스" : "내 인스턴스";
  $("#instance-subtitle").textContent = admin
    ? "소유자, 배치 compute, 예약 자원을 기준으로 전체 워크로드를 관리합니다."
    : "내가 요청한 VM의 배치, 접속 정보, 작업 이력을 확인합니다.";
}

function showView(view) {
  if (!PAGE_META[view] || (!isAdmin() && ["operations", "users"].includes(view))) return;
  if (view === "instance-detail" && !state.selectedInstance) view = "instances";
  state.activeView = view;
  document.querySelectorAll(".view").forEach((section) => { section.hidden = section.id !== `view-${view}`; });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
    button.setAttribute("aria-current", button.dataset.view === view ? "page" : "false");
  });
  const [eyebrow, title] = PAGE_META[view];
  setText("#page-eyebrow", eyebrow);
  setText("#page-title", title);
  if (view === "instance-detail") loadSelectedDetails().catch((error) => message(error.message, "error"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadKeysAndImages() {
  [state.keys, state.images] = await Promise.all([api("/v1/ssh-keys"), api("/v1/images")]);
  fillSelect($("#instance-key"), state.keys, "id", (key) => `${key.name} — ${key.fingerprint}`);
  fillSelect($("#instance-image"), state.images, "id", (image) => `${image.display_name} (${image.os_family} ${image.os_version})`);
  const list = $("#key-list");
  list.replaceChildren();
  if (!state.keys.length) addEmptyState(list, "등록된 공개키가 없습니다. VM 생성 전에 공개키를 등록하세요.");
  for (const key of state.keys) {
    const item = document.createElement("li");
    item.append(make("strong", { text: key.name }), make("code", { text: key.fingerprint }));
    list.append(item);
  }
}

function renderOverview() {
  const visible = state.instances;
  const running = visible.filter((item) => item.status === "ACTIVE");
  const processing = visible.filter((item) => ACTIVE_STATUSES.has(item.status) && item.status !== "ACTIVE");
  const monitored = visible.filter((item) => item.monitoring_enabled);
  const admin = isAdmin();
  setText("#overview-greeting", admin ? "플랫폼 운영 현황" : `${state.user.username}님의 자원 현황`);
  setText("#overview-copy", admin
    ? "워크로드의 소유자와 compute 배치를 확인하고, 상세 관측은 Grafana에서 이어서 분석합니다."
    : "내 VM의 생성 상태, 접속 정보, 관리형 모니터링 상태를 확인하세요.");
  setText("#summary-label-one", admin ? "전체 인스턴스" : "내 인스턴스");
  setText("#summary-one", String(visible.length));
  setText("#summary-one-note", processing.length ? `처리 중 ${processing.length}개` : "처리 대기 없음");
  setText("#summary-label-two", "실행 중");
  setText("#summary-two", String(running.length));
  setText("#summary-two-note", admin ? "전체 워크로드 기준" : "내 VM 기준");
  setText("#summary-label-three", "관리형 모니터링");
  setText("#summary-three", String(monitored.length));
  setText("#summary-three-note", monitored.length ? "guest OS exporter 선택됨" : "선택된 VM 없음");

  const target = $("#recent-instances");
  target.replaceChildren();
  if (!visible.length) addEmptyState(target, "아직 인스턴스가 없습니다. ‘새 VM 요청’에서 첫 워크로드를 생성하세요.");
  for (const instance of visible.slice(0, 4)) {
    const row = make("div", { className: "recent-item" });
    const info = document.createElement("div");
    const title = make("strong", { text: instance.name });
    const meta = make("div", { className: "recent-meta" });
    meta.append(statusBadge(instance.status), make("span", { text: imageLabel(instance) }), make("span", { text: instance.assigned_compute || "배치 대기" }));
    if (admin) meta.append(make("span", { text: `소유자 ${instance.owner_username}` }));
    info.append(title, meta);
    const detail = make("button", { className: "quiet mini-action", text: "상세" });
    detail.onclick = () => openInstanceDetail(instance);
    row.append(info, detail);
    target.append(row);
  }
}

function renderInstances() {
  const body = $("#instance-list");
  body.replaceChildren();
  const admin = isAdmin();
  if (!state.instances.length) {
    const row = document.createElement("tr");
    const cell = make("td", { text: "표시할 인스턴스가 없습니다." });
    cell.colSpan = admin ? 8 : 7;
    row.append(cell);
    body.append(row);
    return;
  }
  for (const instance of state.instances) {
    const row = document.createElement("tr");
    row.append(make("td", { text: instance.name }));
    if (admin) row.append(make("td", { text: instance.owner_username }));
    const statusCell = document.createElement("td"); statusCell.append(statusBadge(instance.status)); row.append(statusCell);
    row.append(make("td", { text: imageLabel(instance) }));
    row.append(make("td", { className: "resource-text", text: resourceLabel(instance) }));
    row.append(make("td", { text: instance.assigned_compute || "scheduler 대기" }));
    row.append(make("td", { text: instance.provider_ip ? `${instance.guest_username}@${instance.provider_ip}` : "IP 대기" }));
    const actions = make("td", { className: "table-actions" });
    const detail = make("button", { className: "quiet mini-action", text: "상세" });
    detail.onclick = () => openInstanceDetail(instance);
    actions.append(detail);
    if (["ACTIVE", "ERROR"].includes(instance.status)) {
      const remove = make("button", { className: "danger mini-action", text: "삭제" });
      remove.onclick = () => deleteInstance(instance);
      actions.append(remove);
    }
    row.append(actions);
    body.append(row);
  }
}

function renderUsers() {
  const target = $("#user-list");
  target.replaceChildren();
  for (const user of state.users) {
    const row = document.createElement("tr");
    [user.username, user.role, user.is_active ? "활성" : "비활성", formatDate(user.created_at)].forEach((value) => row.append(make("td", { text: value })));
    target.append(row);
  }
}

function capacityBar(label, used, total, unit) {
  const wrapper = document.createElement("div");
  const line = make("div", { className: "capacity-label" });
  line.append(make("span", { text: label }), make("span", { text: `${used}/${total} ${unit}` }));
  const bar = make("div", { className: "bar" });
  const fill = document.createElement("span");
  fill.style.width = `${Math.min(100, total ? (used / total) * 100 : 0)}%`;
  bar.append(fill); wrapper.append(line, bar);
  return wrapper;
}

function renderAdminOperations() {
  if (!isAdmin() || !state.overview) return;
  setText("#metric-users", String(state.overview.users));
  setText("#metric-instances", String(state.overview.active_instances));
  setText("#metric-operations", String(state.overview.queued_operations));
  const cards = $("#compute-cards");
  cards.replaceChildren();
  for (const node of state.overview.compute_nodes) {
    const card = make("article", { className: "compute-card" });
    card.append(make("h3", { text: node.name }), make("p", { text: `${node.state} · 배치 VM ${node.active_instances}개` }));
    card.append(capacityBar("예약 vCPU", node.allocated_vcpus, node.allocatable_vcpus, "vCPU"));
    card.append(capacityBar("예약 메모리", node.allocated_memory_mb, node.allocatable_memory_mb, "MB"));
    const list = make("div", { className: "placement-list" });
    const assigned = state.instances.filter((item) => item.assigned_compute === node.name && ACTIVE_STATUSES.has(item.status));
    if (!assigned.length) addEmptyState(list, "현재 배치된 실행·처리 VM이 없습니다.");
    for (const instance of assigned) {
      const item = make("div", { className: "placement-item" });
      const info = document.createElement("div");
      info.append(make("p", { text: instance.name }), make("small", { text: `${instance.owner_username} · ${resourceLabel(instance)} · ${statusLabel(instance.status)}` }));
      const detail = make("button", { className: "quiet mini-action", text: "상세" });
      detail.onclick = () => openInstanceDetail(instance);
      item.append(info, detail); list.append(item);
    }
    card.append(list); cards.append(card);
  }
}

async function loadInstances() {
  state.instances = await api("/v1/instances");
  renderOverview();
  renderInstances();
  renderAdminOperations();
}

async function loadAdmin() {
  if (!isAdmin()) return;
  [state.overview, state.users] = await Promise.all([api("/v1/admin/overview"), api("/v1/users")]);
  renderUsers();
  renderAdminOperations();
}

function renderDetail(instance) {
  state.selectedInstance = instance;
  setText("#detail-title", instance.name);
  setText("#detail-subtitle", `${instance.owner_username} · ${formatDate(instance.created_at)} 생성`);
  setDefinitionList("#detail-configuration", [
    ["소유자", instance.owner_username], ["이미지", imageLabel(instance)], ["요청 자원", resourceLabel(instance)],
    ["모니터링", instance.monitoring_enabled ? "관리형 모니터링 활성화" : "비활성"], ["상태", statusLabel(instance.status)],
  ]);
  setDefinitionList("#detail-connectivity", [
    ["배치 compute", instance.assigned_compute || "scheduler 배치 대기"], ["Provider IP", instance.provider_ip || "DHCP IP 대기"],
    ["SSH 계정", instance.guest_username], ["접속 형식", instance.provider_ip ? `ssh -i <private-key> ${instance.guest_username}@${instance.provider_ip}` : "IP가 할당되면 표시됩니다."],
  ]);
  const errorPanel = $("#detail-error-panel");
  errorPanel.hidden = !instance.error_message;
  setText("#detail-error", instance.error_message || "");
  const actions = $("#detail-actions"); actions.replaceChildren();
  if (["ACTIVE", "ERROR"].includes(instance.status)) {
    const remove = make("button", { className: "danger", text: "인스턴스 삭제" });
    remove.onclick = () => deleteInstance(instance);
    actions.append(remove);
  }
}

async function loadOperations(instance) {
  const operations = await api(`/v1/instances/${instance.id}/operations`);
  const target = $("#operation-list"); target.replaceChildren();
  if (!operations.length) addEmptyState(target, "기록된 작업 이력이 없습니다.");
  for (const operation of operations) {
    const item = make("div", { className: "timeline-item" });
    const headline = document.createElement("p"); headline.append(make("strong", { text: `${operation.operation_type} · ` }), statusBadge(operation.status));
    const meta = make("p", { className: "timeline-meta", text: `${formatDate(operation.created_at)} · 시도 ${operation.attempts}회` });
    item.append(headline, meta);
    if (operation.error_message) item.append(make("p", { className: "timeline-error", text: operation.error_message }));
    target.append(item);
  }
}

async function loadMonitoring(instance) {
  const panel = $("#detail-monitoring");
  if (!instance.monitoring_enabled) { panel.hidden = true; return; }
  const data = await api(`/v1/instances/${instance.id}/monitoring`);
  panel.hidden = false;
  const monitorState = $("#monitoring-state");
  monitorState.className = `status status-${data.state}`;
  monitorState.textContent = monitoringStateLabel(data.state);
  setText("#monitoring-cpu", formatPercent(data.cpu_percent));
  setText("#monitoring-memory", formatPercent(data.memory_percent));
  setText("#monitoring-disk", formatPercent(data.root_disk_percent));
  setText("#monitoring-network", `${formatRate(data.network_receive_bytes_per_second)} / ${formatRate(data.network_transmit_bytes_per_second)}`);
  setText("#monitoring-description", data.enabled
    ? `Prometheus가 ${data.provider_ip || "할당 대기"}의 exporter를 control에서만 수집합니다.`
    : "이 VM은 생성할 때 관리형 모니터링을 선택하지 않았습니다.");
  setText("#monitoring-sampled-at", data.sampled_at ? `마지막 exporter 표본: ${formatDate(data.sampled_at)}` : "첫 표본은 VM 기동과 Prometheus 발견 뒤 표시됩니다.");
}

async function loadSelectedDetails() {
  if (!state.selectedInstance) return;
  const current = state.instances.find((item) => item.id === state.selectedInstance.id);
  if (!current) { state.selectedInstance = null; showView("instances"); return; }
  renderDetail(current);
  await Promise.all([loadOperations(current), loadMonitoring(current)]);
}

async function openInstanceDetail(instance) {
  state.selectedInstance = instance;
  showView("instance-detail");
}

async function refresh() {
  if (!state.user || state.refreshing) return;
  state.refreshing = true;
  try {
    await Promise.all([loadKeysAndImages(), loadInstances(), loadAdmin()]);
    if (state.selectedInstance) await loadSelectedDetails();
  } finally { state.refreshing = false; }
}

async function deleteInstance(instance) {
  if (!confirm(`${instance.name} VM과 연결된 overlay 디스크를 정상 종료 후 삭제할까요?`)) return;
  try {
    await api(`/v1/instances/${instance.id}`, { method: "DELETE" });
    message("삭제 작업을 큐에 등록했습니다.", "success");
    await refresh();
    showView("instances");
  } catch (error) { message(error.message, "error"); }
}

async function enterPortal() {
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  applyRoleVisibility();
  showView("overview");
  await refresh();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    state.user = await api("/v1/auth/login", { method: "POST", body: JSON.stringify({ username: $("#login-username").value, password: $("#login-password").value }) });
    await enterPortal();
  } catch (error) { setText("#login-message", error.message); }
});
$("#logout-button").onclick = async () => { await api("/v1/auth/logout", { method: "POST" }); location.reload(); };
document.querySelectorAll(".nav-item,.view-switch").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelectorAll(".refresh-button").forEach((button) => button.addEventListener("click", () => refresh().catch((error) => message(error.message, "error"))));
$("#detail-back").onclick = () => showView("instances");

$("#key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/v1/ssh-keys", { method: "POST", body: JSON.stringify({ name: $("#key-name").value, public_key: $("#key-value").value }) });
    event.target.reset(); message("공개키를 등록했습니다.", "success"); await loadKeysAndImages();
  } catch (error) { message(error.message, "error"); }
});
$("#instance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/v1/instances", { method: "POST", body: JSON.stringify({
      name: $("#instance-name").value, image_id: $("#instance-image").value, ssh_public_key_id: $("#instance-key").value,
      vcpus: Number($("#instance-vcpus").value), memory_mb: Number($("#instance-memory").value), disk_gb: Number($("#instance-disk").value),
      monitoring_enabled: $("#instance-monitoring").checked,
    }) });
    event.target.reset(); message("VM 생성 작업을 큐에 등록했습니다. scheduler가 배치와 생성을 처리합니다.", "success"); await refresh(); showView("instances");
  } catch (error) { message(error.message, "error"); }
});
$("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/v1/users", { method: "POST", body: JSON.stringify({ username: $("#new-username").value, password: $("#new-password").value, role: $("#new-role").value }) });
    event.target.reset(); message("사용자를 생성했습니다.", "success"); await loadAdmin();
  } catch (error) { message(error.message, "error"); }
});

(async () => {
  try { state.user = await api("/v1/me"); await enterPortal(); } catch (_) { /* 로그인 전 상태가 정상이다. */ }
})();
setInterval(() => { refresh().catch(() => {}); }, 10000);
