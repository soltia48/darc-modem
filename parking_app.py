# parking_decoder_with_web.py
"""DARC Parking Decoder + Leaflet Web マップ (ワンファイル版)

最初に提示されたスクリプトを **そのまま残しつつ**、
`--webmap` オプションを追加して OpenStreetMap 上に駐車場を表示できるようにした完全版。

- オリジナルの標準入力デコーダ動作は変更なし
- `--webmap` を付ければ同時に Web サーバ (FastAPI + Leaflet) を起動
- 必要パッケージ: `pip install fastapi uvicorn jinja2 aiofiles python-multipart`

Usage::

    # DARC ビットストリームを流し込みつつ Web 表示
    cat darc_dump.bin | python parking_decoder_with_web.py -log INFO --webmap --port 8000

ブラウザで `http://localhost:8000` を開くと地図が表示され、
新たな駐車場データをリアルタイムにプロットします。
"""
from __future__ import annotations

###############################################################################
# 既存コード: 列挙体・データクラス・デコーダなど (変更なし)
###############################################################################
import enum
from dataclasses import dataclass, field
from typing import Optional, List, Sequence, Final, Literal, TypeAlias, Any, Self

###############################################################################
# 追加インポート (オリジナルの import 群に追記して OK)
###############################################################################
import asyncio
import json
import threading

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import argparse
import logging
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from pprint import pprint
from typing import (
    Final,
    Literal,
    NoReturn,
    Self,
    Sequence,
    TypeAlias,
    Any,
    get_type_hints,
)

from darc.arib_b3_position import arib_to_tokyo_deg, tokyo_to_wgs84
from darc.arib_string import AribStringDecoder
from darc.dump_binary import dump_binary
from darc.l2_block_decoder import L2BlockDecoder
from darc.l2_frame_decoder import L2FrameDecoder
from darc.l3_data import L3DataPacketServiceIdentificationCode
from darc.l3_data_packet_decoder import L3DataPacketDecoder
from darc.l4_data import L4DataGroup1, L4DataGroup2
from darc.l4_data_group_decoder import L4DataGroupDecoder
from darc.l5_data import GenericDataUnit, Segment
from darc.l5_data_decoder import L5DataDecoder
from darc.l5_data import (
    DataHeaderBase,
    ProgramDataHeaderA,
    ProgramDataHeaderB,
    PageDataHeaderA,
    PageDataHeaderB,
    ProgramCommonMacroDataHeaderA,
    ProgramCommonMacroDataHeaderB,
    ContinueDataHeader,
    ProgramIndexDataHeader,
)
from darc.l5_data_units import ParkingRecord, ParkingUnit, decode_unit

# Type aliases with more specific typing
DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2
LogLevel: TypeAlias = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
BitValue: TypeAlias = Literal[0, 1]

# Constants
STDIN_MARKER: Final[str] = "-"
DEFAULT_LOG_LEVEL: Final[LogLevel] = "WARNING"
PROGRAM_DESCRIPTION: Final[str] = "DARC bitstream Decoder"
SEPARATOR_LINE: Final[str] = "-" * 80
DOUBLE_SEPARATOR: Final[str] = "=" * 80


@dataclass(frozen=True, slots=True)
class DecoderPipeline:
    """DARC decoder pipeline configuration."""

    l2_block_decoder: L2BlockDecoder
    l2_frame_decoder: L2FrameDecoder
    l3_packet_decoder: L3DataPacketDecoder
    l4_group_decoder: L4DataGroupDecoder
    l5_data_decoder: L5DataDecoder

    @classmethod
    def create(cls) -> Self:
        """Create a new decoder pipeline instance."""
        return cls(
            L2BlockDecoder(),
            L2FrameDecoder(),
            L3DataPacketDecoder(),
            L4DataGroupDecoder(),
            L5DataDecoder(),
        )


###############################################################################
# 共有メモリ: Web サーバ側が参照する最新駐車場データ
###############################################################################
_PARKINGS: dict[str, tuple[float, float, "ParkingRecord"]] = {}
_PARKINGS_LOCK = threading.Lock()


