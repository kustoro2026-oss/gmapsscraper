/**
 * Google Maps Scraper — Landing Page Logic
 * Redirect form submit ke halaman /hasil
 */

const form      = document.getElementById("scrape-form");
const submitBtn = document.getElementById("submit-btn");

form.addEventListener("submit", (e) => {
    e.preventDefault();

    const keyword = document.getElementById("keyword").value.trim();
    const maxScrolls = parseInt(document.getElementById("max-scrolls").value) || 0;
    const proxy = document.getElementById("proxy").value.trim();

    // Kumpulkan field yang dipilih
    const fieldCheckboxes = document.querySelectorAll('input[name="fields"]:checked');
    const fields = [...fieldCheckboxes].map(cb => cb.value);

    if (!keyword) {
        alert("Masukkan kata kunci pencarian!");
        return;
    }

    if (fields.length === 0) {
        alert("Pilih minimal satu data yang ingin diekstrak!");
        return;
    }

    // Redirect ke halaman /hasil dengan parameter
    const params = new URLSearchParams();
    params.set("keyword", keyword);
    params.set("max_scrolls", maxScrolls.toString());
    params.set("fields", fields.join(","));
    if (proxy) {
        params.set("proxy", proxy);
    }

    window.location.href = "/hasil?" + params.toString();
});
