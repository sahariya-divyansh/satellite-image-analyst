// Frontend application logic for Natural-Language Satellite Image Analyst

document.addEventListener("DOMContentLoaded", () => {
  // Initialize Leaflet Map centered on India (defaulting over Raipur region)
  const map = L.map("map").setView([21.25, 81.63], 11);

  // High-performance dark satellite/carto basemap
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);

  // Layer groups for water change categories
  const layers = {
    persistent: L.layerGroup().addTo(map),
    gained: L.layerGroup().addTo(map),
    lost: L.layerGroup().addTo(map),
  };

  // DOM Elements
  const queryInput = document.getElementById("query-input");
  const submitBtn = document.getElementById("submit-btn");
  const statusCard = document.getElementById("status-card");
  const resultsCard = document.getElementById("results-card");
  const statusBadge = document.getElementById("status-badge");
  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressPercent = document.getElementById("progress-percent");
  const statusDetail = document.getElementById("status-detail");
  const exampleChips = document.querySelectorAll(".chip");
  const tabButtons = document.querySelectorAll(".tab-btn");

  // Example chip handlers
  exampleChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      queryInput.value = chip.getAttribute("data-query") || "";
    });
  });

  // Tab switching logic
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((tc) => tc.classList.remove("active"));
      btn.classList.add("active");
      const targetTab = btn.getAttribute("data-tab");
      const content = document.getElementById(`tab-${targetTab}`);
      if (content) content.classList.add("active");
    });
  });

  // Layer toggles
  document.getElementById("layer-persistent").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layers.persistent);
    else map.removeLayer(layers.persistent);
  });
  document.getElementById("layer-gained").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layers.gained);
    else map.removeLayer(layers.gained);
  });
  document.getElementById("layer-lost").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layers.lost);
    else map.removeLayer(layers.lost);
  });

  // Query Submission
  submitBtn.addEventListener("click", async () => {
    const query = queryInput.value.trim();
    if (!query) return;

    submitBtn.disabled = true;
    statusCard.classList.remove("hidden");
    resultsCard.classList.add("hidden");
    progressBarFill.style.width = "10%";
    progressPercent.textContent = "10%";
    statusBadge.textContent = "Starting";
    statusDetail.textContent = "Submitting query to API...";

    try {
      const response = await fetch("/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
      }

      const job = await response.json();
      pollJobStatus(job.job_id);
    } catch (err) {
      statusBadge.textContent = "Error";
      statusBadge.className = "badge";
      statusBadge.style.color = "#ef4444";
      statusDetail.textContent = err.message || "Failed to submit job.";
      submitBtn.disabled = false;
    }
  });

  async function pollJobStatus(jobId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/v1/jobs/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();

        progressBarFill.style.width = `${data.progress_percent}%`;
        progressPercent.textContent = `${data.progress_percent}%`;
        statusBadge.textContent = data.status.toUpperCase();

        if (data.status === "completed") {
          clearInterval(interval);
          submitBtn.disabled = false;
          statusDetail.textContent = "Pipeline completed successfully.";
          displayResults(data);
        } else if (data.status === "failed") {
          clearInterval(interval);
          submitBtn.disabled = false;
          statusDetail.textContent = data.error || "Analysis failed.";
        }
      } catch (e) {
        console.error("Polling error", e);
      }
    }, 1000);
  }

  function displayResults(data) {
    resultsCard.classList.remove("hidden");
    if (data.plan && data.plan.aoi && data.plan.aoi.bbox) {
      const bbox = data.plan.aoi.bbox;
      map.fitBounds([
        [bbox.min_lat, bbox.min_lon],
        [bbox.max_lat, bbox.max_lon],
      ]);
    }

    if (data.stats) {
      document.getElementById("stat-net-change").textContent = `${data.stats.net_change_ha > 0 ? "+" : ""}${data.stats.net_change_ha} ha`;
      document.getElementById("stat-percent-change").textContent = `${data.stats.percent_change}%`;
      document.getElementById("stat-persistent").textContent = `${data.stats.persistent_water_ha} ha`;
      document.getElementById("stat-gained").textContent = `${data.stats.gained_water_ha} ha`;
      document.getElementById("stat-lost").textContent = `${data.stats.lost_water_ha} ha`;
      document.getElementById("stat-count").textContent = data.stats.waterbody_count;
    }

    document.getElementById("provenance-details").textContent = JSON.stringify(data.plan || {}, null, 2);
  }
});
