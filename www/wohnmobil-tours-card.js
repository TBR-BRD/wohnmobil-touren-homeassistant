const WOHNMOBIL_TOURS_VERSION = "1.0.0";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";

const COLORS = [
  "#FF9800","#00BCD4","#4CAF50","#E91E63","#9C27B0",
  "#F44336","#03A9F4","#CDDC39","#FFC107","#795548",
  "#8BC34A","#FF5722","#3F51B5","#009688","#673AB7",
  "#FFEB3B","#2196F3","#C2185B","#7CB342","#F57C00"
];

function ensureWohnmobilLeaflet() {
  if (window.__wohnmobilLeaflet) return Promise.resolve(window.__wohnmobilLeaflet);

  if (!document.querySelector('link[data-wohnmobil-leaflet]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = LEAFLET_CSS;
    link.dataset.wohnmobilLeaflet = "1";
    document.head.appendChild(link);
  }

  if (window.__wohnmobilLeafletPromise) return window.__wohnmobilLeafletPromise;

  window.__wohnmobilLeafletPromise = new Promise((resolve, reject) => {
    const previousL = window.L;
    const script = document.createElement("script");
    script.src = `${LEAFLET_JS}?wohnmobil=1.9.4`;
    script.async = true;
    script.dataset.wohnmobilLeaflet = "1";

    script.onload = () => {
      try {
        const ownL = window.L;
        if (!ownL || !ownL.map || !ownL.geoJSON) {
          throw new Error("Leaflet 1.9.4 wurde nicht korrekt geladen.");
        }
        window.__wohnmobilLeaflet = ownL;
        if (previousL === undefined) {
          try { delete window.L; } catch (_) { window.L = undefined; }
        } else {
          window.L = previousL;
        }
        resolve(window.__wohnmobilLeaflet);
      } catch (err) {
        if (previousL !== undefined) window.L = previousL;
        reject(err);
      }
    };

    script.onerror = () => {
      if (previousL !== undefined) window.L = previousL;
      reject(new Error("Leaflet 1.9.4 konnte nicht geladen werden."));
    };

    document.head.appendChild(script);
  });

  return window.__wohnmobilLeafletPromise;
}

class WohnmobilToursCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._selectedSlot = null;
    this._map = null;
    this._L = null;
    this._renderScheduled = false;
    this._renderGeneration = 0;
    this._lastRelevantToken = null;
  }

  static getStubConfig() {
    return {
      entity: "sensor.wohnmobil_gesamtroute",
      names_entity: "sensor.wohnmobil_tour_names",
      title: "Wohnmobil-Touren",
      height: 720,
      sidebar_width: 320,
      show_rename: true
    };
  }

  getCardSize() { return 12; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 12, min_rows: 6 }; }

  setConfig(config) {
    if (!config.entity) throw new Error("entity fehlt");
    this._config = {
      title: "Wohnmobil-Touren",
      tracker_entity: null,
      names_entity: "sensor.wohnmobil_tour_names",
      height: 720,
      sidebar_width: 320,
      show_rename: true,
      map_tiles: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      line_weight: 4,
      line_opacity: 1,
      ...config
    };
    this._lastRelevantToken = null;
    this._scheduleRender();
  }

  set hass(hass) {
    this._hass = hass;
    const route = hass?.states?.[this._config.entity];
    const names = this._config.names_entity ? hass?.states?.[this._config.names_entity] : null;
    const tracker = this._config.tracker_entity ? hass?.states?.[this._config.tracker_entity] : null;
    const token = [
      this._config.entity || "", route?.last_updated || "",
      this._config.names_entity || "", names?.last_updated || "",
      this._config.tracker_entity || "", tracker?.last_updated || ""
    ].join("|");

    if (token === this._lastRelevantToken) return;
    this._lastRelevantToken = token;
    this._scheduleRender();
  }

  connectedCallback() { this._scheduleRender(); }

  disconnectedCallback() {
    this._renderGeneration++;
    this._destroyMap();
  }

  _destroyMap() {
    if (this._map) {
      try {
        this._map.off();
        this._map.remove();
      } catch (_) {}
      this._map = null;
    }
  }

  _scheduleRender() {
    if (!this.isConnected || !this._hass || !this._config.entity || this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame(async () => {
      this._renderScheduled = false;
      await this._render();
    });
  }

  _routeState() { return this._hass?.states?.[this._config.entity]; }

  _names() {
    const entity = this._hass?.states?.[this._config.names_entity];
    const names = entity?.attributes?.names;
    return names && typeof names === "object" ? names : {};
  }

  _tourMeta() {
    const attrs = this._routeState()?.attributes || {};
    const meta = Array.isArray(attrs.tours) ? attrs.tours : [];
    const result = [];

    for (let i = 0; i < meta.length; i++) {
      const slot = i + 1;
      const key = `tour_${String(slot).padStart(2, "0")}_geojson`;
      const geojson = attrs[key];
      if (!geojson) continue;
      const tourNo = Number(meta[i]?.tour || slot);
      result.push({
        slot,
        geojson,
        meta: meta[i] || {},
        tourNo,
        color: COLORS[(tourNo - 1) % COLORS.length]
      });
    }
    return result;
  }

  _tourName(item) {
    const names = this._names();
    return names[String(item.tourNo)] || item.meta?.name || `Tour ${item.tourNo}`;
  }

  async _saveTourName(item, name) {
    const clean = String(name || "").trim();
    if (clean) {
      await this._hass.callService("wohnmobil_tour_names", "set_name", {
        tour: item.tourNo,
        name: clean
      });
    } else {
      await this._hass.callService("wohnmobil_tour_names", "delete_name", {
        tour: item.tourNo
      });
    }
  }

  _distanceSummary(meta) {
    const gps = Number(meta?.distance_gps_km ?? meta?.distance_km ?? 0);
    const road = Number(meta?.distance_road_km ?? 0);
    const fmt = (v) => Number(v || 0).toLocaleString("de-DE", { maximumFractionDigits: 1 });
    return Number.isFinite(road) && road > 0
      ? `${fmt(road)} km Straße · ${fmt(gps)} km GPS`
      : `${fmt(gps)} km GPS`;
  }

  _formatDate(value) {
    if (!value) return "—";
    try {
      return new Intl.DateTimeFormat("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric"
      }).format(new Date(value));
    } catch { return String(value); }
  }

  _formatDateTime(value) {
    if (!value) return "—";
    try {
      return new Intl.DateTimeFormat("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit"
      }).format(new Date(value));
    } catch { return String(value); }
  }

  _duration(meta) {
    const h = Number(meta?.duration_hours);
    if (!Number.isFinite(h)) return "—";
    return h >= 48 ? `${(h / 24).toFixed(1)} Tage` : `${h.toFixed(1)} h`;
  }

  _collectGeoPoints(geojson, out) {
    if (!geojson || typeof geojson !== "object") return;
    if (geojson.type === "Feature") {
      this._collectGeoPoints(geojson.geometry, out);
      return;
    }
    if (geojson.type === "FeatureCollection") {
      for (const feature of geojson.features || []) this._collectGeoPoints(feature, out);
      return;
    }
    if (geojson.type === "GeometryCollection") {
      for (const geometry of geojson.geometries || []) this._collectGeoPoints(geometry, out);
      return;
    }
    const coords = geojson.coordinates;
    if (!Array.isArray(coords)) return;

    const walk = (node) => {
      if (!Array.isArray(node)) return;
      if (node.length >= 2 && typeof node[0] === "number" && typeof node[1] === "number") {
        const lon = Number(node[0]);
        const lat = Number(node[1]);
        if (Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
          out.push([lat, lon]);
        }
        return;
      }
      for (const child of node) walk(child);
    };
    walk(coords);
  }

  async _render() {
    const generation = ++this._renderGeneration;
    this._destroyMap();
    const stateObj = this._routeState();

    if (!stateObj) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;color:var(--error-color)">Entity ${this._esc(this._config.entity)} nicht gefunden.</div></ha-card>`;
      return;
    }

    const tours = this._tourMeta();
    const selected = this._selectedSlot == null
      ? null
      : tours.find((item) => item.slot === this._selectedSlot) || null;

    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;width:100%}
        ha-card{width:100%;overflow:hidden;--b:var(--divider-color,rgba(127,127,127,.25))}
        .shell{display:grid;grid-template-columns:minmax(0,1fr) ${Math.max(240, Number(this._config.sidebar_width)||320)}px;min-height:${Number(this._config.height)||720}px}
        .map-wrap{min-width:0;position:relative;border-right:1px solid var(--b)}
        #map{width:100%;height:100%;min-height:${Number(this._config.height)||720}px;background:#1a1a1a}
        .side{display:flex;flex-direction:column;min-width:0;max-height:${Number(this._config.height)||720}px;background:var(--ha-card-background,var(--card-background-color))}
        .header{padding:16px 18px 12px;border-bottom:1px solid var(--b)}
        .header h2{margin:0 0 4px;font-size:20px}
        .sub{color:var(--secondary-text-color);font-size:12px}
        .all-btn,.tour-btn{width:100%;border:0;background:transparent;color:var(--primary-text-color);text-align:left;cursor:pointer;font:inherit}
        .all-btn{padding:12px 16px;border-bottom:1px solid var(--b);font-weight:600}
        .all-btn.active,.tour-btn.active{background:color-mix(in srgb,var(--primary-color) 12%,transparent)}
        .list{overflow:auto;flex:1 1 auto}
        .tour-btn{display:grid;grid-template-columns:12px 1fr;gap:10px;padding:11px 16px;border-bottom:1px solid var(--b)}
        .dot{width:10px;height:10px;border-radius:50%;margin-top:5px}
        .tour-name{font-weight:600}
        .tour-meta{color:var(--secondary-text-color);font-size:12px;margin-top:3px}
        .details{border-top:1px solid var(--b);padding:14px 16px 16px}
        .details h3{margin:0 0 10px;font-size:17px}
        .facts{display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font-size:13px}
        .facts .label{color:var(--secondary-text-color)}
        .rename{display:flex;gap:8px;margin-top:12px}
        .rename input{flex:1;min-width:0;padding:8px 10px;border:1px solid var(--b);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color)}
        .rename button{padding:8px 12px;border:0;border-radius:8px;background:var(--primary-color);color:white;cursor:pointer}
        .status{margin-top:6px;font-size:12px;color:var(--secondary-text-color)}
        .map-error{padding:16px;color:var(--error-color);white-space:pre-wrap}
        .leaflet-container{overflow:hidden;position:relative;outline:0;background:#ddd;font-family:sans-serif}
        .leaflet-pane,.leaflet-tile,.leaflet-marker-icon,.leaflet-marker-shadow,.leaflet-tile-container,.leaflet-pane>svg,.leaflet-pane>canvas,.leaflet-zoom-box,.leaflet-image-layer,.leaflet-layer{position:absolute;left:0;top:0}
        .leaflet-container .leaflet-overlay-pane svg{max-width:none!important;max-height:none!important}
        .leaflet-container .leaflet-marker-pane img,.leaflet-container .leaflet-shadow-pane img,.leaflet-container .leaflet-tile-pane img,.leaflet-container img.leaflet-image-layer,.leaflet-container .leaflet-tile{max-width:none!important;max-height:none!important;width:auto;padding:0}
        .leaflet-container.leaflet-touch-zoom{touch-action:pan-x pan-y}
        .leaflet-container.leaflet-touch-drag{touch-action:none;touch-action:pinch-zoom}
        .leaflet-tile{filter:inherit;visibility:hidden}.leaflet-tile-loaded{visibility:inherit}
        .leaflet-zoom-animated{transform-origin:0 0}.leaflet-zoom-hide{visibility:hidden}
        .leaflet-pane{z-index:400}.leaflet-tile-pane{z-index:200}.leaflet-overlay-pane{z-index:400}.leaflet-shadow-pane{z-index:500}.leaflet-marker-pane{z-index:600}.leaflet-tooltip-pane{z-index:650}.leaflet-popup-pane{z-index:700}.leaflet-map-pane canvas{z-index:100}.leaflet-map-pane svg{z-index:200}
        .leaflet-control{position:relative;z-index:800;pointer-events:auto}
        .leaflet-top,.leaflet-bottom{position:absolute;z-index:1000;pointer-events:none}.leaflet-top{top:0}.leaflet-right{right:0}.leaflet-bottom{bottom:0}.leaflet-left{left:0}
        .leaflet-control{float:left;clear:both}.leaflet-right .leaflet-control{float:right}.leaflet-top .leaflet-control{margin-top:10px}.leaflet-bottom .leaflet-control{margin-bottom:10px}.leaflet-left .leaflet-control{margin-left:10px}.leaflet-right .leaflet-control{margin-right:10px}
        .leaflet-bar{box-shadow:0 1px 5px rgba(0,0,0,.65);border-radius:4px}.leaflet-bar a{background-color:#fff;border-bottom:1px solid #ccc;width:26px;height:26px;line-height:26px;display:block;text-align:center;text-decoration:none;color:#000}.leaflet-bar a:first-child{border-top-left-radius:4px;border-top-right-radius:4px}.leaflet-bar a:last-child{border-bottom-left-radius:4px;border-bottom-right-radius:4px;border-bottom:none}
        .leaflet-control-zoom-in,.leaflet-control-zoom-out{font:bold 18px "Lucida Console",Monaco,monospace}.leaflet-control-attribution{padding:0 5px;color:#333;background:rgba(255,255,255,.8);font-size:11px}.leaflet-control-attribution a{text-decoration:none}
        .leaflet-tooltip{position:absolute;padding:6px;background-color:#fff;border:1px solid #fff;border-radius:3px;color:#222;white-space:nowrap;user-select:none;pointer-events:none;box-shadow:0 1px 3px rgba(0,0,0,.4)}
        @media(max-width:850px){.shell{grid-template-columns:1fr}.map-wrap{border-right:0;border-bottom:1px solid var(--b)}#map{min-height:460px}.side{max-height:none}.list{max-height:320px}}
      </style>
      <ha-card>
        <div class="shell">
          <div class="map-wrap"><div id="map"></div></div>
          <div class="side">
            <div class="header">
              <h2>${this._esc(this._config.title)}</h2>
              <div class="sub">${tours.length} Tour${tours.length===1?"":"en"} · Namen zentral in Home Assistant gespeichert</div>
            </div>
            <button class="all-btn ${selected?"":"active"}" data-action="all">Alle Touren anzeigen</button>
            <div class="list">
              ${tours.map((item) => `
                <button class="tour-btn ${selected?.slot===item.slot?"active":""}" data-slot="${item.slot}">
                  <span class="dot" style="background:${item.color}"></span>
                  <span>
                    <div class="tour-name">${this._esc(this._tourName(item))}</div>
                    <div class="tour-meta">${this._formatDate(item.meta?.start)} – ${this._formatDate(item.meta?.end)} · ${this._distanceSummary(item.meta)}</div>
                  </span>
                </button>`).join("")}
            </div>
            <div class="details">${selected ? this._details(selected) : this._allDetails(tours)}</div>
          </div>
        </div>
      </ha-card>`;

    this.shadowRoot.querySelector('[data-action="all"]')?.addEventListener("click", () => {
      this._selectedSlot = null;
      this._scheduleRender();
    });

    this.shadowRoot.querySelectorAll("[data-slot]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._selectedSlot = Number(btn.dataset.slot);
        this._scheduleRender();
      });
    });

    const save = this.shadowRoot.querySelector("[data-action='save-name']");
    const input = this.shadowRoot.querySelector("#rename");
    const status = this.shadowRoot.querySelector("#rename-status");

    if (save && input && selected) {
      const doSave = async () => {
        save.disabled = true;
        if (status) status.textContent = "Speichere…";
        try {
          await this._saveTourName(selected, input.value);
          if (status) status.textContent = "Gespeichert – auf allen HA-Geräten verfügbar.";
        } catch (err) {
          console.error(err);
          if (status) status.textContent = "Speichern fehlgeschlagen.";
        } finally {
          save.disabled = false;
        }
      };
      save.addEventListener("click", doSave);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") doSave();
      });
    }

    try {
      this._L = await ensureWohnmobilLeaflet();
      if (generation !== this._renderGeneration) return;
      const mapEl = this.shadowRoot.querySelector("#map");
      if (!mapEl || !mapEl.isConnected) return;
      this._initMap(tours, selected, mapEl);
    } catch (err) {
      console.error("Wohnmobil Tours Card:", err);
      const mapDiv = this.shadowRoot.querySelector("#map");
      if (mapDiv) mapDiv.innerHTML = `<div class="map-error">${this._esc(err?.stack || err?.message || String(err))}</div>`;
    }
  }

  _allDetails(tours) {
    const gpsKm = tours.reduce((sum, item) => sum + Number(item.meta?.distance_gps_km ?? item.meta?.distance_km ?? 0), 0);
    const matched = tours.filter((item) => Number(item.meta?.distance_road_km) > 0);
    const roadKm = matched.reduce((sum, item) => sum + Number(item.meta?.distance_road_km || 0), 0);
    return `
      <h3>Alle Touren</h3>
      <div class="facts">
        <div class="label">Anzahl</div><div>${tours.length}</div>
        ${matched.length ? `<div class="label">Straßenstrecke</div><div>${roadKm.toLocaleString("de-DE",{maximumFractionDigits:1})} km (${matched.length}/${tours.length} gematcht)</div>` : ""}
        <div class="label">GPS-Strecke</div><div>${gpsKm.toLocaleString("de-DE",{maximumFractionDigits:1})} km</div>
        <div class="label">Ansicht</div><div>Alle Touren farbig</div>
      </div>`;
  }

  _details(item) {
    const meta = item.meta || {};
    return `
      <h3><span class="dot" style="display:inline-block;background:${item.color};vertical-align:middle;margin-right:7px"></span>${this._esc(this._tourName(item))}</h3>
      <div class="facts">
        <div class="label">Zeitraum</div><div>${this._formatDateTime(meta.start)} – ${this._formatDateTime(meta.end)}</div>
        <div class="label">Dauer</div><div>${this._duration(meta)}</div>
        ${Number(meta.distance_road_km) > 0 ? `<div class="label">Straßenstrecke</div><div>${Number(meta.distance_road_km).toLocaleString("de-DE",{maximumFractionDigits:1})} km</div>` : ""}
        <div class="label">GPS-Strecke</div><div>${Number(meta.distance_gps_km ?? meta.distance_km ?? 0).toLocaleString("de-DE",{maximumFractionDigits:1})} km</div>
        ${meta.map_matching_status ? `<div class="label">Map Matching</div><div>${meta.map_matching_status === "ok" ? "OSRM / OpenStreetMap ✓" : `Fehler: ${this._esc(meta.map_matching_error || "unbekannt")}`}</div>` : ""}
        <div class="label">Status</div><div>${meta.active ? "Aktive Tour" : "Abgeschlossen"}</div>
        <div class="label">Tour-Nr.</div><div>${item.tourNo}</div>
      </div>
      ${this._config.show_rename!==false ? `
        <div class="rename">
          <input id="rename" value="${this._escAttr(this._tourName(item))}" placeholder="Tour umbenennen">
          <button data-action="save-name">Speichern</button>
        </div>
        <div class="status" id="rename-status">Name wird zentral in Home Assistant gespeichert.</div>` : ""}`;
  }

  _initMap(tours, selected, mapEl) {
    const L = this._L;
    if (!L) throw new Error("Eigene Leaflet-Instanz ist nicht verfügbar.");
    if (mapEl._leaflet_id) {
      try { delete mapEl._leaflet_id; } catch (_) {}
    }

    this._map = L.map(mapEl, { zoomControl: true, attributionControl: true });
    const shown = selected ? [selected] : tours;
    const allPoints = [];
    for (const item of shown) this._collectGeoPoints(item.geojson, allPoints);

    const tracker = this._config.tracker_entity ? this._hass.states[this._config.tracker_entity] : null;
    let trackerPoint = null;
    if (tracker) {
      const lat = Number(tracker.attributes?.latitude);
      const lon = Number(tracker.attributes?.longitude);
      if (Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
        trackerPoint = [lat, lon];
        allPoints.push(trackerPoint);
      }
    }

    if (allPoints.length >= 2) {
      this._map.fitBounds(L.latLngBounds(allPoints), { padding: [24, 24] });
    } else if (allPoints.length === 1) {
      this._map.setView(allPoints[0], 12);
    } else {
      this._map.setView([51.0, 10.0], 6);
    }

    L.tileLayer(this._config.map_tiles, {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(this._map);

    for (const item of shown) {
      L.geoJSON(item.geojson, {
        style: {
          color: item.color,
          weight: Number(this._config.line_weight || 4),
          opacity: Number(this._config.line_opacity ?? 1)
        },
        onEachFeature: (_feature, layer) => {
          const road = Number(item.meta?.distance_road_km || 0);
          const distance = Number(road > 0 ? road : (item.meta?.distance_gps_km ?? item.meta?.distance_km ?? 0))
            .toLocaleString("de-DE", { maximumFractionDigits: 1 });
          layer.bindTooltip(`${this._tourName(item)} · ${distance} km ${road > 0 ? "Straße" : "GPS"}`, { sticky: true });
          layer.on("click", () => {
            this._selectedSlot = item.slot;
            this._scheduleRender();
          });
        }
      }).addTo(this._map);
    }

    if (trackerPoint) {
      const marker = L.circleMarker(trackerPoint, {
        radius: 8, color: "#fff", weight: 2, fillColor: "#000", fillOpacity: 0.9
      }).addTo(this._map);
      marker.bindTooltip(tracker.attributes?.friendly_name || "Aktuelle Position");
    }

    setTimeout(() => this._map?.invalidateSize(), 100);
  }

  _esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  _escAttr(value) { return this._esc(value).replaceAll("'", "&#39;"); }
}

if (!customElements.get("wohnmobil-tours-card")) {
  customElements.define("wohnmobil-tours-card", WohnmobilToursCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((item) => item.type === "wohnmobil-tours-card")) {
  window.customCards.push({
    type: "wohnmobil-tours-card",
    name: "Wohnmobil Tours Card",
    description: "Dynamische Wohnmobil-Tourenkarte",
    preview: true
  });
}

console.info(`WOHNMOBIL-TOURS-CARD v${WOHNMOBIL_TOURS_VERSION}`);
