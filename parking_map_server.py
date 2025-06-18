import argparse
import logging
import sys
import threading
from typing import Sequence

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse

# --- shared core -----------------------------------------------------------
from decoder_core import (
    DecoderPipeline,
    LogLevel,
    STDIN_MARKER,
    bits,
    byte_stream,
    setup_logging,
)

# --- domain-specific helpers ----------------------------------------------
from darc.arib_b3_position import arib_to_tokyo_deg, tokyo_to_wgs84
from darc.l5_data import PageDataHeaderB, Segment
from darc.l5_data_units import ParkingDataUnit, data_unit_from_generic

from parking_store import ParkingStore


# ---------------------------------------------------------------------------
# HTML (Leaflet UI)
# ---------------------------------------------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>駐車場マップ</title>

    <!-- Fonts -->
    <link
      href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&display=swap"
      rel="stylesheet"
    />

    <!-- Leaflet CSS -->
    <link
      rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      crossorigin
    />

    <style>
      /* Tokens */
      :root {
        --bg: #ffffff;
        --fg: #222222;
        --panel-bg: rgba(255, 255, 255, 0.9);
        --panel-border: #cccccc;
        --accent: #0078ff;
        --vac-empty: #28a745;
        --vac-congest: #fd7e14;
        --vac-full: #dc3545;
        --vac-closed: #6c757d;
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --bg: #1e1e1e;
          --fg: #e0e0e0;
          --panel-bg: rgba(30, 30, 30, 0.9);
          --panel-border: #444;
          --accent: #479cff;
        }
      }

      html,
      body {
        height: 100%;
        margin: 0;
        font-family: "Noto Sans JP", system-ui, sans-serif;
        background: var(--bg);
        color: var(--fg);
      }
      #map {
        height: 100%;
      }

      /* Popup */
      .popup {
        font-size: 0.9rem;
        line-height: 1.4;
      }
      .popup h3 {
        margin: 0 0 0.25rem;
        font-size: 1.05rem;
        font-weight: 700;
      }
      .row {
        display: flex;
        justify-content: space-between;
        gap: 0.5rem;
        white-space: nowrap;
      }
      .row span:first-child {
        color: #666;
      }

      /* Common controls */
      .L-control-panel {
        background: var(--panel-bg);
        border: 1px solid var(--panel-border);
        border-radius: 0.5rem;
        padding: 0.6rem 0.8rem;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
        font-size: 0.8rem;
      }

      /* Legend */
      .legend-item {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-bottom: 0.25rem;
      }
      .legend-swatch {
        width: 0.9rem;
        height: 0.9rem;
        border-radius: 50%;
      }

      /* Refresh button */
      button.L-control-panel {
        background: var(--accent);
        color: #fff;
        border: none;
        cursor: pointer;
      }
      button.L-control-panel:hover {
        opacity: 0.85;
      }
    </style>
  </head>
  <body>
    <div id="map" aria-label="駐車場マップ"></div>

    <!-- Leaflet JS -->
    <script
      src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
      crossorigin
      defer
    ></script>

    <script defer>
      // Color constants (CSS tokens)
      const CSSColor = (name) =>
        getComputedStyle(document.documentElement).getPropertyValue(name);
      const COLORS = {
        EMPTY: CSSColor("--vac-empty"),
        CONGEST: CSSColor("--vac-congest"),
        FULL: CSSColor("--vac-full"),
        CLOSED: CSSColor("--vac-closed"),
      };

      // Japanese labels
      const formatRow = (label, value) =>
        value
          ? `<div class="row"><span>${label}</span><span>${value}</span></div>`
          : "";

      window.addEventListener("DOMContentLoaded", () => {
        // Map initialization
        const map = L.map("map", { attributionControl: false }).setView(
          [35.681236, 139.767125],
          11
        );
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);

        // Legend control
        const legend = L.control({ position: "bottomright" });
        legend.onAdd = () => {
          const div = L.DomUtil.create("div", "L-control-panel");
          div.innerHTML = `
            <strong>空車状況</strong>
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.EMPTY}"></span>空車</div>
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.CONGEST}"></span>混雑</div>
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.FULL}"></span>満車</div>
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.CLOSED}"></span>閉鎖</div>
            <div class="legend-item"><span class="legend-swatch" style="background:#ffffff"></span>不明</div>
          `;
          return div;
        };
        legend.addTo(map);

        // Timestamp control
        const tsCtrl = L.control({ position: "topright" });
        tsCtrl.onAdd = () => {
          const div = L.DomUtil.create("div", "L-control-panel");
          div.id = "timestamp";
          div.textContent = "--";
          return div;
        };
        tsCtrl.addTo(map);

        // Manual refresh button
        const refreshBtn = L.control({ position: "topleft" });
        refreshBtn.onAdd = () => {
          const btn = L.DomUtil.create("button", "L-control-panel");
          btn.textContent = "↻ 更新";
          btn.onclick = refreshAll;
          return btn;
        };
        refreshBtn.addTo(map);

        // Parking layer
        let parkingMarkers = {};
        const colorVac = (prop) => prop.vacancy_color || COLORS.CLOSED;

        const popParking = (p) => `
          <div class="popup">
            <h3>${p.name || "駐車場"}</h3>
            ${formatRow("満空", p.vacancy_status_jp)}
            ${formatRow("満車率", p.vacancy_rate)}
            ${formatRow(
              "待ち時間",
              p.waiting_time && p.waiting_time !== "0分" ? p.waiting_time : ""
            )}
            ${formatRow("収容台数", p.capacity_class)}
            ${formatRow("料金", p.fee_text)}
            ${formatRow("営業時間", p.hours_text)}
            ${formatRow("入口までの距離", p.entrance_distance)}
            ${formatRow("面する道路", p.road_link)}
            ${formatRow("高さ制限", p.height_limit)}
            ${formatRow("車種制限", p.vehicle_limit)}
            ${formatRow("割引条件", p.discount)}
          </div>
        `;

        async function refreshParking() {
          try {
            const res = await fetch("/parkings");
            if (!res.ok) throw new Error(res.statusText);
            const geojson = await res.json();

            // Remove existing markers
            Object.values(parkingMarkers).forEach((m) => map.removeLayer(m));
            parkingMarkers = {};

            // Add new markers
            geojson.features.forEach((f) => {
              const [lon, lat] = f.geometry.coordinates;
              const props = f.properties;
              const m = L.circleMarker([lat, lon], {
                radius: 6,
                color: colorVac(props),
                weight: 1,
                fillColor: colorVac(props),
                fillOpacity: 0.9,
              })
                .addTo(map)
                .bindPopup(popParking(props));
              parkingMarkers[f.id] = m;
            });

            updateTimestamp();
          } catch (err) {
            console.error("parking", err);
          }
        }

        const updateTimestamp = () => {
          const el = document.getElementById("timestamp");
          if (el)
            el.textContent = new Date().toLocaleTimeString("ja-JP", {
              hour12: false,
            });
        };

        async function refreshAll() {
          await refreshParking();
        }

        refreshAll();
        setInterval(refreshAll, 30_000);
      });
    </script>
  </body>
