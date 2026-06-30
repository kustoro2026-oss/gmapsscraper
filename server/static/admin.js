/** Admin Panel JS — GMaps Scraper v2 */

const TOKEN = localStorage.getItem("token");
const USER = JSON.parse(localStorage.getItem("user") || "null");

if (!TOKEN || !USER || USER.role !== "admin") {
    document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;color:#ef4444;font-size:20px;">Access Denied — Admin Only</div>';
    throw new Error("Not admin");
}

// ── Tab Navigation ─────────────────────────────────────────────

function switchTab(tab) {
    document.querySelectorAll(".tab").forEach(el => el.classList.remove("active"));
    const target = document.getElementById("tab-" + tab);
    if (target) target.classList.add("active");
    document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
    const navBtn = document.querySelector(`nav button:nth-child(${getTabIndex(tab)})`);
    if (navBtn) navBtn.classList.add("active");
    if (tab === "dashboard") loadDashboard();
    if (tab === "users") loadUsers();
    if (tab === "transactions") loadTransactions();
    if (tab === "packages") loadPackages();
}

function getTabIndex(tab) {
    const map = { dashboard: 1, users: 2, transactions: 3, packages: 4, activity: 5 };
    return map[tab] || 1;
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
    // Recent transactions
    const txns = await api("/api/admin/transactions?page=1");
    document.getElementById("recent-txns").innerHTML = (txns.transactions || []).slice(0, 10).map(t => `
        <tr><td>${esc(t.user_email)}</td><td>${t.product.toUpperCase()}</td><td>Rp ${t.amount.toLocaleString()}</td><td><span class="badge badge-${t.status}">${t.status}</span></td><td>${t.created_at?.slice(0,16)||"-"}</td></tr>
    `).join("");
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

    const pag = document.getElementById("user-pagination");
    let html = "";
    for (let i = 1; i <= data.total_pages; i++) {
        html += `<button onclick="loadUsers(${i})" style="${i===page?'background:#3b82f6;':''}">${i}</button>`;
    }
    pag.innerHTML = html;
}

let _pkgCache = null;
async function getPackages() {
    if (!_pkgCache) _pkgCache = await api("/api/admin/packages");
    return _pkgCache;
}

async function viewUser(userId) {
    const data = await api(`/api/admin/users/${userId}`);
    const u = data.user;
    const pkgData = await getPackages();
    const pkgOptions = Object.entries(pkgData).map(([k,p]) => `<option value="${k}">${p.name} (Rp ${(p.price/1000).toFixed(0)}K)</option>`).join("");

    let licHtml = data.licenses.map(l => `
        <div style="background:#0f172a;padding:12px;border-radius:8px;margin-bottom:8px;">
            <strong>${l.package.toUpperCase()}</strong> — Quota: ${l.used_quota}/${l.total_quota} (sisa ${l.remaining})
            <br><span style="color:#94a3b8;font-size:12px;">Max scroll: ${l.max_scrolls} | ${l.is_active ? "Active":"Inactive"} | ${l.created_at?.slice(0,10)}</span>
        </div>
    `).join("") || "<p style='color:#94a3b8;'>Belum ada lisensi</p>";

    document.getElementById("user-modal-content").innerHTML = `
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
            <button class="btn-sm btn-outline" onclick="editScrolls('${userId}', ${data.licenses[0]?.max_scrolls||1})">Edit Max Scroll</button>
            <div class="license-add-box" style="display:flex;gap:6px;align-items:center;">
                <select id="lic-pkg-${userId}" style="padding:4px 8px;border-radius:6px;font-size:12px;">${pkgOptions}</select>
                <button class="btn-sm btn-green" onclick="addLicense('${userId}')">+ Lisensi</button>
            </div>
            <button class="btn-sm btn-outline" onclick="resetKey('${userId}')">Reset Key</button>
            ${u.is_banned ? `<button class="btn-sm btn-outline" onclick="closeModal();unbanUser('${userId}')">Unban</button>` : `<button class="btn-sm btn-danger" onclick="closeModal();banUser('${userId}')">Ban</button>`}
            <button class="btn-sm btn-outline" onclick="closeModal()">Tutup</button>
        </div>
    `;
    document.getElementById("user-modal").classList.remove("hidden");
}

function closeModal() { document.getElementById("user-modal").classList.add("hidden"); }

async function banUser(userId) {
    const reason = prompt("Alasan ban (opsional):") || "";
    const fd = new FormData(); fd.append("reason", reason);
    await api(`/api/admin/users/${userId}/ban`, "POST", fd);
    closeModal(); loadUsers();
}

async function unbanUser(userId) {
    await api(`/api/admin/users/${userId}/unban`, "POST", new FormData());
    closeModal(); loadUsers();
}

async function addQuota(userId) {
    const amount = parseInt(prompt("Tambah quota:") || "0");
    if (!amount || amount <= 0) return;
    const fd = new FormData(); fd.append("amount", amount.toString());
    await api(`/api/admin/users/${userId}/add-quota`, "POST", fd);
    alert("Quota ditambah " + amount);
    viewUser(userId);
}

async function editQuota(userId, current) {
    const newTotal = parseInt(prompt("Total quota baru:", current) || "0");
    if (!newTotal || newTotal <= 0) return;
    const fd = new FormData(); fd.append("new_total", newTotal.toString());
    await api(`/api/admin/users/${userId}/edit-quota`, "POST", fd);
    alert("Quota diubah ke " + newTotal);
    viewUser(userId);
}

async function editScrolls(userId, current) {
    const newScrolls = parseInt(prompt("Max scroll baru:", current) || "0");
    if (!newScrolls || newScrolls <= 0) return;
    const fd = new FormData(); fd.append("max_scrolls", newScrolls.toString());
    await api(`/api/admin/users/${userId}/edit-scrolls`, "POST", fd);
    alert("Max scroll diubah ke " + newScrolls);
    viewUser(userId);
}