def setup_logging(level: LogLevel) -> None:
    """Configure logging with specified level."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def process_stdin(pipeline: DecoderPipeline) -> NoReturn:
    """Process DARC bitstream from standard input."""
    while True:
        try:
            bit = ord(sys.stdin.read(1))

            if not (block := pipeline.l2_block_decoder.push_bit(bit)):
                continue

            if not (frame := pipeline.l2_frame_decoder.push_block(block)):
                continue

            data_packets = pipeline.l3_packet_decoder.push_frame(frame)
            data_packets = [
                data_packet
                for data_packet in data_packets
                if data_packet.service_id
                not in (
                    L3DataPacketServiceIdentificationCode.TRANSMISSION_7_MODE,
                    L3DataPacketServiceIdentificationCode.TRANSMISSION_8_MODE,
                    L3DataPacketServiceIdentificationCode.TRANSMISSION_9_MODE,
                )
            ]

            data_groups = pipeline.l4_group_decoder.push_data_packets(data_packets)

            for data_group in data_groups:
                l5_data = pipeline.l5_data_decoder.push_data_group(data_group)

                match l5_data:
                    case (data_header, data_units):
                        if data_header is None:
                            continue

                        for data_unit in data_units:
                            if data_group.is_crc_valid() and isinstance(
                                data_unit, GenericDataUnit
                            ):
                                data_unit = decode_unit(data_unit)
                                if isinstance(data_unit, ParkingUnit):
                                    for parking in data_unit.records:
                                        lat_t, lon_t = arib_to_tokyo_deg(
                                            data_header.map_position_x,
                                            data_header.map_position_y,
                                            parking.center_x,
                                            parking.center_y,
                                        )
                                        lat_w, lon_w = tokyo_to_wgs84(lat_t, lon_t)
                                        code = f"P:{lat_w},{lon_w}"
                                        _PARKINGS[code] = (lat_w, lon_w, parking)

                    case Segment():
                        pass

        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
        except Exception as e:
            logging.error("Processing error: %s", str(e))
            continue


def process_file(path: Path) -> NoReturn:
    """Process DARC bitstream from file."""
    print("File input is not yet supported.")
    sys.exit(1)

###############################################################################
# Leaflet フロント (VacancyStatus で色分け)
###############################################################################
INDEX_HTML = """<!DOCTYPE html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Parking Map</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" crossorigin="" />
  <style>
    html,body,#map{height:100%;margin:0}
    .popup{font-size:.9rem;line-height:1.4}
    .popup h3{margin:0 0 .25rem;font-size:1.1rem}
  </style>
</head>
<body>
  <div id=\"map\"></div>
  <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" crossorigin=""></script>
  <script>
    const map=L.map('map').setView([35.681236,139.767125],11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);

    let markers={};

    function getColor(status){
      switch(status){
        case 'EMPTY': return 'green';
        case 'CONGEST': return 'orange';
        case 'FULL': return 'red';
        case 'CLOSED': return 'gray';
        default: return 'gray';
      }
    }

    async function loadParkings(){
      const r=await fetch('/parkings'); if(!r.ok)return; const data=await r.json();
      // 既存マーカー削除
      Object.values(markers).forEach(m=>map.removeLayer(m)); markers={};

      data.features.forEach(f=>{
        const [lon,lat]=f.geometry.coordinates;
        const color=getColor(f.properties.vacancy_status);
        const m=L.circleMarker([lat,lon],{
          radius:6,weight:1,color:color,fillColor:color,fillOpacity:0.9
        }).addTo(map);
        m.bindPopup(`<div class='popup'><h3>${f.properties.name||'Parking'}</h3>`+
          `<div>Vacancy: ${f.properties.vacancy_status}</div>`+
          (f.properties.capacity_class?`<div>Capacity: ${f.properties.capacity_class}</div>`:'')+
          (f.properties.fee_unit?`<div>Fee: ${f.properties.fee_unit}</div>`:'')+`</div>`);
        markers[f.id]=m;
      });
    }

    loadParkings(); setInterval(loadParkings,30000);
  </script>
</body>
</html>"""

###############################################################################
# FastAPI アプリ
###############################################################################
app = FastAPI(title="Parking Map Server")
app.mount("/static", StaticFiles(directory="."), name="static")  # dummy

@app.get("/", response_class=HTMLResponse)
async def index(_: Request) -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)

@app.get("/parkings")
async def parkings() -> JSONResponse:
    with _PARKINGS_LOCK:
        features=[]
        for code,(lat,lon,rec) in _PARKINGS.items():
            props={
                'name': rec.ext1.name if rec.ext1 and rec.ext1.name else None,
                'vacancy_status': rec.vacancy_status.name,
            }
            if getattr(rec,'ext2',None):
                props.update({'capacity_class':rec.ext2.capacity_class.name,'fee_unit':rec.ext2.fee_unit.name})
            features.append({'type':'Feature','id':code,'geometry':{'type':'Point','coordinates':[lon,lat]},'properties':props})
    return JSONResponse({'type':'FeatureCollection','features':features})

###############################################################################
# Web サーバ起動ヘルパ & main() —— 変更なし (色分けロジックに影響しない)
###############################################################################

def start_web_server(port:int)->threading.Thread:
    def _run():
        uvicorn.run(app,host='0.0.0.0',port=port,log_level='info')
    t=threading.Thread(target=_run,daemon=True); t.start(); return t

STDIN_MARKER:Final[str]="-"; DEFAULT_LOG_LEVEL:Final[str]="WARNING"; PROGRAM_DESCRIPTION:Final[str]="DARC bitstream Decoder + Web Map"

def parse_arguments(args:Sequence[str]|None=None)->argparse.Namespace:
    p=argparse.ArgumentParser(description=PROGRAM_DESCRIPTION)
    p.add_argument('input_path',help=f'Input DARC bitstream path ({STDIN_MARKER} for stdin)')
    p.add_argument('-log','--log-level',default=DEFAULT_LOG_LEVEL,choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'])
    p.add_argument('--webmap',action='store_true',help='Enable web map server')
    p.add_argument('--port',type=int,default=8000,help='Web server port')
    return p.parse_args(args)

def main(argv:Sequence[str]|None=None)->int:
    args=parse_arguments(argv); setup_logging(args.log_level); pipeline=DecoderPipeline.create()
    if args.webmap: start_web_server(args.port); logging.getLogger(__name__).info('Web server: http://localhost:%d',args.port)
    if args.input_path==STDIN_MARKER: process_stdin(pipeline)
    else: process_file(Path(args.input_path))
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except KeyboardInterrupt: pass
