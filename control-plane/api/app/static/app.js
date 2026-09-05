const state = { user: null, images: [], keys: [] };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
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

function escapeText(value) { return String(value || ""); }
function formatDate(value) { return value ? new Date(value).toLocaleString("ko-KR") : "–"; }
function statusBadge(status) { const span = document.createElement("span"); span.className = `status status-${status}`; span.textContent = status; return span; }

function fillSelect(select, values, valueKey, label) {
  // refresh()가 주기적으로 실행되어도 사용자가 고른 값을 유지한다.
  // 기존 값이 더 이상 목록에 없을 때만 브라우저가 첫 항목을 선택한다.
  const selectedValue = select.value;
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option"); option.value = value[valueKey]; option.textContent = label(value); select.append(option);
  }
  if (values.some((value) => value[valueKey] === selectedValue)) select.value = selectedValue;
}

async function loadKeysAndImages() {
  [state.keys, state.images] = await Promise.all([api("/v1/ssh-keys"), api("/v1/images")]);
  fillSelect($("#instance-key"), state.keys, "id", (key) => `${key.name} — ${key.fingerprint}`);
  fillSelect($("#instance-image"), state.images, "id", (image) => `${image.display_name} (${image.os_family} ${image.os_version})`);
  const list = $("#key-list"); list.replaceChildren();
  if (!state.keys.length) list.innerHTML = "<li class=\"hint\">등록된 공개키가 없습니다. 먼저 공개키를 등록하세요.</li>";
  for (const key of state.keys) { const item = document.createElement("li"); const name = document.createElement("strong"); name.textContent = key.name; const fp = document.createElement("code"); fp.textContent = key.fingerprint; item.append(name, fp); list.append(item); }
}

async function loadInstances() {
  const instances = await api("/v1/instances"); const body = $("#instance-list"); body.replaceChildren();
  if (!instances.length) { body.innerHTML = "<tr><td colspan=\"6\">아직 생성한 VM이 없습니다.</td></tr>"; return; }
  for (const instance of instances) {
    const row = document.createElement("tr");
    const cells = [instance.name, null, instance.image_id, instance.assigned_compute || "scheduler 대기", instance.provider_ip ? `${instance.guest_username}@${instance.provider_ip}` : "IP 대기"];
    cells.forEach((value, index) => { const cell = document.createElement("td"); if (index === 1) cell.append(statusBadge(instance.status)); else cell.textContent = escapeText(value); row.append(cell); });
    const actions = document.createElement("td");
    if (["ACTIVE", "ERROR"].includes(instance.status)) { const button = document.createElement("button"); button.className = "danger"; button.textContent = "삭제"; button.onclick = () => deleteInstance(instance); actions.append(button); }
    else { actions.textContent = "처리 중"; }
    row.append(actions); body.append(row);
  }
}

async function loadAdmin() {
  if (state.user.role !== "admin") return;
  const [overview, users] = await Promise.all([api("/v1/admin/overview"), api("/v1/users")]);
  $("#metric-users").textContent = overview.users; $("#metric-instances").textContent = overview.active_instances; $("#metric-operations").textContent = overview.queued_operations;
  const cards = $("#compute-cards"); cards.replaceChildren();
  overview.compute_nodes.forEach((node) => {
    const cpuPercent = Math.min(100, (node.allocated_vcpus / node.allocatable_vcpus) * 100);
    const memoryPercent = Math.min(100, (node.allocated_memory_mb / node.allocatable_memory_mb) * 100);
    const card = document.createElement("article"); card.className = "compute-card";
    card.innerHTML = `<h3>${node.name}</h3><p>${node.state} · VM ${node.active_instances}개</p><p>vCPU ${node.allocated_vcpus}/${node.allocatable_vcpus}</p><div class="bar"><span style="width:${cpuPercent}%"></span></div><p>Memory ${node.allocated_memory_mb}/${node.allocatable_memory_mb} MB</p><div class="bar"><span style="width:${memoryPercent}%"></span></div>`;
    cards.append(card);
  });
  const userList = $("#user-list"); userList.replaceChildren();
  users.forEach((user) => { const row = document.createElement("tr"); [user.username, user.role, user.is_active ? "활성" : "비활성", formatDate(user.created_at)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); userList.append(row); });
}

async function refresh() { await Promise.all([loadKeysAndImages(), loadInstances(), loadAdmin()]); }
async function deleteInstance(instance) { if (!confirm(`${instance.name} VM과 연결된 디스크를 정상 종료 후 삭제할까요?`)) return; try { await api(`/v1/instances/${instance.id}`, { method: "DELETE" }); message("삭제 작업을 큐에 등록했습니다.", "success"); await refresh(); } catch (error) { message(error.message, "error"); } }

$("#login-form").addEventListener("submit", async (event) => { event.preventDefault(); try { state.user = await api("/v1/auth/login", { method: "POST", body: JSON.stringify({ username: $("#login-username").value, password: $("#login-password").value }) }); $("#login-view").hidden = true; $("#app-view").hidden = false; $("#current-user").textContent = `${state.user.username} (${state.user.role})`; const admin = state.user.role === "admin"; $("#admin-overview").hidden = !admin; $("#admin-users").hidden = !admin; $("#instance-heading").textContent = admin ? "전체 VM" : "내 VM"; await refresh(); } catch (error) { $("#login-message").textContent = error.message; } });
$("#logout-button").onclick = async () => { await api("/v1/auth/logout", { method: "POST" }); location.reload(); };
$("#key-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await api("/v1/ssh-keys", { method: "POST", body: JSON.stringify({ name: $("#key-name").value, public_key: $("#key-value").value }) }); event.target.reset(); message("공개키를 등록했습니다.", "success"); await loadKeysAndImages(); } catch (error) { message(error.message, "error"); } });
$("#instance-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await api("/v1/instances", { method: "POST", body: JSON.stringify({ name: $("#instance-name").value, image_id: $("#instance-image").value, ssh_public_key_id: $("#instance-key").value, vcpus: Number($("#instance-vcpus").value), memory_mb: Number($("#instance-memory").value), disk_gb: Number($("#instance-disk").value) }) }); event.target.reset(); message("VM 생성 작업을 큐에 등록했습니다. 상태가 ACTIVE가 될 때까지 잠시 기다리세요.", "success"); await loadInstances(); } catch (error) { message(error.message, "error"); } });
$("#user-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await api("/v1/users", { method: "POST", body: JSON.stringify({ username: $("#new-username").value, password: $("#new-password").value, role: $("#new-role").value }) }); event.target.reset(); message("사용자를 생성했습니다.", "success"); await loadAdmin(); } catch (error) { message(error.message, "error"); } });
document.querySelectorAll(".refresh-button").forEach((button) => button.addEventListener("click", () => refresh().catch((error) => message(error.message, "error"))));
(async () => { try { state.user = await api("/v1/me"); $("#login-view").hidden = true; $("#app-view").hidden = false; $("#current-user").textContent = `${state.user.username} (${state.user.role})`; const admin = state.user.role === "admin"; $("#admin-overview").hidden = !admin; $("#admin-users").hidden = !admin; $("#instance-heading").textContent = admin ? "전체 VM" : "내 VM"; await refresh(); } catch (_) { /* 로그인 전 상태가 정상이다. */ } })();
setInterval(() => { if (state.user) refresh().catch(() => {}); }, 5000);