async function addLicense(userId) {
    const pkgSelect = document.getElementById("lic-pkg-" + userId);
    if (!pkgSelect) return;
    const pkgKey = pkgSelect.value;
    if (!confirm(`Tambah lisensi ${pkgKey.toUpperCase()} untuk user ini? Lisensi lama akan dinonaktifkan.`)) return;
    const fd = new FormData(); fd.append("package_key", pkgKey);
    const data = await api(`/api/admin/users/${userId}/add-license`, "POST", fd);
    if (data.success) { alert(data.message); viewUser(userId); }
    else { alert(data.detail || "Gagal"); }
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

// ── Packages ───────────────────────────────────────────────────

async function loadPackages() {
    _pkgCache = null; // refresh cache
    const pkgs = await getPackages();
    const entries = Object.entries(pkgs);
    document.getElementById("packages-table").innerHTML = entries.length === 0
        ? '<tr><td colspan="6" class="empty">Belum ada paket</td></tr>'
        : entries.map(([k, p]) => `
            <tr>
                <td><code>${esc(k)}</code></td>
                <td>${esc(p.name)}</td>
                <td>Rp ${p.price.toLocaleString()}</td>
                <td>${p.quota}</td>
                <td>${p.max_scrolls}</td>
                <td>
                    <button class="btn-sm btn-primary" onclick="editPackage('${k}','${esc(p.name)}',${p.price},${p.quota},${p.max_scrolls})">Edit</button>
                    <button class="btn-sm btn-danger" onclick="deletePackage('${k}')">Hapus</button>
                </td>
            </tr>
        `).join("");
}

function showAddPackage() {
    document.getElementById("pkg-modal-body").innerHTML = `
        <h3>Tambah Paket Baru</h3>
        <form onsubmit="saveNewPackage(event)">
            <label>Key</label><input type="text" id="pkg-key" placeholder="e.g. ultimate" required style="width:100%;margin-bottom:8px;">
            <label>Nama</label><input type="text" id="pkg-name" required style="width:100%;margin-bottom:8px;">
            <label>Harga (Rp)</label><input type="number" id="pkg-price" required style="width:100%;margin-bottom:8px;">
            <label>Quota</label><input type="number" id="pkg-quota" required style="width:100%;margin-bottom:8px;">
            <label>Max Scroll</label><input type="number" id="pkg-scrolls" required style="width:100%;margin-bottom:12px;">
            <div style="display:flex;gap:8px;">
                <button type="submit" class="btn-blue btn-sm">Simpan</button>
                <button type="button" class="btn-outline btn-sm" onclick="closePkgModal()">Batal</button>
            </div>
        </form>
    `;
    document.getElementById("pkg-modal").classList.remove("hidden");
}

function editPackage(key, name, price, quota, scrolls) {
    document.getElementById("pkg-modal-body").innerHTML = `
        <h3>Edit Paket: ${esc(name)}</h3>
        <form onsubmit="saveEditPackage(event, '${key}')">
            <label>Nama</label><input type="text" id="pkg-name" value="${esc(name)}" required style="width:100%;margin-bottom:8px;">
            <label>Harga (Rp)</label><input type="number" id="pkg-price" value="${price}" required style="width:100%;margin-bottom:8px;">
            <label>Quota</label><input type="number" id="pkg-quota" value="${quota}" required style="width:100%;margin-bottom:8px;">
            <label>Max Scroll</label><input type="number" id="pkg-scrolls" value="${scrolls}" required style="width:100%;margin-bottom:12px;">
            <div style="display:flex;gap:8px;">
                <button type="submit" class="btn-blue btn-sm">Simpan</button>
                <button type="button" class="btn-outline btn-sm" onclick="closePkgModal()">Batal</button>
            </div>
        </form>
    `;
    document.getElementById("pkg-modal").classList.remove("hidden");
}

function closePkgModal() {
    document.getElementById("pkg-modal").classList.add("hidden");
}

async function saveNewPackage(e) {
    e.preventDefault();
    const fd = new FormData();
    fd.append("package_key", document.getElementById("pkg-key").value.trim());
    fd.append("name", document.getElementById("pkg-name").value.trim());
    fd.append("price", document.getElementById("pkg-price").value);
    fd.append("quota", document.getElementById("pkg-quota").value);
    fd.append("max_scrolls", document.getElementById("pkg-scrolls").value);
    const data = await api("/api/admin/packages", "POST", fd);
    if (data.success) { closePkgModal(); loadPackages(); alert("Paket ditambahkan!"); }
    else { alert(data.detail || "Gagal menambah paket"); }
}

async function saveEditPackage(e, key) {
    e.preventDefault();
    const fd = new FormData();
    fd.append("name", document.getElementById("pkg-name").value.trim());
    fd.append("price", document.getElementById("pkg-price").value);
    fd.append("quota", document.getElementById("pkg-quota").value);
    fd.append("max_scrolls", document.getElementById("pkg-scrolls").value);
    const data = await api(`/api/admin/packages/${key}`, "PUT", fd);
    if (data.success) { closePkgModal(); loadPackages(); alert("Paket diupdate!"); }
    else { alert(data.detail || "Gagal update paket"); }
}

async function deletePackage(key) {
    if (!confirm(`Hapus paket "${key}"? Lisensi existing TIDAK akan terpengaruh.`)) return;
    const data = await api(`/api/admin/packages/${key}`, "DELETE");
    if (data.success) { loadPackages(); alert("Paket dihapus!"); }
    else { alert(data.detail || "Gagal menghapus paket"); }
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
