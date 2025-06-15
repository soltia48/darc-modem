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

from darc.arib_string import AribStringDecoder


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
    """表3.1‑1‑3 渋滞度 (2bit)"""

    UNKNOWN = 0  # 不明
    FREE = 1  # 渋滞なし
    SLOW = 2  # 混雑
    JAM = 3  # 渋滞


class DistanceUnit(enum.IntEnum):
    """表3.1‑6 距離単位 (2bit)"""

    TEN_M = 0  # 10 m 単位
    HUNDRED_M = 1  # 100 m 単位
    ONE_KM = 2  # 1 km 単位
    UNDEFINED = 3  # 未定義


class TimeUnit(enum.IntEnum):
    """表3.1‑8 時間単位 (1bit)"""

    SEC_10 = 0  # 10 秒単位
    MINUTE = 1  # 1 分単位


class TravelTimeKind(enum.IntEnum):
    """表3.1‑1‑1 旅行時間種別 (b6)"""

    CURRENT = 0  # 現在データ
    PREDICTION = 1  # 予測データ


# ====================== 0x40 Congestion / Travel‑time =====================


class ProvideForm(enum.IntEnum):
    TRAVEL_TIME_INCLUDED = 0  # 提形0  (渋滞 + 旅行時間)
    CONGESTION_ONLY = 1  # 提形1  (渋滞のみ)


# per‑link 拡張フラグ (表3.1‑1‑5)
class LinkExtFlag(enum.IntEnum):
    NONE = 0  # 基本情報のみ
    EXT1 = 1  # 基本 + 拡張1
    EXT1_EXT2 = 2  # 基本 + 拡張1 + 2
    AGGREGATED_OR_INVALID = 3  # 消失リンク / 情報集約 / 無効


# ----- 拡張1 : 距離 / 渋滞長 -------------------------------------------------
@dataclass
class Ext1:
    distance_unit: DistanceUnit  # 2bit
    leading_position: int  # 0‑126 : 位置 × 単位, 127=不明
    jam_length: int  # 0‑126 : 長さ × 単位, 127=不明 (0→リンク長)


# ----- 拡張2 : リンク旅行時間 ------------------------------------------------
@dataclass
class Ext2:
    time_unit: TimeUnit  # 1bit
    travel_time_code: int  # 0 (不明) / 1‑125 有効 / 126‑127 未定義

    @property
    def seconds(self) -> Optional[int]:
        if self.travel_time_code == 0 or self.travel_time_code >= 126:
            return None
        return self.travel_time_code * (10 if self.time_unit == TimeUnit.SEC_10 else 60)


# ----- per‑link 情報 ----------------------------------------------------------
@dataclass
class LinkInfo:
    congestion: CongestionDegree
    ext_flag: LinkExtFlag
    travel_time_code: Optional[int]
    travel_time_seconds: Optional[int]
    ext1: Optional[Ext1] = None
    ext2: Optional[Ext2] = None


# ================== CongestionTravelTimeUnit (DUP 0x40) ====================


