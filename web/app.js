// Frontend application logic for Natural-Language Satellite Image Analyst

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialize Leaflet Map
  const map = L.map("map", {
    zoomControl: true,
  }).setView([21.24, 81.63], 11);

  // Basemaps definition
  const esriSatellite = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      attribution:
        "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
      maxZoom: 19,
    }
  );

  const openStreetMap = L.tileLayer(
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }
  );

  // Default basemap: Esri Satellite
  esriSatellite.addTo(map);

  // Basemap switcher buttons
  const btnSatellite = document.getElementById("btn-basemap-satellite");
  const btnOsm = document.getElementById("btn-basemap-osm");

  btnSatellite.addEventListener("click", () => {
    map.removeLayer(openStreetMap);
    map.addLayer(esriSatellite);
    btnSatellite.classList.add("active");
    btnOsm.classList.remove("active");
  });

  btnOsm.addEventListener("click", () => {
    map.removeLayer(esriSatellite);
    map.addLayer(openStreetMap);
    btnOsm.classList.add("active");
    btnSatellite.classList.remove("active");
  });

  // Layer groups for surface water categories
  const geojsonLayers = {
    gained: null,
    lost: null,
    persistent: null,
  };

  const layerGroupGained = L.layerGroup().addTo(map);
  const layerGroupLost = L.layerGroup().addTo(map);
  const layerGroupPersistent = L.layerGroup().addTo(map);

  let currentOpacity = 0.7;

  // DOM Elements
  const queryInput = document.getElementById("query-input");
  const submitBtn = document.getElementById("submit-btn");
  const btnText = document.getElementById("btn-text");
  const btnSpinner = document.getElementById("btn-spinner");
  const demoIndicator = document.getElementById("demo-indicator");

  const clarificationCard = document.getElementById("clarification-card");
  const clarificationText = document.getElementById("clarification-text");
  const clarificationAssumptions = document.getElementById("clarification-assumptions");
  const assumptionsList = document.getElementById("assumptions-list");
  const dismissClarificationBtn = document.getElementById("dismiss-clarification-btn");

  const statusCard = document.getElementById("status-card");
  const statusBadge = document.getElementById("status-badge");
  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressPercent = document.getElementById("progress-percent");
  const statusDetail = document.getElementById("status-detail");

  const resultsCard = document.getElementById("results-card");
  const significanceBadge = document.getElementById("significance-badge");
  const tabButtons = document.querySelectorAll(".tab-btn");

  const opacitySlider = document.getElementById("layer-opacity");
  const opacityVal = document.getElementById("opacity-val");

  // Fetch dynamic examples from API if available
  fetchExamples();

  async function fetchExamples() {
    try {
      const res = await fetch("/v1/examples");
      if (!res.ok) return;
      const data = await res.json();
      if (data.examples && data.examples.length > 0) {
        const container = document.getElementById("examples-container");
        container.innerHTML = "";
        data.examples.forEach((ex) => {
          const btn = document.createElement("button");
          btn.className = "chip";
          btn.textContent = ex.title;
          btn.title = ex.description;
          btn.addEventListener("click", () => {
            queryInput.value = ex.query;
            queryInput.focus();
          });
          container.appendChild(btn);
        });
      }
    } catch {
      // Use fallback HTML chips
    }
  }

  // Example chip click handlers for initial buttons
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      queryInput.value = chip.getAttribute("data-query") || "";
      queryInput.focus();
    });
  });

  // Tab switching
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      document.querySelectorAll(".tab-content").forEach((tc) => tc.classList.remove("active"));
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      const targetTab = btn.getAttribute("data-tab");
      const content = document.getElementById(`tab-${targetTab}`);
      if (content) content.classList.add("active");
    });
  });

  // Dismiss clarification card
  dismissClarificationBtn.addEventListener("click", () => {
    clarificationCard.classList.add("hidden");
    queryInput.focus();
  });

  // Layer visibility checkboxes
  document.getElementById("layer-gained").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layerGroupGained);
    else map.removeLayer(layerGroupGained);
  });

  document.getElementById("layer-lost").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layerGroupLost);
    else map.removeLayer(layerGroupLost);
  });

  document.getElementById("layer-persistent").addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(layerGroupPersistent);
    else map.removeLayer(layerGroupPersistent);
  });

  // Opacity Slider
  opacitySlider.addEventListener("input", (e) => {
    currentOpacity = parseFloat(e.target.value) / 100.0;
    opacityVal.textContent = `${e.target.value}%`;
    updateLayersOpacity();
  });

  function updateLayersOpacity() {
    if (geojsonLayers.gained) {
      geojsonLayers.gained.setStyle({ fillOpacity: currentOpacity, opacity: currentOpacity });
    }
    if (geojsonLayers.lost) {
      geojsonLayers.lost.setStyle({ fillOpacity: currentOpacity, opacity: currentOpacity });
    }
    if (geojsonLayers.persistent) {
      geojsonLayers.persistent.setStyle({ fillOpacity: currentOpacity * 0.7, opacity: currentOpacity });
    }
  }

  // Submit Query
  submitBtn.addEventListener("click", async () => {
    const query = queryInput.value.trim();
    if (!query) return;

    // Reset UI
    submitBtn.disabled = true;
    btnText.textContent = "Analyzing...";
    btnSpinner.classList.remove("hidden");
    clarificationCard.classList.add("hidden");
    resultsCard.classList.add("hidden");
    demoIndicator.classList.add("hidden");

    statusCard.classList.remove("hidden");
    progressBarFill.style.width = "5%";
    progressPercent.textContent = "5%";
    statusBadge.textContent = "QUEUED";
    statusBadge.className = "badge badge-info";
    statusDetail.textContent = "Evaluating query with natural-language planner...";

    // Clear previous map layers
    layerGroupGained.clearLayers();
    layerGroupLost.clearLayers();
    layerGroupPersistent.clearLayers();

    try {
      const response = await fetch("/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      const body = await response.json();

      if (response.status === 200 && body.status === "clarification_required") {
        // Clarification required flow
        statusCard.classList.add("hidden");
        clarificationCard.classList.remove("hidden");
        clarificationText.textContent = body.clarification_question || "Please refine your query with explicit dates or location.";

        if (body.assumptions && body.assumptions.length > 0) {
          clarificationAssumptions.classList.remove("hidden");
          assumptionsList.innerHTML = "";
          body.assumptions.forEach((asm) => {
            const li = document.createElement("li");
            li.textContent = asm;
            assumptionsList.appendChild(li);
          });
        } else {
          clarificationAssumptions.classList.add("hidden");
        }

        submitBtn.disabled = false;
        btnText.textContent = "Run Pipeline";
        btnSpinner.classList.add("hidden");
        return;
      }

      if (!response.ok && response.status !== 202) {
        throw new Error(body.detail || body.title || `API error ${response.status}`);
      }

      const jobId = body.job_id;
      pollJobStatus(jobId);
    } catch (err) {
      statusCard.classList.remove("hidden");
      statusBadge.textContent = "ERROR";
      statusBadge.className = "badge";
      statusBadge.style.color = "#ef4444";
      statusDetail.textContent = err.message || "Failed to submit query.";
      submitBtn.disabled = false;
      btnText.textContent = "Run Pipeline";
      btnSpinner.classList.add("hidden");
    }
  });

  // Polling Job Status
  function pollJobStatus(jobId) {
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/v1/jobs/${jobId}`);
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `Polling failed (${res.status})`);
        }
        const job = await res.json();

        const pct = Math.max(5, job.progress_percent || 0);
        progressBarFill.style.width = `${pct}%`;
        progressPercent.textContent = `${pct}%`;
        statusBadge.textContent = (job.status || "RUNNING").toUpperCase();
        statusDetail.textContent = job.stage || "Executing pipeline...";

        if (job.status === "succeeded") {
          clearInterval(pollInterval);
          submitBtn.disabled = false;
          btnText.textContent = "Run Pipeline";
          btnSpinner.classList.add("hidden");
          statusBadge.textContent = "COMPLETED";
          statusBadge.className = "badge";
          statusBadge.style.color = "#10b981";
          displayResults(job);
        } else if (job.status === "failed") {
          clearInterval(pollInterval);
          submitBtn.disabled = false;
          btnText.textContent = "Run Pipeline";
          btnSpinner.classList.add("hidden");
          statusBadge.textContent = "FAILED";
          statusBadge.className = "badge";
          statusBadge.style.color = "#ef4444";
          statusDetail.textContent = job.error || "Analysis pipeline failed.";
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, 800);
  }

  // Display Succeeded Analysis Results
  async function displayResults(job) {
    resultsCard.classList.remove("hidden");

    // Demo Indicator
    if (job.is_demo) {
      demoIndicator.classList.remove("hidden");
    } else {
      demoIndicator.classList.add("hidden");
    }

    // 1. Scientific Significance Badge (Taken DIRECTLY from API, NEVER computed in JS)
    const significance = (job.stats && job.stats.significance) || "INCONCLUSIVE";
    significanceBadge.textContent = significance.toUpperCase();
    significanceBadge.className = "significance-badge";

    const sigLower = significance.toLowerCase();
    if (sigLower.includes("expansion")) {
      significanceBadge.classList.add("significance-expansion");
    } else if (sigLower.includes("contraction")) {
      significanceBadge.classList.add("significance-contraction");
    } else {
      significanceBadge.classList.add("significance-inconclusive");
    }

    // 2. Populate Grounded Stats
    if (job.stats) {
      const netHa = job.stats.net_change_ha || 0.0;
      const pct = job.stats.percent_change || 0.0;
      document.getElementById("stat-net-change").textContent = `${netHa > 0 ? "+" : ""}${netHa.toFixed(2)} ha`;
      document.getElementById("stat-percent-change").textContent = `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
      document.getElementById("stat-persistent").textContent = `${(job.stats.persistent_water_ha || 0).toFixed(2)} ha`;
      document.getElementById("stat-gained").textContent = `${(job.stats.gained_water_ha || 0).toFixed(2)} ha`;
      document.getElementById("stat-lost").textContent = `${(job.stats.lost_water_ha || 0).toFixed(2)} ha`;
      document.getElementById("stat-churn").textContent = `${((job.stats.churn_ratio || 0) * 100).toFixed(2)}%`;
      document.getElementById("stat-count").textContent = `${job.stats.waterbody_count || 0} features`;

      if (job.stats.headline_1ha) {
        document.getElementById("stat-headline").textContent = `${job.stats.headline_1ha.count} bodies (${job.stats.headline_1ha.net_change_ha > 0 ? "+" : ""}${job.stats.headline_1ha.net_change_ha} ha)`;
      } else {
        document.getElementById("stat-headline").textContent = "N/A";
      }
    }

    // 3. Populate Plan Tab
    const planObj = job.plan || {};
    document.getElementById("plan-details").textContent = JSON.stringify(planObj, null, 2);

    // 4. Load Sandboxed Report HTML
    const reportIframe = document.getElementById("report-iframe");
    reportIframe.src = `/v1/jobs/${job.job_id}/report?format=html`;

    // 5. Wire Download Links
    document.getElementById("btn-dl-geojson").href = `/v1/jobs/${job.job_id}/download/geojson`;
    document.getElementById("btn-dl-csv").href = `/v1/jobs/${job.job_id}/download/csv`;
    document.getElementById("btn-dl-report").href = `/v1/jobs/${job.job_id}/report?format=md`;

    // 6. Fetch Vector GeoJSON Layers and Render on Leaflet Map
    await loadVectorLayers(job.job_id);

    // 7. Pan / Fit Map to Bounding Box
    if (job.plan && job.plan.aoi && job.plan.aoi.bbox) {
      const b = job.plan.aoi.bbox;
      map.fitBounds([
        [b.min_lat, b.min_lon],
        [b.max_lat, b.max_lon],
      ], { padding: [30, 30] });
    }
  }

  // Load and style GeoJSON layers
  async function loadVectorLayers(jobId) {
    layerGroupGained.clearLayers();
    layerGroupLost.clearLayers();
    layerGroupPersistent.clearLayers();

    // Style helper
    function getPolygonStyle(color) {
      return {
        color: color,
        weight: 1.5,
        fillColor: color,
        fillOpacity: currentOpacity,
        opacity: currentOpacity,
      };
    }

    // Feature popup binding
    function onEachFeature(feature, layer) {
      if (!feature.properties) return;
      const p = feature.properties;
      const popupHtml = `
        <div class="popup-title">Water Body #${p.waterbody_id || "N/A"}</div>
        <div class="popup-row"><span>Status:</span><span>${(p.status || "unknown").toUpperCase()}</span></div>
        <div class="popup-row"><span>Baseline (Period A):</span><span>${(p.area_period_a_ha || 0).toFixed(2)} ha</span></div>
        <div class="popup-row"><span>Comparison (Period B):</span><span>${(p.area_period_b_ha || 0).toFixed(2)} ha</span></div>
        <div class="popup-row"><span>Net Difference:</span><span>${(p.net_change_ha > 0 ? "+" : "") + (p.net_change_ha || 0).toFixed(2)} ha</span></div>
        <div class="popup-row"><span>Percent Change:</span><span>${(p.percent_change > 0 ? "+" : "") + (p.percent_change || 0).toFixed(1)}%</span></div>
      `;
      layer.bindPopup(popupHtml);
    }

    try {
      // 1. Gained Layer (Blue)
      const resGained = await fetch(`/v1/jobs/${jobId}/layers/gained.geojson`);
      if (resGained.ok) {
        const geoGained = await resGained.json();
        geojsonLayers.gained = L.geoJSON(geoGained, {
          style: getPolygonStyle("#2563eb"),
          onEachFeature: onEachFeature,
        }).addTo(layerGroupGained);
      }

      // 2. Lost Layer (Red)
      const resLost = await fetch(`/v1/jobs/${jobId}/layers/lost.geojson`);
      if (resLost.ok) {
        const geoLost = await resLost.json();
        geojsonLayers.lost = L.geoJSON(geoLost, {
          style: getPolygonStyle("#dc2626"),
          onEachFeature: onEachFeature,
        }).addTo(layerGroupLost);
      }

      // 3. Persistent Layer (Cyan)
      const resPersistent = await fetch(`/v1/jobs/${jobId}/layers/persistent.geojson`);
      if (resPersistent.ok) {
        const geoPersistent = await resPersistent.json();
        geojsonLayers.persistent = L.geoJSON(geoPersistent, {
          style: {
            color: "#06b6d4",
            weight: 1,
            fillColor: "#06b6d4",
            fillOpacity: currentOpacity * 0.7,
            opacity: currentOpacity,
          },
          onEachFeature: onEachFeature,
        }).addTo(layerGroupPersistent);
      }
    } catch (e) {
      console.warn("Failed loading vector layers:", e);
    }
  }
});
