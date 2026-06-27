/** Admin Panel JS — GMaps Scraper v2 */

const TOKEN = localStorage.getItem("token");
const USER = JSON.parse(localStorage.getItem("user") || "null");

// Check admin
if (!TOKEN || !USER || USER.role !== "admin") {
    document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;color:#ef4444;font-size:20px;">Access Denied — Admin Only</div>';
    throw new Error("Not admin");
}

// ── Tab Navigation ─────────────────────────────────────────────

function switchTab(tab) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");
    document.querySelectorAll("nav a").forEach(a => a.classList.remove("active"));
    if (tab === "dashboard") loadDashboard();
    if (tab === "users") loadUsers();
    if (tab === "transactions") loadTransactions();
}

// ── API Helper ─────────────────────────────────────────────────

async function api(path, method = "GET", body = null) {
    const opts = { method, headers: { Authorization: "Bearer " + TOKEN } };
    if (body) opts.body = body;
    const resp = await fetch(path, opts);
    if (resp.status === 401) { localStorage.clear(); window.location.href = "/login"; }
    return resp.json();
}

// ── Dashboard ──────────────────────────────────────────────────

async function loadDashboard() {
    const stats = await api("/api/admin/stats");
    document.getElementById("stats-grid").innerHTML = `
        <div class="stat-box"><div class="value">${stats.total_users}</div><div class="label">Total Users</div></div>
        <div class="stat-box"><div class="value">${stats.active_licenses}</div><div class="label">Active Licenses</div></div>
        <div class="stat-box"><div class="value">Rp ${(stats.total_revenue || 0).toLocaleString()}</div><div class="label">Total Revenue</div></div>
        <div class="stat-box"><div class="value">${stats.today_usage}</div><div class="label">Scrape Hari Ini</div></div>
    `;
}

// ── Users ──────────────────────────────────────────────────────

async function loadUsers(page = 1) {
    const search = document.getElementById("user-search").value;
    const data = await api(`/api/admin/users?page=${page}&search=${encodeURIComponent(search)}`);
    const tbody = document.getElementById("user-table");
    tbody.innerHTML = data.users.map(u => `
        <tr>
            <td>${esc(u.email)}</td>
            <td>${esc(u.name || "-")}</td>
            <td><span class="badge ${u.role==='admin'?'badge-admin':'badge-user'}">${u.role}</span></td>
            <td>${u.latest_license || "-"}</td>
            <td>${u.is_banned ? '<span class="badge badge-banned">BANNED</span>' : '<span class="badge badge-success">Active</span>'}</td>
            <td>
                <button class="btn-sm btn-primary" onclick="viewUser('${u.id}')">Detail</button>
                ${u.is_banned
                    ? `<button class="btn-sm btn-outline" onclick="unbanUser('${u.id}')">Unban</button>`
                    : `<button class="btn-sm btn-danger" onclick="banUser('${u.id}')">Ban</button>`}
            </td>
        </tr>
    `).join("");

    // Pagination
    const pag = document.getElementById("user-pagination");
    let html = "";
    for (let i = 1; i <= data.total_pages; i++) {
        html += `<button onclick="loadUsers(${i})" style="${i===page?'background:#3b82f6;':''}">${i}</button>`;
    }
    pag.innerHTML = html;
}