@register(0x40)
@dataclass
class CongestionTravelTimeUnit(GenericDataUnit):
    """ARIB STD‑B3 データユニット 0x40   渋滞・旅行時間"""

    provide_form: ProvideForm = field(init=False)
    travel_kind: TravelTimeKind = field(init=False)  # ← b6 (旅行時間種別)
    info_count_flag: bool = field(init=False)  # b5  情報数フラグ
    mode_flag: int = field(init=False)  # b4  モード識別 (現状予約)
    continuous_links: int = field(init=False)  # 12bit  連続リンク数
    link_type: int = field(init=False)  # 2bit   リンク種別
    first_link_no: int = field(init=False)  # 12bit  先頭リンク番号

    links: List[LinkInfo] = field(default_factory=list, repr=False, init=False)
    raw_tail: bytes = field(default=b"", init=False)

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: "GenericDataUnit") -> "CongestionTravelTimeUnit":
        # 通常の __init__ をバイパス
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )

        br = BitReader(self.data_unit_data)
        self.provide_form = ProvideForm(br.read_uint(1))  # b7
        self.travel_kind = TravelTimeKind(br.read_uint(1))  # b6
        self.info_count_flag = bool(br.read_uint(1))  # b5
        self.mode_flag = br.read_uint(1)  # b4
        self.continuous_links = br.read_uint(12)  # b3‑b0 + b11‑b0
        self.link_type = br.read_uint(2)
        self.first_link_no = br.read_uint(12)

        if self.provide_form == ProvideForm.TRAVEL_TIME_INCLUDED:
            self._decode_form0(br)
        else:
            self._decode_form1(br)
        return self

    # ------------------------------------------------------------------
    def _decode_form0(self, br: "BitReader") -> None:
        """提形0 : 渋滞 + 旅行時間 (表3.1‑1‑4)"""
        first_link_info: Optional[LinkInfo] = None
        for _ in range(self.continuous_links):
            if br.pos + 8 > br.length:
                break
            byte = br.read_uint(8)

            congestion = CongestionDegree((byte >> 6) & 0x03)  # b7‑b6
            code = byte & 0x3F  # b5‑b0

            ext_flag: LinkExtFlag
            t_code: Optional[int] = None
            t_sec: Optional[int] = None
            ext1 = ext2 = None

            if code <= 59:  # 0‑59 → 10 秒単位, 0=不明
                ext_flag = LinkExtFlag.NONE
                t_code = code
                t_sec = None if code == 0 else code * 10
            elif code in (60, 61):  # 拡張1 / 拡張1+2
                ext_flag = LinkExtFlag.EXT1 if code == 60 else LinkExtFlag.EXT1_EXT2
                # ----- 拡張1 : 16bit -----
                if br.pos + 16 > br.length:
                    break
                e1b0 = br.read_uint(8)
                e1b1 = br.read_uint(8)
                ext1 = Ext1(
                    DistanceUnit((e1b0 >> 6) & 0x03),
                    ((e1b0 & 0x3F) << 1) | (e1b1 >> 7),
                    e1b1 & 0x7F,
                )
                # ----- 拡張2 (任意) : 8bit -----
                if code == 61 and br.pos + 8 <= br.length:
                    e2 = br.read_uint(8)
                    ext2 = Ext2(TimeUnit((e2 >> 7) & 0x01), e2 & 0x7F)
                    t_code = ext2.travel_time_code
                    t_sec = ext2.seconds
            elif code == 62:  # 未定義
                ext_flag = LinkExtFlag.AGGREGATED_OR_INVALID
            else:  # 63 : 消失リンク／情報集約
                ext_flag = LinkExtFlag.AGGREGATED_OR_INVALID

            link_info = LinkInfo(congestion, ext_flag, t_code, t_sec, ext1, ext2)
            self.links.append(link_info)
            if self.info_count_flag and first_link_info is None:
                first_link_info = link_info

        # 情報数フラグが1 → 最初のデータを残りリンクに複製
        if self.info_count_flag and first_link_info is not None:
            missing = self.continuous_links - len(self.links)
            if missing > 0:
                self.links.extend([first_link_info] * missing)

        # 末尾残り (予約領域) を保持
        if br.pos < br.length:
            self.raw_tail = br.read(br.length - br.pos).bytes

    # ------------------------------------------------------------------
    def _decode_form1(self, br: "BitReader") -> None:
        """提形1 : 渋滞度のみ (表3.1‑1‑11/12)"""
        first_link_info: Optional[LinkInfo] = None
        for _ in range(self.continuous_links):
            if br.pos + 8 > br.length:
                break
            byte = br.read_uint(8)
            ext_flag = LinkExtFlag((byte >> 4) & 0x03)  # b5‑b4
            congestion = CongestionDegree((byte >> 2) & 0x03)  # b3‑b2
            # b1‑b0 は未定義 (読み飛ばし)
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

        if self.info_count_flag and first_link_info is not None:
            missing = self.continuous_links - len(self.links)
            if missing > 0:
                self.links.extend([first_link_info] * missing)

        if br.pos < br.length:
            self.raw_tail = br.read(br.length - br.pos).bytes


# ==================== 0x41 Restriction / Accident =========================
class ExtFlag(enum.IntEnum):
    BASIC = 0  # 基本構成のみ
    BASIC_EXT1 = 1  # 基本 + 拡張1
    BASIC_EXT1_EXT2 = 2  # 基本 + 拡張1 + 2
    MODE = 3  # モード識別 (将来拡張/無効)


