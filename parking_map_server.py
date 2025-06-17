import argparse
import logging
import sys
import threading
from typing import Any, Final, Sequence

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

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
from darc.l5_data_units import ParkingDataUnit, ParkingRecord, data_unit_from_generic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FEE_UNIT_TEXT: Final[dict[str, str]] = {
    "MIN_30": "30分",
    "HOUR_1": "1時間",
    "HOUR_2": "2時間",
    "HOUR_3": "3時間",
    "HALF_DAY": "半日",
    "ONE_DAY": "1日",
    "ONCE": "1回",
    "UNKNOWN": "不明",
}

# ---------------------------------------------------------------------------
# ParkingStore implementation
# ---------------------------------------------------------------------------


class ParkingStore:
    """Thread‑safe container that deduplicates parking records by coordinates.

    Two main responsibilities:

    1. **Upsert** a record keyed by its *WGS‑84* latitude/longitude.
    2. **Serialize** the current snapshot as GeoJSON so that web clients can
       consume it directly.

    The class intentionally *does not* perform time‑series storage or
    persistence – that concern should live elsewhere (DB, TimescaleDB, etc.).
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, float, ParkingRecord]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert(self, lat: float, lon: float, record: ParkingRecord) -> None:
        """Insert or replace a record at *lat/lon*.

        A simple string key ``"P:{lat},{lon}"`` avoids floating‑point key issues
        while remaining human‑readable.
        """
        key = f"P:{lat},{lon}"
        with self._lock:
            self._data[key] = (lat, lon, record)

    # ------------------------------------------------------------------
    def to_geojson(self) -> dict[str, Any]:
        """Return the entire store as a *GeoJSON FeatureCollection*."""
        with self._lock:
            features = [
                self._to_feature(code, *tpl) for code, tpl in self._data.items()
            ]
        return {"type": "FeatureCollection", "features": features}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_feature(
        code: str, lat: float, lon: float, rec: ParkingRecord
    ) -> dict[str, Any]:
        """Convert a single :class:`ParkingRecord` to a GeoJSON *Feature*."""
        props: dict[str, Any] = {
            "name": getattr(rec.ext1, "name", None),
            "vacancy_status": rec.vacancy_status.name,
        }

        if (ext2 := getattr(rec, "ext2", None)) is not None:
            # Capacity class --------------------------------------------------
            props["capacity_class"] = ext2.capacity_class.name

            # Vacancy rate ---------------------------------------------------
            if (rate := ext2.vacancy_rate_10pct) is not None:
                props["vacancy_rate"] = f"{rate * 10}%"

            # Waiting time ---------------------------------------------------
            if (wt := ext2.waiting_time_10min) is not None:
                props["waiting_time"] = f"{wt * 10}分"
            else:
                props["waiting_time"] = "0分"  # JS hides when "0分"

            # Fee -------------------------------------------------------------
            if ext2.fee_code is None:
                props["fee_text"] = "料金不明"
            else:
                price = ext2.fee_code * 10
                unit_jp = FEE_UNIT_TEXT.get(ext2.fee_unit.name, "不明")
                props["fee_text"] = f"{price}円 / {unit_jp}"

            # Business hours --------------------------------------------------
            def _fmt(h: int | None, m10: int | None) -> str:
                return "--" if h is None or m10 is None else f"{h:02d}:{m10 * 10:02d}"

            props["hours_text"] = (
                f"{_fmt(ext2.start_hour, ext2.start_min10)} - {_fmt(ext2.end_hour, ext2.end_min10)}"
            )

        return {
            "type": "Feature",
            "id": code,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        }


# ---------------------------------------------------------------------------
# HTML (Leaflet UI)
# ---------------------------------------------------------------------------
INDEX_HTML: str = """<!DOCTYPE html>
<html lang=\"ja\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">
    <title>Parking Map</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" crossorigin>
    <style>
      html,body{height:100%;margin:0}#map{height:100%}
      .popup{font-size:.9rem;line-height:1.4}.popup h3{margin:0 0 .25rem;font-size:1.1rem}
    </style>
  </head>
  <body>
    <div id=\"map\" aria-label=\"駐車場マップ\"></div>
    <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" crossorigin defer></script>
    <script defer>
      window.addEventListener('DOMContentLoaded',()=>{
        const map=L.map('map').setView([35.681236,139.767125],11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
        let markers={};
        const colorOf=s=>({EMPTY:'green',CONGEST:'orange',FULL:'red',CLOSED:'gray'})[s]||'gray';
        const popupHtml=p=>`<div class=\"popup\"><h3>${p.name||'Parking'}</h3><div>Vacancy: ${p.vacancy_status}</div>${p.vacancy_rate?`<div>Rate: ${p.vacancy_rate}</div>`:''}${p.waiting_time&&p.waiting_time!=='0分'?`<div>Wait: ${p.waiting_time}</div>`:''}${p.capacity_class?`<div>Capacity: ${p.capacity_class}</div>`:''}${p.fee_text?`<div>Fee: ${p.fee_text}</div>`:''}${p.hours_text?`<div>Hours: ${p.hours_text}</div>`:''}</div>`;
        async function refresh(){
          try{
            const res=await fetch('/parkings');
            if(!res.ok)throw new Error(res.statusText);
            const data=await res.json();
            Object.values(markers).forEach(m=>map.removeLayer(m));
            markers={};
            data.features.forEach(f=>{
              const[lon,lat]=f.geometry.coordinates;const col=colorOf(f.properties.vacancy_status);
              const marker=L.circleMarker([lat,lon],{radius:6,color:col,weight:1,fillColor:col,fillOpacity:.9}).addTo(map).bindPopup(popupHtml(f.properties));
              markers[f.id]=marker;
            });
          }catch(e){console.error('refresh failed',e)}
        }
        refresh();setInterval(refresh,30_000);
      });
    </script>
  </body>
</html>"""

# ---------------------------------------------------------------------------
# CLI / argparse helpers
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None):
    p = argparse.ArgumentParser("DARC Parking Map Server")
    p.add_argument(
        "input_path",
        nargs="?",
        default=STDIN_MARKER,
        help="Path to DARC bit-stream or '-' for stdin",
    )
    p.add_argument("--port", type=int, default=8000, help="Web server port")
    p.add_argument(
        "-l",
        "--log-level",
        default=LogLevel.INFO.value,
        choices=[lvl.value for lvl in LogLevel],
        help="Logging level",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Decoder thread
# ---------------------------------------------------------------------------


def run_decoder(input_path: str, store: ParkingStore, stop_event: threading.Event):
    """Decode bit-stream and upsert ParkingDataUnit records into *store*."""
    pipe = DecoderPipeline()
    for bit in bits(byte_stream(input_path)):
        if stop_event.is_set():
            break
        for grp, event in pipe.push_bit(bit):
            if not grp.is_crc_valid():
                # Drop CRC
                continue

            match event:
                case Segment():
                    # Ignore Segments
                    continue
                case (header, units):
                    if not isinstance(header, PageDataHeaderB):
                        continue
                    for u in units:
                        u = data_unit_from_generic(u)
                        if not isinstance(u, ParkingDataUnit):
                            continue
                        for rec in u.records:
                            lat_t, lon_t = arib_to_tokyo_deg(
                                header.map_position_x,
                                header.map_position_y,
                                rec.center_x,
                                rec.center_y,
                            )
                            lat_w, lon_w = tokyo_to_wgs84(lat_t, lon_t)
                            store.upsert(lat_w, lon_w, rec)


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def build_app(store: ParkingStore) -> FastAPI:
    app = FastAPI(title="Parking Map Server")

    @app.get("/", response_class=HTMLResponse)
    async def index(_: Request):  # noqa: D401
        return HTMLResponse(INDEX_HTML)

    @app.get("/parkings")
    async def parkings():  # noqa: D401
        return JSONResponse(store.to_geojson())

    return app


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(LogLevel(args.log_level))

    store = ParkingStore()
    stop_event = threading.Event()

    decoder_thr = threading.Thread(
        target=run_decoder,
        args=(args.input_path, store, stop_event),
        daemon=True,
    )
    decoder_thr.start()

    logging.info("Web map 👉 http://localhost:%d", args.port)

    try:
        uvicorn.run(build_app(store), host="0.0.0.0", port=args.port, log_level="info")
    except KeyboardInterrupt:
        stop_event.set()
        decoder_thr.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
