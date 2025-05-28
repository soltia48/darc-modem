# -*- coding: utf-8 -*-
"""arib_std_b3_decoders.py – traffic-information decoders for ARIB STD-B3

Hot-fix-4 ▸ 2025-05-27  (focus: **0x40 full-field decode**)
========================================================
* `CongestionTravelTimeUnit`
  * 新たに `ProvideForm` 列挙体を導入し、`provide_form` を型付け。
  * `info_count_flag` を **bool** に。`True` の場合は 1 データで
    *continuous_links* 個を代表する仕様に従い、リンク情報を複製。
  * `LinkInfo` に `ext_flag` を追加（0 = 無拡張, 1 = Ext-1, 2 = Ext-1+2, 3 = 予約／無効）。
  * `provide_form == 1`（旅行時間無しフォーマット）をデコード：
    * 1 バイトの構成は `ext_flag(2b) + congestion(2b)` とし、拡張が付く場合は
      **必ず Ext-1**（距離・渋滞長）あるいは **Ext-1+2**（距離・渋滞長 + 拡張旅行時間）
      が続く。
  * 予約値 62,63 は `ext_flag = 3` として扱い `travel_time_code = None`。

他ユニット（0x41–0x43, Parking）は Hot-fix-3 のままです。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, Type
from logging import getLogger

from bitstring import ConstBitStream

from darc.arib_string import AribDecoder


# ───────────────────────────── 共通ヘルパ ──────────────────────────────
class BitReader(ConstBitStream):
    """`bitstring.ConstBitStream` ラッパ。`read_uint(n)` で n bit Unsigned。"""

    def read_uint(self, length: int) -> int:
        try:
            return self.read(f"uint:{length}")
        except Exception as exc:
            raise ValueError("data-unit ends prematurely") from exc


# ───────────────────────────── レジストリ ───────────────────────────────
_decoder_registry: Dict[int, Type["GenericDataUnit"]] = {}


def register(parameter: int):
    def deco(cls: Type["GenericDataUnit"]):
        _decoder_registry[parameter] = cls
        return cls

    return deco


def decode_unit(unit: "GenericDataUnit") -> "GenericDataUnit":
    cls = _decoder_registry.get(unit.data_unit_parameter)
    return cls.from_unit(unit) if cls else unit


# -----------------------------------------------------------------------
@dataclass
class GenericDataUnit:  # type: ignore – shadow
    data_unit_parameter: int
    data_unit_link_flag: int
    data_unit_data: bytes

    _logger: ClassVar = getLogger(__name__)

    @classmethod
    def from_unit(cls, unit: "GenericDataUnit") -> "GenericDataUnit":
        return unit


# ───────────────────────────── 列挙体共通 ──────────────────────────────
class CongestionDegree(enum.IntEnum):
    UNKNOWN = 0
    FREE = 1
    SLOW = 2
    JAM = 3


class DistanceUnit(enum.IntEnum):
    TEN_M = 0
    HUNDRED_M = 1
    ONE_KM = 2
    UNDEFINED = 3


class TimeUnit(enum.IntEnum):
    SEC_10 = 0
    MINUTE = 1


# ====================== 0x40 Congestion / Travel-time =====================
class ProvideForm(enum.IntEnum):
    TRAVEL_TIME_INCLUDED = 0  # 提形0
    CONGESTION_ONLY = 1  # 提形1


# — per-link extension flag (b5,b4 or code group) —
class LinkExtFlag(enum.IntEnum):
    NONE = 0  # 基本情報のみ
    EXT1 = 1  # 基本+拡張1
    EXT1_EXT2 = 2  # 基本+拡張1+2
    RESERVED = 3  # 消失/情報集約/無効


@dataclass
class Ext1:  # 距離・渋滞長
    distance_unit: DistanceUnit
    leading_position: int  # 0–126 ⇒ 距離 = value × unit
    jam_length: int  # 0–126 ⇒ 0:リンク長さ, 127:不明


@dataclass
class Ext2:  # 拡張リンク旅行時間
    time_unit: TimeUnit
    travel_time_code: int  # 1–125 valid, 0 unknown

    @property
    def seconds(self) -> Optional[int]:
        if self.travel_time_code == 0:
            return None
        return self.travel_time_code * (10 if self.time_unit == TimeUnit.SEC_10 else 60)


@dataclass
class LinkInfo:
    congestion: CongestionDegree
    ext_flag: LinkExtFlag
    travel_time_code: Optional[int]
    travel_time_seconds: Optional[int]
    ext1: Optional[Ext1] = None
    ext2: Optional[Ext2] = None


@register(0x40)
@dataclass
class CongestionTravelTimeUnit(GenericDataUnit):
    provide_form: ProvideForm = field(init=False)
    time_type: int = field(init=False)
    info_count_flag: bool = field(init=False)  # True ⇒ 1データ代表
    mode_flag: int = field(init=False)
    continuous_links: int = field(init=False)
    link_type: int = field(init=False)
    first_link_no: int = field(init=False)

    links: List[LinkInfo] = field(default_factory=list, repr=False, init=False)
    raw_tail: bytes = field(default=b"", init=False)

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "CongestionTravelTimeUnit":
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )
        br = BitReader(self.data_unit_data)
        self.provide_form = ProvideForm(br.read_uint(1))
        self.time_type = br.read_uint(1)
        self.info_count_flag = bool(br.read_uint(1))
        self.mode_flag = br.read_uint(1)
        self.continuous_links = br.read_uint(12)
        self.link_type = br.read_uint(2)
        self.first_link_no = br.read_uint(12)

        if self.provide_form == ProvideForm.TRAVEL_TIME_INCLUDED:
            self._decode_form0(br)
        else:
            self._decode_form1(br)
        return self

    # ------------------------------------------------------------------
    def _decode_form0(self, br: BitReader) -> None:
        """Provide-form 0: congestion + travel-time."""
        first_link_info: Optional[LinkInfo] = None
        for link_idx in range(self.continuous_links):
            if br.pos + 8 > br.length:
                break
            byte = br.read_uint(8)
            congestion = CongestionDegree((byte >> 6) & 0x03)
            code = byte & 0x3F  # 6 bits
            ext_flag: LinkExtFlag
            t_code: Optional[int] = None
            t_sec: Optional[int] = None
            ext1 = ext2 = None

            if code <= 59:
                ext_flag = LinkExtFlag.NONE
                t_code = code
                t_sec = None if code == 0 else code * 10
            elif code in (60, 61):
                ext_flag = LinkExtFlag.EXT1 if code == 60 else LinkExtFlag.EXT1_EXT2
                # Ext-1 (2 byte)
                if br.pos + 16 > br.length:
                    break
                e1b0 = br.read_uint(8)
                e1b1 = br.read_uint(8)
                ext1 = Ext1(
                    DistanceUnit((e1b0 >> 6) & 0x03),
                    ((e1b0 & 0x3F) << 1) | (e1b1 >> 7),
                    e1b1 & 0x7F,
                )
                if code == 61 and br.pos + 8 <= br.length:
                    e2 = br.read_uint(8)
                    ext2 = Ext2(TimeUnit((e2 >> 7) & 0x01), e2 & 0x7F)
                    t_sec = ext2.seconds
            else:  # 62, 63
                ext_flag = LinkExtFlag.RESERVED

            link_info = LinkInfo(congestion, ext_flag, t_code, t_sec, ext1, ext2)
            self.links.append(link_info)
            if self.info_count_flag and first_link_info is None:
                first_link_info = link_info
                # replicate later

        # 情報数フラグが1なら、最初の情報を残りリンク数分コピー
        if self.info_count_flag and first_link_info:
            missing = self.continuous_links - len(self.links)
            if missing > 0:
                self.links.extend([first_link_info] * missing)

        if br.pos < br.length:
            self.raw_tail = br.read(br.length - br.pos).bytes

    # ------------------------------------------------------------------
    def _decode_form1(self, br: BitReader) -> None:
        """Provide-form 1: congestion only (no travel-time)."""
        first_link_info: Optional[LinkInfo] = None
        for link_idx in range(self.continuous_links):
            if br.pos + 8 > br.length:
                break
            byte = br.read_uint(8)
            ext_flag = LinkExtFlag((byte >> 4) & 0x03)
            congestion = CongestionDegree((byte >> 2) & 0x03)
            ext1 = ext2 = None
            if ext_flag in (LinkExtFlag.EXT1, LinkExtFlag.EXT1_EXT2):
                if br.pos + 16 > br.length:
                    break
                e1b0 = br.read_uint(8)
                e1b1 = br.read_uint(8)
                ext1 = Ext1(
                    DistanceUnit((e1b0 >> 6) & 0x03),
                    ((e1b0 & 0x3F) << 1) | (e1b1 >> 7),
                    e1b1 & 0x7F,
                )
                if ext_flag == LinkExtFlag.EXT1_EXT2 and br.pos + 8 <= br.length:
                    e2 = br.read_uint(8)
                    ext2 = Ext2(TimeUnit((e2 >> 7) & 0x01), e2 & 0x7F)
            link_info = LinkInfo(congestion, ext_flag, None, None, ext1, ext2)
            self.links.append(link_info)
            if self.info_count_flag and first_link_info is None:
                first_link_info = link_info

        if self.info_count_flag and first_link_info:
            missing = self.continuous_links - len(self.links)
            if missing > 0:
                self.links.extend([first_link_info] * missing)

        if br.pos < br.length:
            self.raw_tail = br.read(br.length - br.pos).bytes


# ======================== 0x41 Restriction / Accident =====================
class ExtFlag(enum.IntEnum):
    BASIC = 0  # 基本構成のみ
    BASIC_EXT1 = 1  # +拡張構成1
    BASIC_EXT1_EXT2 = 2  # +拡張構成1+2
    MODE = 3  # モード識別 (将来拡張 / 無効)


# ----- 拡張1 ----------------------------------------------------------------
@dataclass
class Ext1R:
    restriction_detail_code: int  # 8 bit (表3.1.2‑9)
    cause_detail_code: int  # 8 bit (表3.1.2‑10)
    distance_unit: DistanceUnit  # 2 bit
    distance_value: int  # 7 bit (0‑126) 127=不明
    reserved: int  # 8 bit (PBm+4 全体)


# ----- 拡張2 (期間情報) ------------------------------------------------------
@dataclass
class Ext2R:
    start_month: Optional[int]
    end_month: Optional[int]
    start_day: Optional[int]
    start_hour: Optional[int]
    start_min: Optional[int]
    end_day: Optional[int]
    end_hour: Optional[int]
    end_min: Optional[int]

    @staticmethod
    def _clean(val: int, undef_values) -> Optional[int]:
        return None if val in undef_values else val

    @classmethod
    def parse(cls, br: BitReader) -> "Ext2R":
        if br.pos + 40 > br.length:
            raise ValueError("insufficient bits for Ext2R")
        b0 = br.read_uint(8)
        start_month = (b0 >> 4) & 0x0F
        end_month = b0 & 0x0F

        b1 = br.read_uint(8)
        start_day = (b1 >> 3) & 0x1F
        _sh_hi = b1 & 0x07  # 時3bit上位

        b2 = br.read_uint(8)
        _sh_lo = (b2 >> 6) & 0x03  # 時2bit下位
        start_hour = (_sh_hi << 2) | _sh_lo  # 0‑23
        start_min = b2 & 0x3F  # 0‑59 / 60‑62 未定義,63 不明

        b3 = br.read_uint(8)
        end_day = (b3 >> 3) & 0x1F
        _eh_hi = b3 & 0x07

        b4 = br.read_uint(8)
        _eh_lo = (b4 >> 6) & 0x03
        end_hour = (_eh_hi << 2) | _eh_lo
        end_min = b4 & 0x3F

        # 正規化 (未定義→None)
        clean = cls._clean
        return cls(
            clean(start_month, {0}),
            clean(end_month, {0}),
            clean(start_day, {0}),
            clean(start_hour, {24, 31}),
            clean(start_min, {60, 61, 62, 63}),
            clean(end_day, {0}),
            clean(end_hour, {24, 31}),
            clean(end_min, {60, 61, 62, 63}),
        )


# ---------------------------------------------------------------------------
@register(0x41)
@dataclass
class RestrictionAccidentUnit(GenericDataUnit):
    ext_flag: ExtFlag = field(init=False)
    link_count: int = field(init=False)
    cause_code: int = field(init=False)  # 4 bit 表3.1.2‑3
    restriction_code: int = field(init=False)  # 4 bit 表3.1.2‑4
    distance_unit: DistanceUnit = field(init=False)
    restriction_length: int = field(init=False)

    ext1: Optional[Ext1R] = field(default=None, init=False)
    ext2: Optional[Ext2R] = field(default=None, init=False)
    raw_links_block: bytes = field(default=b"", init=False)

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "RestrictionAccidentUnit":
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )
        br = BitReader(self.data_unit_data)

        # ─ PB L1 ────────────────────────────────────────────────
        b1 = br.read_uint(8)
        self.ext_flag = ExtFlag((b1 >> 6) & 0x03)
        self.link_count = b1 & 0x3F

        # ─ PB L2 ────────────────────────────────────────────────
        b2 = br.read_uint(8)
        self.cause_code = (b2 >> 4) & 0x0F
        self.restriction_code = b2 & 0x0F

        # ─ PB L3 ────────────────────────────────────────────────
        b3 = br.read_uint(8)
        self.distance_unit = DistanceUnit((b3 >> 6) & 0x03)
        self.restriction_length = b3 & 0x3F

        # ----- 拡張1 ---------------------------------------------------
        if self.ext_flag in (ExtFlag.BASIC_EXT1, ExtFlag.BASIC_EXT1_EXT2):
            if br.pos + 24 > br.length:
                raise ValueError("insufficient bits for Ext1R")
            r_detail = br.read_uint(8)
            c_detail = br.read_uint(8)
            dist_byte = br.read_uint(8)
            dist_val = dist_byte & 0x7F
            # 単位は次の byte 上位2bit
            unit_byte = br.read_uint(8)
            dist_unit = DistanceUnit((unit_byte >> 6) & 0x03)
            reserved = unit_byte & 0x3F
            reserved2 = br.read_uint(8)  # PBm+4 (仕様では未定義領域)
            self.ext1 = Ext1R(r_detail, c_detail, dist_unit, dist_val, reserved2)

        # ----- 拡張2 ---------------------------------------------------
        if self.ext_flag == ExtFlag.BASIC_EXT1_EXT2:
            self.ext2 = Ext2R.parse(br)

        # ----- リンク列ブロック ---------------------------------------
        if br.pos < br.length:
            self.raw_links_block = br.read(br.length - br.pos).bytes
        return self


# ────────────────────────── 0x42 Parking Unit ──────────────────────────
class ParkingExtFlag(enum.IntEnum):
    BASIC = 0
    BASIC_EXT1 = 1
    BASIC_EXT1_EXT2 = 2
    MODE = 3


class VacancyStatus(enum.IntEnum):
    EMPTY = 0
    CONGEST = 1
    FULL = 2
    CLOSED = 3
    UNDEF1 = 4
    UNDEF2 = 5
    UNDEF3 = 6
    UNKNOWN = 7


class DistanceUnitP(enum.IntEnum):
    TEN_M = 0
    HUNDRED_M = 1


@dataclass
class Ext1P:
    mesh_flag: bool
    name_flag: bool
    link_type: int
    link_number: int
    distance_unit: DistanceUnitP
    entrance_distance: int
    entrance_x: int
    entrance_y: int
    name: Optional[str]


@dataclass
class Ext2P:
    vacancy_rate_10pct: int
    waiting_time_10min: int
    capacity_class: int
    height_limit: int
    vehicle_limit: int
    discount_condition: int
    fee_unit: int
    fee_code: int
    start_hour: Optional[int]
    start_min10: Optional[int]
    end_hour: Optional[int]
    end_min10: Optional[int]


@dataclass
class ParkingRecord:
    ext1: Ext1P
    ext2: Optional[Ext2P]


@register(0x42)
@dataclass
class ParkingUnit(GenericDataUnit):
    ext_flag: ParkingExtFlag = field(init=False)
    vacancy_status: VacancyStatus = field(init=False)
    is_general: bool = field(init=False)
    center_x: int = field(init=False)
    center_y: int = field(init=False)
    records: List[ParkingRecord] = field(default_factory=list, init=False)
    raw_rest: bytes = field(default=b"", init=False)

    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "ParkingUnit":
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )
        br = BitReader(self.data_unit_data)

        # PB L1: ext_flag, vacancy_status, is_general
        b1 = br.read_uint(8)
        self.ext_flag = ParkingExtFlag((b1 >> 6) & 0x03)
        self.vacancy_status = VacancyStatus((b1 >> 3) & 0x07)
        self.is_general = bool((b1 >> 2) & 0x01)
        # PB L2-L3: center coords
        self.center_x = br.read_uint(16)
        self.center_y = br.read_uint(16)
        self.records = []

        # Repeated parsing of Ext-1 and Ext-2 blocks
        while br.pos < br.length:
            # Ext-1
            if self.ext_flag not in (
                ParkingExtFlag.BASIC_EXT1,
                ParkingExtFlag.BASIC_EXT1_EXT2,
            ):
                break
            if br.pos + 40 > br.length:
                break
            e1b0 = br.read_uint(8)
            mesh_flag = bool((e1b0 >> 7) & 1)
            name_flag = bool((e1b0 >> 6) & 1)
            link_type = (e1b0 >> 4) & 0x03
            link_no_hi = e1b0 & 0x0F
            e1b1 = br.read_uint(8)
            link_number = (link_no_hi << 8) | e1b1
            dist_byte = br.read_uint(8)
            distance_unit = DistanceUnitP((dist_byte >> 7) & 1)
            entrance_distance = dist_byte & 0x7F
            entrance_x = br.read_uint(16)
            entrance_y = br.read_uint(16)
            name = None
            if name_flag:
                name_len = br.read_uint(8)
                name_bytes = br.read(name_len * 8).bytes
                decoder = AribDecoder()
                name = decoder.decode(name_bytes)
            ext1 = Ext1P(
                mesh_flag,
                name_flag,
                link_type,
                link_number,
                distance_unit,
                entrance_distance,
                entrance_x,
                entrance_y,
                name,
            )
            # Ext-2
            ext2 = None
            if self.ext_flag == ParkingExtFlag.BASIC_EXT1_EXT2:
                if br.pos + 40 > br.length:
                    break
                vaw = br.read_uint(8)
                vacancy_rate = (vaw >> 4) & 0x0F
                waiting_time = vaw & 0x0F
                cap_ht = br.read_uint(8)
                capacity = (cap_ht >> 5) & 0x07
                height_lim = (cap_ht >> 3) & 0x03
                veh_lim = cap_ht & 0x07
                dfee = br.read_uint(16)
                discount_cond = (dfee >> 14) & 0x03
                fee_unit = (dfee >> 11) & 0x07
                fee_code = dfee & 0x7FF
                sh = br.read_uint(8)
                start_hour = None if ((sh >> 3) & 0x1F) >= 24 else (sh >> 3) & 0x1F
                start_min10 = None if (sh & 0x07) >= 6 else sh & 0x07
                eh = br.read_uint(8)
                end_hour = None if ((eh >> 3) & 0x1F) >= 24 else (eh >> 3) & 0x1F
                end_min10 = None if (eh & 0x07) >= 6 else eh & 0x07
                ext2 = Ext2P(
                    vacancy_rate,
                    waiting_time,
                    capacity,
                    height_lim,
                    veh_lim,
                    discount_cond,
                    fee_unit,
                    fee_code,
                    start_hour,
                    start_min10,
                    end_hour,
                    end_min10,
                )
            self.records.append(ParkingRecord(ext1, ext2))
        # Store any leftover
        if br.pos < br.length:
            self.raw_rest = br.read(br.length - br.pos).bytes
        return self


# ────────────────────────── 0x43 Section Travel-time ──────────────────────────
class SectionExtFlag(enum.IntEnum):
    BASIC = 0  # PB L1 only
    BASIC_EXT1 = 1  # future extension-1
    MODE = 2  # reserved
    MODE_3 = 3  # reserved


class Priority(enum.IntEnum):
    UNDEFINED = 0
    NORMAL = 1
    UNDEFINED_2 = 2
    IMPORTANT = 3


@register(0x43)
@dataclass
class SectionTravelTimeUnit(GenericDataUnit):
    ext_flag: SectionExtFlag = field(init=False)
    hours: int = field(init=False)
    priority: Priority = field(init=False)
    minutes: int = field(init=False)
    link_count: int = field(init=False)
    raw_links: bytes = field(default=b"", init=False)

    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "SectionTravelTimeUnit":
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )
        br = BitReader(self.data_unit_data)
        # PB L1: ext_flag (2bit) + hours (5bit) + reserved (1bit)
        b1 = br.read_uint(8)
        self.ext_flag = SectionExtFlag((b1 >> 6) & 0x03)
        self.hours = b1 & 0x1F
        # PB L2: priority (2bit) + minutes (6bit)
        b2 = br.read_uint(8)
        self.priority = Priority((b2 >> 6) & 0x03)
        self.minutes = b2 & 0x3F
        # PB L3: link_count
        self.link_count = br.read_uint(8)
        # Remaining variable-length block: links, names, coords... keep raw
        if br.pos < br.length:
            self.raw_links = br.read(br.length - br.pos).bytes
        return self