# ───────────────────────── 拡張1 ──────────────────────────
@dataclass
class Ext1R:
    """拡張1 (PBm〜PBm+4)"""

    restriction_detail_code: int  #  8 bit  表 3.1-2-9
    cause_detail_code: int  #  8 bit  表 3.1-2-10

    distance_unit: DistanceUnit  #  2 bit  (PBm+2 b7, PBm+3 b7)
    start_distance: int  #  7 bit  (PBm+2 b6-0)
    end_distance: int  #  7 bit  (PBm+3 b6-0)

    timeband_flag: bool  #  1 bit  (PBm+4 b7) 0=終日,1=時刻帯指定
    reserved: int  #  7 bit  (PBm+4 b6-0)


# ───────────────────────── 拡張2 ──────────────────────────
@dataclass
class Ext2R:
    """
    拡張2 期間情報 (PBm+5〜PBm+9, 5 Byte = 40 bit)

    None           … 未定義 / 不明を表す
    start_* / end_* … 仕様書 §3.1-2-8〜§3.1-2-11 に準拠
    """

    start_month: Optional[int]
    end_month: Optional[int]
    start_day: Optional[int]
    start_hour: Optional[int]
    start_min: Optional[int]
    end_day: Optional[int]
    end_hour: Optional[int]
    end_min: Optional[int]

    # ------------------------------------------------------------------
    @staticmethod
    def _clean(value: int, undef_vals: set[int]) -> Optional[int]:
        """未定義値 → None へ変換"""
        return None if value in undef_vals else value

    # ------------------------------------------------------------------
    @classmethod
    def parse(cls, br: BitReader) -> "Ext2R":
        """BitReader 位置は拡張2 先頭 (PBm+5) を指している前提"""
        if br.pos + 40 > br.length:
            raise ValueError("insufficient bits for Ext2R (need 40 bits)")

        # ---- PBm+5 ---------------------------------------------------
        b0 = br.read_uint(8)
        start_month = (b0 >> 4) & 0x0F  # 1-12, 0=未定義
        end_month = b0 & 0x0F  # 1-12, 0=未定義

        # ---- PBm+6 ---------------------------------------------------
        b1 = br.read_uint(8)
        start_day = (b1 >> 3) & 0x1F  # 1-31, 0=未定義
        sh_hi = b1 & 0x07  # 時上位 3 bit

        # ---- PBm+7 ---------------------------------------------------
        b2 = br.read_uint(8)
        sh_lo = (b2 >> 6) & 0x03  # 時下位 2 bit
        start_hour = (sh_hi << 2) | sh_lo  # 0-23, 24-31=未定義
        start_min = b2 & 0x3F  # 0-59, 60-63=未定義

        # ---- PBm+8 ---------------------------------------------------
        b3 = br.read_uint(8)
        end_day = (b3 >> 3) & 0x1F  # 1-31, 0=未定義
        eh_hi = b3 & 0x07  # 時上位 3 bit

        # ---- PBm+9 ---------------------------------------------------
        b4 = br.read_uint(8)
        eh_lo = (b4 >> 6) & 0x03
        end_hour = (eh_hi << 2) | eh_lo  # 0-23, 24-31=未定義
        end_min = b4 & 0x3F  # 0-59, 60-63=未定義

        undef_hour = set(range(24, 32))
        undef_min = {60, 61, 62, 63}

        clean = cls._clean
        return cls(
            clean(start_month, {0}),
            clean(end_month, {0}),
            clean(start_day, {0}),
            clean(start_hour, undef_hour),
            clean(start_min, undef_min),
            clean(end_day, {0}),
            clean(end_hour, undef_hour),
            clean(end_min, undef_min),
        )