</html>"""

# ---------------------------------------------------------------------------
# CLI / argparse helpers
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None):
    p = argparse.ArgumentParser("DARC Parking & Regulation Map Server")
    p.add_argument(
        "input_path",
        nargs="?",
        default=STDIN_MARKER,
        help="Path to DARC bit-stream or '-' for stdin",
    )
    p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8000, help="Web server port")
    p.add_argument(
        "--cors",
        nargs="*",
        default=["*"],
        help="Allowed CORS origins (default: '*')",
    )
    p.add_argument(
        "-l",
        "--log-level",
        default=LogLevel.INFO.value,
        choices=[lvl.value for lvl in LogLevel],
        help="Logging level",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Decoder thread - pushes records into ParkingStore
# ---------------------------------------------------------------------------


def run_decoder(
    input_path: str,
    park_store: ParkingStore,
    stop_event: threading.Event,
):
    """Decode bit-stream and upsert Parking records into the store."""
    pipe = DecoderPipeline()
    for bit in bits(byte_stream(input_path)):
        if stop_event.is_set():
            break
        for grp, event in pipe.push_bit(bit):
            if not grp.is_crc_valid():
                continue  # Drop CRC errors
            match event:
                case Segment():
                    continue  # Ignore segments
                case (header, units):
                    if not isinstance(header, PageDataHeaderB):
                        continue
                    for u in units:
                        u = data_unit_from_generic(u)
                        if isinstance(u, ParkingDataUnit):
                            for rec in u.records:
                                lat_t, lon_t = arib_to_tokyo_deg(
                                    header.map_position_x,
                                    header.map_position_y,
                                    rec.center_x,
                                    rec.center_y,
                                )
                                lat_w, lon_w = tokyo_to_wgs84(lat_t, lon_t)
                                park_store.upsert(lat_w, lon_w, rec)


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def build_app(park_store: ParkingStore, allowed_origins: list[str]) -> FastAPI:
    app = FastAPI(
        title="Parking Map Server", default_response_class=ORJSONResponse
    )

    # CORS ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Routes ----------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def index(_: Request):
        return HTMLResponse(INDEX_HTML)

    @app.get("/parkings", response_class=Response)
    async def parkings():
        """Return all parking data as GeoJSON (bytes, UTF-8)."""
        return Response(
            park_store.to_geojson_bytes(),
            media_type="application/json",
        )

    return app


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(LogLevel(args.log_level))

    park_store = ParkingStore()
    stop_event = threading.Event()

    decoder_thr = threading.Thread(
        target=run_decoder,
        args=(args.input_path, park_store, stop_event),
        daemon=True,
    )
    decoder_thr.start()

    logging.info("Web map 👉 http://%s:%d", args.host, args.port)

    try:
        uvicorn.run(
            build_app(park_store, args.cors),
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except KeyboardInterrupt:
        stop_event.set()
        decoder_thr.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
