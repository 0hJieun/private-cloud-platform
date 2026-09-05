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
  preflight: null,
  preflightSequence: 0,
  preflightTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["SCHEDULING", "PROVISIONING", "WAITING_FOR_IP", "ACTIVE", "DELETE_REQUESTED", "DELETING"]);
const ISSUE_STATUSES = new Set(["ERROR", "HOST_DOWN", "GUEST_UNREACHABLE"]);
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

function clearRefreshError() {
  const target = $("#app-message");
  if (target.classList.contains("error")) message();
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
    REQUESTED: "생성 중", SCHEDULING: "생성 중", PROVISIONING: "생성 중", WAITING_FOR_IP: "생성 중",
    ACTIVE: "생성 완료", ERROR: "생성 실패", DELETE_REQUESTED: "삭제 중", DELETING: "삭제 중", DELETED: "삭제됨",
    PENDING: "대기", RUNNING: "실행 중", SUCCEEDED: "완료", FAILED: "실패",
    UP: "정상", DOWN: "응답 없음", RUNTIME_UP: "사용 가능", HOST_DOWN: "호스트 연결 끊김",
    GUEST_UNREACHABLE: "VM 응답 없음", UNMONITORED: "생성 완료", UNKNOWN: "상태 확인 중", NOT_READY: "생성 중",
    WAITING_FOR_METRICS: "상태 확인 중", WAITING_FOR_INSTANCE: "생성 중", DISABLED: "상태 점검 안 함",
  })[status] || status;
}
function statusBadge(status, description = statusLabel(status)) {
  const badge = make("span", { className: `status status-${status}`, text: statusLabel(status) });
  badge.title = description;
  return badge;
}
function monitoringStateLabel(value) { return statusLabel(value); }
function computeObservationLabel(value) {
  return ({ UP: "정상", DOWN: "응답 없음", UNKNOWN: "상태 확인 중" })[value] || value;
}
function instanceDisplayStatus(instance) {
  if (["ERROR", "DELETE_REQUESTED", "DELETING"].includes(instance.status)) return instance.status;
  if (instance.status !== "ACTIVE") return "NOT_READY";
  return instance.runtime_state;
}
function instanceStatusDescription(instance) {
  const display = instanceDisplayStatus(instance);
  if (display === "HOST_DOWN") return `${instance.assigned_compute || "배치 노드"}와의 연결이 끊겼습니다.`;
  if (display === "GUEST_UNREACHABLE") return "배치 노드는 정상이나 VM 상태 점검 응답이 없습니다.";
  if (display === "UNMONITORED") return "VM 생성은 완료됐지만 상태 점검을 설정하지 않았습니다.";
  if (display === "RUNTIME_UP") return "VM 상태 점검이 정상입니다.";
  if (display === "ERROR") return instance.error_message || "VM 생성 작업이 실패했습니다.";
  return statusLabel(display);
}
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
function instancePreflightInput() {
  const name = $("#instance-name").value.trim();
  if (!/^[a-z][a-z0-9-]{0,62}$/.test(name)) return null;
  return {
    name,
    vcpus: Number($("#instance-vcpus").value),
    memory_mb: Number($("#instance-memory").value),
    disk_gb: Number($("#instance-disk").value),
  };
}
function renderPreflight(result = null, checking = false) {
  const badge = $("#preflight-state");
  const hint = $("#preflight-message");
  const submit = $("#instance-form button[type='submit']");
  if (checking) {
    badge.className = "status status-WAITING_FOR_METRICS";
    badge.textContent = "확인 중";
    hint.textContent = "이름 중복과 scheduler 예약 자원을 확인하고 있습니다.";
    submit.disabled = true;
    return;
  }
  if (!result) {
    badge.className = "status status-DISABLED";
    badge.textContent = "입력 대기";
    hint.textContent = "VM 이름과 자원을 선택하면 이름 중복과 예약 자원 수용 가능 여부를 확인합니다.";
    submit.disabled = true;
    return;
  }
  const available = result.name_available && result.capacity_available;
  badge.className = `status status-${available ? "UP" : "DOWN"}`;
  badge.textContent = available ? "요청 가능" : "요청 불가";
  hint.textContent = available
    ? `${result.message} 실제 생성 직전 worker가 compute의 live 자원을 다시 확인합니다.`
    : result.message;
  submit.disabled = !available;
}
async function checkPreflight() {
  const request = instancePreflightInput();
  if (!request) {
    state.preflight = null;
    renderPreflight();
    return null;
  }
  const sequence = ++state.preflightSequence;
  renderPreflight(null, true);
  try {
    const result = await api("/v1/instances/preflight", { method: "POST", body: JSON.stringify(request) });
    if (sequence !== state.preflightSequence) return null;
    state.preflight = result;
    renderPreflight(result);
    return result;
  } catch (error) {
    if (sequence !== state.preflightSequence) return null;
    state.preflight = null;
    renderPreflight();
    $("#preflight-message").textContent = `사전 확인 실패: ${error.message}`;
    return null;
  }
}
function schedulePreflight() {
  clearTimeout(state.preflightTimer);
  state.preflightTimer = setTimeout(() => { checkPreflight().catch(() => {}); }, 350);
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
  $("#compute-column-heading").hidden = !admin;
  $("#sidebar-role").textContent = admin ? "ADMIN" : "MEMBER";
  $("#current-user").textContent = `${state.user.username} · ${admin ? "관리자" : "사용자"}`;
  $("#instance-heading").textContent = admin ? "전체 인스턴스" : "내 인스턴스";
  $("#instance-subtitle").textContent = admin
    ? "소유자, 배치 노드, 예약 자원을 기준으로 전체 워크로드를 관리합니다."
    : "내 VM의 상태와 접속 정보를 확인합니다.";
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
  if (view === "create") schedulePreflight();
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
  const running = visible.filter((item) => item.runtime_state === "RUNTIME_UP");
  const processing = visible.filter((item) => ACTIVE_STATUSES.has(item.status) && item.status !== "ACTIVE");
  const issues = visible.filter((item) => ISSUE_STATUSES.has(instanceDisplayStatus(item)));
  const admin = isAdmin();
  setText("#overview-greeting", admin ? "플랫폼 운영 현황" : `${state.user.username}님의 자원 현황`);
  setText("#overview-copy", admin
    ? "워크로드 상태와 배치 노드를 확인하고, 자세한 운영 지표는 Grafana에서 분석합니다."
    : "내 VM의 현재 상태와 접속 정보를 확인하세요.");
  setText("#summary-label-one", admin ? "전체 인스턴스" : "내 인스턴스");
  setText("#summary-one", String(visible.length));
  setText("#summary-one-note", processing.length ? `생성·삭제 중 ${processing.length}개` : "처리 대기 없음");
  setText("#summary-label-two", "사용 가능");
  setText("#summary-two", String(running.length));
  setText("#summary-two-note", "상태 점검이 정상인 VM");
  setText("#summary-label-three", "문제 있는 VM");
  setText("#summary-three", String(issues.length));
  setText("#summary-three-note", issues.length ? "최근 목록에서 먼저 표시" : "현재 문제 없음");

  const target = $("#recent-instances");
  target.replaceChildren();
  if (!visible.length) addEmptyState(target, "아직 인스턴스가 없습니다. ‘새 VM 요청’에서 첫 워크로드를 생성하세요.");
  const recent = [...visible].sort((left, right) => {
    const leftIssue = ISSUE_STATUSES.has(instanceDisplayStatus(left));
    const rightIssue = ISSUE_STATUSES.has(instanceDisplayStatus(right));
    return Number(rightIssue) - Number(leftIssue);
  });
  for (const instance of recent.slice(0, 4)) {
    const row = make("div", { className: "recent-item" });
    const info = document.createElement("div");
    const title = make("strong", { text: instance.name });
    const meta = make("div", { className: "recent-meta" });
    meta.append(statusBadge(instanceDisplayStatus(instance), instanceStatusDescription(instance)), make("span", { text: imageLabel(instance) }));
    if (admin) meta.append(make("span", { text: instance.assigned_compute || "배치 대기" }));
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
    cell.colSpan = admin ? 8 : 6;
    row.append(cell);
    body.append(row);
    return;
  }
  for (const instance of state.instances) {
    const row = document.createElement("tr");
    row.append(make("td", { text: instance.name }));
    if (admin) row.append(make("td", { text: instance.owner_username }));
    const statusCell = document.createElement("td");
    statusCell.append(statusBadge(instanceDisplayStatus(instance), instanceStatusDescription(instance)));
    row.append(statusCell);
    row.append(make("td", { text: imageLabel(instance) }));
    row.append(make("td", { className: "resource-text", text: resourceLabel(instance) }));
    if (admin) row.append(make("td", { text: instance.assigned_compute || "배치 대기" }));
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
    card.append(make("h3", { text: node.name }), make("p", { text: `${computeObservationLabel(node.observed_state)} · 배치 VM ${node.active_instances}개` }));
    card.append(capacityBar("VM 배정 vCPU", node.allocated_vcpus, node.allocatable_vcpus, "vCPU"));
    card.append(capacityBar("VM 배정 메모리", node.allocated_memory_mb, node.allocatable_memory_mb, "MB"));
    const list = make("div", { className: "placement-list" });
    const assigned = state.instances.filter((item) => item.assigned_compute === node.name && ACTIVE_STATUSES.has(item.status));
    if (!assigned.length) addEmptyState(list, "현재 배치된 실행·처리 VM이 없습니다.");
    for (const instance of assigned) {
      const item = make("div", { className: "placement-item" });
      const info = document.createElement("div");
      info.append(make("p", { text: instance.name }), make("small", { text: `${instance.owner_username} · ${resourceLabel(instance)} · ${statusLabel(instanceDisplayStatus(instance))}` }));
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
  const configuration = [
    ["이미지", imageLabel(instance)], ["요청 자원", resourceLabel(instance)],
    ["현재 상태", statusLabel(instanceDisplayStatus(instance))],
  ];
  if (isAdmin()) {
    configuration.unshift(["소유자", instance.owner_username]);
    if (statusLabel(instanceDisplayStatus(instance)) !== statusLabel(instance.status)) {
      configuration.push(["생성 기록", statusLabel(instance.status)]);
    }
    configuration.push(["자동화 관리", instance.automation_enrolled ? "등록됨" : "등록되지 않음"]);
  }
  setDefinitionList("#detail-configuration", configuration);
  const connectivity = [
    ["Provider IP", instance.provider_ip || "IP 준비 중"], ["SSH 계정", instance.guest_username],
    ["접속 형식", instance.provider_ip ? `ssh -i <private-key> ${instance.guest_username}@${instance.provider_ip}` : "IP가 할당되면 표시됩니다."],
  ];
  if (isAdmin()) connectivity.unshift(["배치 노드", instance.assigned_compute || "배치 대기"]);
  setDefinitionList("#detail-connectivity", connectivity);
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
    : "이 VM은 기본 상태 점검 정책을 적용하기 전에 생성되었습니다.");
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
    if (state.activeView === "create") schedulePreflight();
    clearRefreshError();
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
    const preflight = await checkPreflight();
    if (!preflight || !preflight.name_available || !preflight.capacity_available) {
      message("현재 입력으로는 VM 생성 요청을 제출할 수 없습니다. 사전 확인 결과를 확인하세요.", "error");
      return;
    }
    await api("/v1/instances", { method: "POST", body: JSON.stringify({
      name: $("#instance-name").value, image_id: $("#instance-image").value, ssh_public_key_id: $("#instance-key").value,
      vcpus: Number($("#instance-vcpus").value), memory_mb: Number($("#instance-memory").value), disk_gb: Number($("#instance-disk").value),
    }) });
    event.target.reset(); state.preflight = null; renderPreflight(); message("VM 생성 작업을 큐에 등록했습니다. scheduler가 배치와 생성을 처리합니다.", "success"); await refresh(); showView("instances");
  } catch (error) { message(error.message, "error"); }
});
$("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/v1/users", { method: "POST", body: JSON.stringify({ username: $("#new-username").value, password: $("#new-password").value, role: $("#new-role").value }) });
    event.target.reset(); message("사용자를 생성했습니다.", "success"); await loadAdmin();
  } catch (error) { message(error.message, "error"); }
});
$("#instance-name").addEventListener("input", schedulePreflight);
["#instance-vcpus", "#instance-memory", "#instance-disk"].forEach((selector) => $(selector).addEventListener("change", schedulePreflight));

const statusHelpDialog = $("#status-help-dialog");
$("#status-help-button").addEventListener("click", () => statusHelpDialog.showModal());
statusHelpDialog.addEventListener("click", (event) => {
  const bounds = statusHelpDialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) statusHelpDialog.close();
});

(async () => {
  try { state.user = await api("/v1/me"); await enterPortal(); } catch (_) { /* 로그인 전 상태가 정상이다. */ }
})();
setInterval(() => { refresh().catch(() => {}); }, 10000);