# ───────────────── Restriction / Accident GDU ─────────────────
@register(0x41)
@dataclass
class RestrictionAccidentUnit(GenericDataUnit):
    """
    Data-unit 0x41  (規制・事故情報)
    """

    # ---------- 基本構成 -------------------------------------------------
    ext_flag: ExtFlag = field(init=False)
    link_count: int = field(init=False)

    cause_code: int = field(init=False)  # 4 bit (表 3.1-2-3)
    restriction_code: int = field(init=False)  # 4 bit (表 3.1-2-4)

    distance_unit: DistanceUnit = field(init=False)  # 基本構成 長さ単位
    restriction_length: int = field(init=False)  # 6 bit (0-63)

    # ---------- 拡張 -----------------------------------------------------
    ext1: Optional[Ext1R] = field(default=None, init=False)
    ext2: Optional[Ext2R] = field(default=None, init=False)

    # ---------- 生リンク列ブロック --------------------------------------
    raw_links_block: bytes = field(default=b"", init=False)

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "RestrictionAccidentUnit":
        """
        GenericDataUnit → RestrictionAccidentUnit へのデコード
        """
        self = cls.__new__(cls)
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )
        br = BitReader(self.data_unit_data)

        # ─ PB L1 ────────────────────────────────────────────────
        b1 = br.read_uint(8)
        self.ext_flag = ExtFlag((b1 >> 6) & 0x03)
        self.link_count = b1 & 0x3F

        # ─ PB L2 ────────────────────────────────────────────────
        b2 = br.read_uint(8)
        self.cause_code = (b2 >> 4) & 0x0F
        self.restriction_code = b2 & 0x0F

        # ─ PB L3 ────────────────────────────────────────────────
        b3 = br.read_uint(8)
        self.distance_unit = DistanceUnit((b3 >> 6) & 0x03)
        self.restriction_length = b3 & 0x3F

        # ---------- 拡張1 -------------------------------------------------
        if self.ext_flag in (ExtFlag.BASIC_EXT1, ExtFlag.BASIC_EXT1_EXT2):
            pbm = br.read_uint(8)  # PBm
            pbm1 = br.read_uint(8)  # PBm+1
            pbm2 = br.read_uint(8)  # PBm+2
            pbm3 = br.read_uint(8)  # PBm+3
            pbm4 = br.read_uint(8)  # PBm+4

            # 距離単位 (PBm+2 b7:MSB, PBm+3 b7:LSB)
            unit_bits = ((pbm2 >> 7) << 1) | (pbm3 >> 7)
            dist_unit = DistanceUnit(unit_bits)

            self.ext1 = Ext1R(
                restriction_detail_code=pbm,
                cause_detail_code=pbm1,
                distance_unit=dist_unit,
                start_distance=pbm2 & 0x7F,
                end_distance=pbm3 & 0x7F,
                timeband_flag=bool((pbm4 >> 7) & 0x01),
                reserved=pbm4 & 0x7F,
            )

        # ---------- 拡張2 -------------------------------------------------
        if self.ext_flag == ExtFlag.BASIC_EXT1_EXT2:
            self.ext2 = Ext2R.parse(br)

        # ---------- リンク列ブロック -------------------------------------
        if br.pos < br.length:
            self.raw_links_block = br.read(br.length - br.pos).bytes

        return self


# =============================================================================
# 列挙体定義（省略なし）
# =============================================================================
class ParkingExtFlag(enum.IntEnum):
    BASIC = 0
    BASIC_EXT1 = 1
    BASIC_EXT1_EXT2 = 2
    MODE = 3  # 仕様ではモード識別用（未実装）


class VacancyStatus(enum.IntEnum):
    EMPTY = 0
    CONGEST = 1
    FULL = 2
    CLOSED = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    UNDEFINED_6 = 6
    UNKNOWN = 7


class LinkType(enum.IntEnum):
    EXPRESSWAY = 0
    URBAN_EXPRESSWAY = 1
    ARTERIAL = 2
    OTHER = 3


class DistanceUnitP(enum.IntEnum):
    TEN_M = 0  # 10 m
    HUNDRED_M = 1  # 100 m


class CapacityClass(enum.IntEnum):
    UNDER_20 = 0
    UNDER_50 = 1
    UNDER_100 = 2
    UNDER_200 = 3
    UNDER_500 = 4
    UNDER_1000 = 5
    OVER_1000 = 6
    UNKNOWN = 7


class HeightLimit(enum.IntEnum):
    NONE = 0
    LIMITED = 1
    UNDEFINED = 2
    UNKNOWN = 3