async function viewUser(userId) {
    const data = await api(`/api/admin/users/${userId}`);
    const u = data.user;
    const modal = document.getElementById("user-modal");
    const content = document.getElementById("user-modal-content");

    let licHtml = data.licenses.map(l => `
        <div style="background:#0f172a;padding:12px;border-radius:8px;margin-bottom:8px;">
            <strong>${l.package.toUpperCase()}</strong> — Quota: ${l.used_quota}/${l.total_quota} (sisa ${l.remaining})
            <br><span style="color:#94a3b8;font-size:12px;">Max scroll: ${l.max_scrolls} | ${l.is_active ? "Active":"Inactive"} | ${l.created_at?.slice(0,10)}</span>
        </div>
    `).join("") || "<p style='color:#94a3b8;'>Belum ada lisensi</p>";

    content.innerHTML = `
        <h3>${esc(u.email)}</h3>
        <p><strong>Nama:</strong> ${esc(u.name||"-")} | <strong>Role:</strong> ${u.role} | ${u.is_banned ? '<span class="badge badge-banned">BANNED</span>' : ''}</p>
        <p><strong>API Key:</strong> <code style="color:#22c55e;">${u.api_key||"-"}</code></p>
        <p><strong>Daftar:</strong> ${u.created_at?.slice(0,16)||"-"}</p>
        <hr style="border-color:#334155;margin:16px 0;">
        <h4>Lisensi</h4>${licHtml}
        <hr style="border-color:#334155;margin:16px 0;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn-sm btn-primary" onclick="addQuota('${userId}')">+ Tambah Quota</button>
            <button class="btn-sm btn-outline" onclick="editQuota('${userId}', ${data.licenses[0]?.total_quota||0})">Edit Total Quota</button>
            <button class="btn-sm btn-outline" onclick="resetKey('${userId}')">Reset API Key</button>
            <button class="btn-sm btn-danger" onclick="closeModal();${u.is_banned?'unbanUser':'banUser'}('${userId}')">${u.is_banned?'Unban':'Ban'}</button>
            <button class="btn-sm btn-outline" onclick="closeModal()">Tutup</button>
        </div>
    `;
    modal.classList.remove("hidden");
}

function closeModal() {
    document.getElementById("user-modal").classList.add("hidden");
}

async function banUser(userId) {
    const reason = prompt("Alasan ban (opsional):") || "";
    const fd = new FormData();
    fd.append("reason", reason);
    await api(`/api/admin/users/${userId}/ban`, "POST", fd);
    closeModal();
    loadUsers();
}

async function unbanUser(userId) {
    await api(`/api/admin/users/${userId}/unban`, "POST", new FormData());
    closeModal();
    loadUsers();
}

async function addQuota(userId) {
    const amount = parseInt(prompt("Tambah quota:") || "0");
    if (!amount || amount <= 0) return;
    const fd = new FormData();
    fd.append("amount", amount.toString());
    await api(`/api/admin/users/${userId}/add-quota`, "POST", fd);
    alert("Quota ditambah " + amount);
    viewUser(userId);
}

async function editQuota(userId, current) {
    const newTotal = parseInt(prompt("Total quota baru:", current) || "0");
    if (!newTotal || newTotal <= 0) return;
    const fd = new FormData();
    fd.append("new_total", newTotal.toString());
    await api(`/api/admin/users/${userId}/edit-quota`, "POST", fd);
    alert("Quota diubah ke " + newTotal);
    viewUser(userId);
}

async function resetKey(userId) {
    if (!confirm("Reset API key? Key lama akan dinonaktifkan.")) return;
    const data = await api(`/api/admin/users/${userId}/reset-key`, "POST", new FormData());
    alert("API Key baru: " + data.new_api_key);
    viewUser(userId);
}

// ── Transactions ───────────────────────────────────────────────

async function loadTransactions(page = 1) {
    const status = document.getElementById("txn-filter").value;
    const data = await api(`/api/admin/transactions?page=${page}&status=${status}`);
    document.getElementById("txn-table").innerHTML = data.transactions.map(t => `
        <tr>
            <td>${esc(t.user_email)}</td>
            <td>${t.product.toUpperCase()}</td>
            <td>Rp ${t.amount.toLocaleString()}</td>
            <td><span class="badge badge-${t.status}">${t.status}</span></td>
            <td>${t.payment_method||"-"}</td>
            <td>${t.created_at?.slice(0,16)||"-"}</td>
        </tr>
    `).join("");

    const pag = document.getElementById("txn-pagination");
    pag.innerHTML = "";
    for (let i = 1; i <= data.total_pages; i++) {
        pag.innerHTML += `<button onclick="loadTransactions(${i})" style="${i===page?'background:#3b82f6;':''}">${i}</button>`;
    }
}

// ── Utils ──────────────────────────────────────────────────────

function esc(s) {
    if (!s) return "";
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
}

// ── Init ──────────────────────────────────────────────────────

loadDashboard();
