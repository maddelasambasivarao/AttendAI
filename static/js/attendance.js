/* attendance.js – Client-side helpers for AttendAI */

document.addEventListener("DOMContentLoaded", function () {

  // ── Live attendance counter ──────────────────────────────────────────────
  function updateCounter() {
    const radios = document.querySelectorAll(".status-group");
    let present = 0, absent = 0, late = 0;
    radios.forEach(group => {
      const checked = group.querySelector("input[type=radio]:checked");
      if (checked) {
        if (checked.value === "present") present++;
        else if (checked.value === "absent") absent++;
        else if (checked.value === "late") late++;
      }
    });
    const counter = document.getElementById("liveCounter");
    if (counter) {
      counter.innerHTML =
        `<span class="text-success fw-semibold">${present} Present</span> &nbsp;|&nbsp; ` +
        `<span class="text-danger fw-semibold">${absent} Absent</span> &nbsp;|&nbsp; ` +
        `<span class="text-warning fw-semibold">${late} Late</span>`;
    }
  }

  // Attach change listeners
  document.querySelectorAll(".status-group input[type=radio]").forEach(r => {
    r.addEventListener("change", updateCounter);
  });
  updateCounter();

  // ── Async ML prediction buttons ───────────────────────────────────────────
  document.querySelectorAll("[data-predict-student]").forEach(btn => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const studentId = this.dataset.predictStudent;
      const badge = document.getElementById(`risk-badge-${studentId}`);
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`;

      fetch(`/analytics/predict/${studentId}`, { method: "POST" })
        .then(r => r.json())
        .then(data => {
          if (data.risk_level && badge) {
            const colors = { High: "danger", Medium: "warning", Low: "success" };
            badge.className = `badge bg-${colors[data.risk_level] || "secondary"}`;
            badge.textContent = data.risk_level;
          }
          btn.disabled = false;
          btn.innerHTML = `<i class="bi bi-robot"></i>`;
        })
        .catch(() => {
          btn.disabled = false;
          btn.innerHTML = `<i class="bi bi-robot"></i>`;
        });
    });
  });

  // ── Confirm delete/deactivate ─────────────────────────────────────────────
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", function (e) {
      if (!confirm(this.dataset.confirm)) e.preventDefault();
    });
  });

  // ── Auto-submit semester selects ──────────────────────────────────────────
  document.querySelectorAll("select[data-autosubmit]").forEach(sel => {
    sel.addEventListener("change", () => sel.closest("form").submit());
  });

});