class VehicleLimit(enum.IntEnum):
    NONE = 0
    LARGE_VEHICLE = 1
    THREE_NUMBER = 2
    UNDEFINED_3 = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    OTHER = 6
    UNKNOWN = 7


class DiscountCondition(enum.IntEnum):
    NONE = 0
    EXISTS = 1
    UNDEFINED = 2
    UNKNOWN = 3


class FeeUnit(enum.IntEnum):
    MIN_30 = 0
    HOUR_1 = 1
    HOUR_2 = 2
    HOUR_3 = 3
    HALF_DAY = 4
    ONE_DAY = 5
    ONCE = 6
    UNKNOWN = 7


# =============================================================================
# Ext-1 / Ext-2 データクラス
# =============================================================================
@dataclass(slots=True)
class Ext1P:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    distance_unit: DistanceUnitP
    entrance_distance: int
    entrance_x: Optional[int]
    entrance_y: Optional[int]
    name: Optional[str]


@dataclass(slots=True)
class Ext2P:
    vacancy_rate_10pct: int
    waiting_time_10min: int
    capacity_class: CapacityClass
    height_limit: HeightLimit
    vehicle_limit: VehicleLimit
    discount_condition: DiscountCondition
    fee_unit: FeeUnit
    fee_code: int
    start_hour_raw: int
    start_min_raw: int
    end_hour_raw: int
    end_min_raw: int

    # ------- 人間に優しいプロパティ -------
    @property
    def start_hour(self) -> Optional[int]:
        return None if self.start_hour_raw >= 24 else self.start_hour_raw

    @property
    def start_min10(self) -> Optional[int]:
        return None if self.start_min_raw >= 6 else self.start_min_raw

    @property
    def end_hour(self) -> Optional[int]:
        return None if self.end_hour_raw >= 24 else self.end_hour_raw

    @property
    def end_min10(self) -> Optional[int]:
        return None if self.end_min_raw >= 6 else self.end_min_raw


# =============================================================================
# レコード（基本＋Ext 構成を包含）
# =============================================================================
@dataclass(slots=True)
class ParkingRecord:
    ext_flag: ParkingExtFlag
    vacancy_status: VacancyStatus
    is_general: bool
    center_x: int
    center_y: int
    ext1: Optional[Ext1P]
    ext2: Optional[Ext2P]


@register(0x42)
@dataclass(slots=True)
class ParkingUnit(GenericDataUnit):
    """0x42 Parking Unit (複数の駐車場レコードを格納)"""

    # 便宜上 1 件目の値を保持（複数レコード時は records を参照）
    vacancy_status: VacancyStatus = field(init=False)
    is_general: bool = field(init=False)
    center_x: int = field(init=False)
    center_y: int = field(init=False)

    records: List[ParkingRecord] = field(default_factory=list, init=False)
    raw_rest: bytes = field(default=b"", init=False)

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "ParkingUnit":  # noqa: C901
        self: "ParkingUnit" = cls.__new__(cls)  # type: ignore[arg-type]
        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )

        br = BitReader(self.data_unit_data)
        self.records = []
        self.raw_rest = b""

        # ================= ループ：レコード毎 =================
        while br.pos < br.length:
            if (br.length - br.pos) < 40:  # PB L1(1B)+L2-L3(4B)
                break

            # ------------ PB L1 (基本) ------------
            b1 = br.read_uint(8)
            ext_flag = ParkingExtFlag((b1 >> 6) & 0b11)
            vacancy_status = VacancyStatus((b1 >> 3) & 0b111)
            is_general = bool((b1 >> 2) & 1)

            # ------------ PB L2-L3 ---------------
            center_x = br.read_uint(16)
            center_y = br.read_uint(16)

            # ------------ Ext-1 -----------------
            ext1: Optional[Ext1P] = None
            if ext_flag in {ParkingExtFlag.BASIC_EXT1, ParkingExtFlag.BASIC_EXT1_EXT2}:
                if (br.length - br.pos) < 24:  # Ext-1 ヘッダ最低 3B
                    break
                e1_b0 = br.read_uint(8)
                mesh_flag = bool(e1_b0 >> 7)
                name_flag = bool((e1_b0 >> 6) & 1)
                link_type = LinkType((e1_b0 >> 4) & 0b11)
                link_num_hi = e1_b0 & 0x0F

                link_num_lo = br.read_uint(8)
                link_number = (link_num_hi << 8) | link_num_lo

                dist = br.read_uint(8)
                distance_unit = DistanceUnitP(dist >> 7)
                entrance_distance = dist & 0x7F

                entrance_x = entrance_y = None
                if mesh_flag:
                    if (br.length - br.pos) < 32:
                        break
                    entrance_x = br.read_uint(16)
                    entrance_y = br.read_uint(16)

                name: Optional[str] = None
                if name_flag:
                    if (br.length - br.pos) < 8:
                        break
                    name_len = br.read_uint(8)
                    if (br.length - br.pos) < name_len * 8:
                        break
                    name_bytes = br.read(name_len * 8).bytes
                    name = AribStringDecoder().decode(name_bytes)

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

            # ------------ Ext-2 -----------------
            ext2: Optional[Ext2P] = None
            if ext_flag == ParkingExtFlag.BASIC_EXT1_EXT2:
                if (br.length - br.pos) < 48:
                    break
                vaw = br.read_uint(8)
                vacancy_rate = (vaw >> 4) & 0x0F
                waiting_time = vaw & 0x0F

                chv = br.read_uint(8)
                capacity = CapacityClass((chv >> 5) & 0x07)
                height_lim = HeightLimit((chv >> 3) & 0x03)
                vehicle_lim = VehicleLimit(chv & 0x07)

                df = br.read_uint(16)
                discount = DiscountCondition((df >> 14) & 0x03)
                fee_unit = FeeUnit((df >> 11) & 0x07)
                fee_code = df & 0x07FF

                sh = br.read_uint(8)
                start_hour_raw = (sh >> 3) & 0x1F
                start_min_raw = sh & 0x07

                eh = br.read_uint(8)
                end_hour_raw = (eh >> 3) & 0x1F
                end_min_raw = eh & 0x07

                ext2 = Ext2P(
                    vacancy_rate,
                    waiting_time,
                    capacity,
                    height_lim,
                    vehicle_lim,
                    discount,
                    fee_unit,
                    fee_code,
                    start_hour_raw,
                    start_min_raw,
                    end_hour_raw,
                    end_min_raw,
                )

            # ------------ レコード保存 ------------
            self.records.append(
                ParkingRecord(
                    ext_flag,
                    vacancy_status,
                    is_general,
                    center_x,
                    center_y,
                    ext1,
                    ext2,
                )
            )

        # ======= 1 件目をトップレベルに転写（互換） =======
        if self.records:
            first = self.records[0]
            self.vacancy_status = first.vacancy_status
            self.is_general = first.is_general
            self.center_x = first.center_x
            self.center_y = first.center_y
        else:
            self.vacancy_status = VacancyStatus.UNKNOWN
            self.is_general = True
            self.center_x = self.center_y = 0

        # ======= 未読ビット保存 ============================
        if br.pos < br.length:
            self.raw_rest = br.read(br.length - br.pos).bytes

        return self


# ──────────────────── 0x43 Section Travel-time ────────────────────


class SectionExtFlag(enum.IntEnum):
    """表3.1.4-1 拡張フラグ (PB L1 b8,b7)"""

    BASIC = 0  # 基本構成
    BASIC_EXT1 = 1  # 基本構成 + 拡張構成1
    MODE = 2  # モード識別 (将来予約)
    MODE_3 = 3  # モード識別 (将来予約)


class Priority(enum.IntEnum):
    """表3.1-4-3 優先度 (PB L2 b8,b7)"""

    UNDEFINED = 0  # 未定義
    NORMAL = 1  # 定常
    UNDEFINED_2 = 2  # 未定義
    IMPORTANT = 3  # 重要


@dataclass
class AltRoute:
    """拡張構成1で付加される『経由路線ごとの旅行時間情報』の外枠だけ保持"""

    hours: int
    minutes: int
    link_count: int
    raw_links: bytes  # 可変長部はパースせずに保持


@register(0x43)
@dataclass
class SectionTravelTimeUnit(GenericDataUnit):
    # ---- 基本構成 ----
    ext_flag: SectionExtFlag = field(init=False)
    hours: int = field(init=False)  # 0-23, 24-30=未定義, 31=不明
    priority: Priority = field(init=False)
    minutes: int = field(init=False)  # 0-59, 60-62=未定義, 63=不明
    link_count: int = field(init=False)
    raw_links: bytes = field(default=b"", init=False)

    # ---- 拡張構成1 ----
    other_route_count: Optional[int] = field(default=None, init=False)
    alt_routes: List[AltRoute] = field(default_factory=list, init=False)
    raw_other_routes: bytes = field(default=b"", init=False)
    # ※ モード識別 (ext_flag 2,3) は未実装

    # ------------------------------------------------------------------
    @classmethod
    def from_unit(cls, unit: GenericDataUnit) -> "SectionTravelTimeUnit":
        self = cls.__new__(cls)

        # dataclass の default / default_factory が実行されないので手動セット
        self.raw_links = b""
        self.other_route_count = None
        self.alt_routes = []  # ← ここが無いと AttributeError
        self.raw_other_routes = b""

        GenericDataUnit.__init__(
            self,
            unit.data_unit_parameter,
            unit.data_unit_link_flag,
            unit.data_unit_data,
        )

        br = BitReader(self.data_unit_data)

        # ── PB L1 ──  ext_flag(2) + 未定義(1) + hours(5)
        b1 = br.read_uint(8)
        self.ext_flag = SectionExtFlag((b1 >> 6) & 0b11)
        self.hours = b1 & 0b1_1111  # 下位5bit

        # ── PB L2 ── priority(2) + minutes(6)
        b2 = br.read_uint(8)
        self.priority = Priority((b2 >> 6) & 0b11)
        self.minutes = b2 & 0b11_1111  # 下位6bit

        # ── PB L3 ── link_count
        self.link_count = br.read_uint(8)

        # ---- 可変長リンク部（始点〜終点） ----
        start_of_link_block = br.pos
        # 現時点では仕様全体を実装していないため、最後までを raw_links に退避
        if br.pos < br.length:
            self.raw_links = br.read(br.length - br.pos).bytes

        # ---- 拡張構成1 ----
        if self.ext_flag is SectionExtFlag.BASIC_EXT1:
            # BitReader がリンク部の末尾まで読んでしまっているので
            # 再度読み直し用に新しい BitReader を起こす
            br_ext = BitReader(self.raw_links)

            # (10) 他経由路線数[5bit] -- 上位5bit だけ有効
            tmp = br_ext.read_uint(8)
            self.other_route_count = (tmp >> 3) & 0b1_1111
            # 残り3bitは「時間(未定義)」として予約されているが、現行仕様では使用しない

            # ── 以降、other_route_count 分だけ “ほぼ基本構成と同じ” ブロックが続く ──
            for _ in range(self.other_route_count or 0):
                if br_ext.pos + 24 > br_ext.length:  # ヘッダ3byte分読めない場合は終了
                    break
                # Hours(予備3bit+5bit) -- 先頭3bitは『予備』
                b1_alt = br_ext.read_uint(8)
                _ = (b1_alt >> 5) & 0b111  # 予備(無視)
                hours = b1_alt & 0b1_1111

                # 優先度/分
                b2_alt = br_ext.read_uint(8)
                minutes = b2_alt & 0b11_1111
                _prio = (b2_alt >> 6) & 0b11  # 代替経路の優先度(現仕様では保持せず)

                link_cnt = br_ext.read_uint(8)

                # 残りはリンク部（可変長）だが、リンク数だけでは長さを確定できないため
                # ここでは “次の代替経路ヘッダ（＝ 8bit 境界で hours 予備3bit が 0-7）” までを raw とする
                start = br_ext.pos
                # まだ残っていなければ break
                # ひとまず「残データ全部」を与える実装。詳細パースは後日対応。
                br_ext.seek(br_ext.length)
                raw = (
                    br_ext.read(br_ext.length - start).bytes
                    if start < br_ext.length
                    else b""
                )

                self.alt_routes.append(
                    AltRoute(
                        hours=hours, minutes=minutes, link_count=link_cnt, raw_links=raw
                    )
                )

            # 最終的に生バイトも保持（デバッグ／後方互換用）
            self.raw_other_routes = br_ext.buffer

        return self
