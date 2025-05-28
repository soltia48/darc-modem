from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Final, TypeAlias, Self
import unicodedata


class CharacterClass(IntEnum):
    KANJI = 0x42
    ALPHANUMERIC = 0x4A
    HIRAGANA = 0x30
    KATAKANA = 0x31
    MOSAIC_A = 0x32
    MOSAIC_B = 0x33
    MOSAIC_C = 0x34
    MOSAIC_D = 0x35
    MACRO = 0x70
    DRCS_0 = 0x40
    DRCS_1 = 0x41
    DRCS_2 = 0x42
    DRCS_3 = 0x43
    DRCS_4 = 0x44
    DRCS_5 = 0x45
    DRCS_6 = 0x46
    DRCS_7 = 0x47
    DRCS_8 = 0x48
    DRCS_9 = 0x49
    DRCS_10 = 0x4A
    DRCS_11 = 0x4B
    DRCS_12 = 0x4C
    DRCS_13 = 0x4D
    DRCS_14 = 0x4E
    DRCS_15 = 0x4F


class ControlCode(IntEnum):
    # C0
    NUL = 0x00
    SOH = 0x01
    ETX = 0x03
    EOT = 0x04
    APB = 0x08
    APF = 0x09
    APD = 0x0A
    APU = 0x0B
    CS = 0x0C
    APR = 0x0D
    LS1 = 0x0E
    LS0 = 0x0F
    PAPF = 0x16
    ETB = 0x17
    SS2 = 0x19
    ESC = 0x1B
    APS = 0x1C
    SS3 = 0x1D
    RS = 0x1E
    US = 0x1F
    SP = 0x20
    # C1
    DEL = 0x7F
    BKF = 0x80
    RDF = 0x81
    GRF = 0x82
    YLF = 0x83
    BLF = 0x84
    MGF = 0x85
    CNF = 0x86
    WHF = 0x87
    SSZ = 0x88
    MSZ = 0x89
    NSZ = 0x8A
    SZX = 0x8B
    COL = 0x90
    FLC = 0x91
    CDC = 0x92
    POL = 0x93
    WMM = 0x94
    MACRO = 0x95
    HLC = 0x97
    RPC = 0x98
    SPL = 0x99
    STL = 0x9A
    CSI = 0x9B
    TIME = 0x9D


ByteHandler: TypeAlias = Callable[[bytes, int], int]
CharacterMap: TypeAlias = dict[int, str]
MacroMap: TypeAlias = dict[int, bytes]
DRCSMap: TypeAlias = dict[CharacterClass, dict[int, str]]


@dataclass
class DecoderState:
    """Maintains the current state of the decoder"""

    g0: CharacterClass = CharacterClass.KANJI
    g1: CharacterClass = CharacterClass.ALPHANUMERIC
    g2: CharacterClass = CharacterClass.HIRAGANA
    g3: CharacterClass = CharacterClass.MACRO
    gl: CharacterClass = field(init=False)
    gr: CharacterClass = field(init=False)
    single_shift: CharacterClass | None = None
    drcs_maps: DRCSMap = field(default_factory=dict)
    position: tuple[int, int] = (0, 0)
    buffer: list[list[str]] = field(default_factory=list)
    macro_stack: list[bytes] = field(default_factory=list)
    expecting_drcs: bool = False

    def __post_init__(self) -> None:
        """Initialize dependent fields after instance creation"""
        self.gl = self.g0
        self.gr = self.g2


class AribDecoder:
    """ARIB STD-B24 character decoder implementation"""

    REPLACEMENT_CHAR: Final = "�"
    MAX_MACRO_DEPTH: Final = 10

    def __init__(self) -> None:
        self.state = DecoderState()
        self._init_character_sets()
        self._init_control_handlers()
        self._init_macros()

    def reset_state(self) -> None:
        """Reset decoder state to initial values"""
        self.g0 = CharacterClass.KANJI
        self.g1 = CharacterClass.ALPHANUMERIC
        self.g2 = CharacterClass.HIRAGANA
        self.g3 = CharacterClass.MACRO
        self.gl = self.g0  # Left side G set
        self.gr = self.g2  # Right side G set
        self.single_shift: CharacterClass | None = None
        self.drcs_maps: dict[CharacterClass, dict[int, str]] = {}
        self.position: tuple[int, int] = (0, 0)
        self.buffer: list[list[str]] = []
        self.macro_stack: list[bytes] = []
        self.expecting_drcs = False
        self.current_macro_context: dict[str, Any] = {}

    def _init_character_sets(self) -> None:
        """Initialize character set mapping tables"""
        self.kanji_map: CharacterMap = self._create_kanji_map()
        self.alphanumeric_map: CharacterMap = {i: chr(i) for i in range(0x21, 0x7F)}
        self.hiragana_map: CharacterMap = self._create_hiragana_map()
        self.katakana_map: CharacterMap = self._create_katakana_map()
        self.mosaic_maps: dict[CharacterClass, CharacterMap] = {
            cls: {}
            for cls in (
                CharacterClass.MOSAIC_A,
                CharacterClass.MOSAIC_B,
                CharacterClass.MOSAIC_C,
                CharacterClass.MOSAIC_D,
            )
        }

    def _create_kanji_map(self) -> CharacterMap:
        """Create JIS X 0213:2004 kanji mapping with caching"""
        kanji_map: CharacterMap = {}

        for first in range(0x21, 0x7F):
            for second in range(0x21, 0x7F):
                jis_seq = bytes(
                    [
                        0x1B,
                        0x24,
                        0x42,  # ESC $ B
                        first,
                        second,  # Character bytes
                        0x1B,
                        0x28,
                        0x42,  # ESC ( B
                    ]
                )

                try:
                    char = jis_seq.decode("iso2022_jp_2004")
                    if char and char != "\x1b":
                        arib_code = (first << 8) | second
                        kanji_map[arib_code] = char
                except UnicodeDecodeError:
                    continue

        return kanji_map

    def _create_hiragana_map(self) -> CharacterMap:
        """Generate hiragana character mapping"""
        hiragana_map: CharacterMap = {}

        # Map using Unicode ranges
        hiragana_start = 0x3041  # Unicode for ぁ
        arib_start = 0x21

        # Map standard hiragana
        for i in range(83):
            unicode_char = chr(hiragana_start + i)
            if unicodedata.category(unicode_char).startswith("Lo"):
                hiragana_map[arib_start + i] = unicode_char

        # Add special cases
        hiragana_map[0x52] = "ゔ"

        return hiragana_map

    def _create_katakana_map(self) -> CharacterMap:
        """Generate katakana character mapping"""
        katakana_map: CharacterMap = {}

        # Map using Unicode ranges
        katakana_start = 0x30A1  # Unicode for ァ
        arib_start = 0x21

        # Map standard katakana
        for i in range(83):
            unicode_char = chr(katakana_start + i)
            if unicodedata.category(unicode_char).startswith("Lo"):
                katakana_map[arib_start + i] = unicode_char

        # Add special cases
        katakana_map[0x52] = "ヴ"

        return katakana_map

    def _init_control_handlers(self) -> None:
        """Initialize control sequence handlers"""
        self.control_handlers: dict[ControlCode, ByteHandler] = {
            ControlCode.APB: self._handle_apb,
            ControlCode.APF: self._handle_apf,
            ControlCode.APD: self._handle_apd,
            ControlCode.APU: self._handle_apu,
            ControlCode.APR: self._handle_apr,
            ControlCode.PAPF: self._handle_papf,
            ControlCode.APS: self._handle_aps,
            ControlCode.CS: self._handle_cs,
            ControlCode.ESC: self._handle_esc,
            ControlCode.LS1: self._handle_ls1,
            ControlCode.LS0: self._handle_ls0,
            ControlCode.SS2: self._handle_ss2,
            ControlCode.SS3: self._handle_ss3,
            ControlCode.COL: self._handle_col,
            ControlCode.POL: self._handle_pol,
            ControlCode.SZX: self._handle_szx,
            ControlCode.CDC: self._handle_cdc,
            ControlCode.WMM: self._handle_wmm,
            ControlCode.TIME: self._handle_time,
            ControlCode.MACRO: self._handle_macro,
            ControlCode.RPC: self._handle_rpc,
            ControlCode.STL: self._handle_stl,
            ControlCode.SPL: self._handle_spl,
            ControlCode.HLC: self._handle_hlc,
            ControlCode.CSI: self._handle_csi,
        }

    def _init_macros(self) -> None:
        """Initialize macro definitions"""
        self.macros: dict[int, bytes] = {}

        # 6/0 (0x60)
        self.macros[0x60] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x4A,  # ESC 02/9 F (Alphanumeric: 0x4A)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/1 (0x61)
        self.macros[0x61] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x31,  # ESC 02/9 F (Katakana: 0x31)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/2 (0x62)
        self.macros[0x62] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x20,
                0x41,  # ESC 02/9 02/0 F (DRCS-1: 0x41)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/3 (0x63)
        self.macros[0x63] = bytes(
            [
                0x1B,
                0x28,
                0x32,  # ESC 02/8 F (Mosaic A: 0x32)
                0x1B,
                0x29,
                0x34,  # ESC 02/9 F (Mosaic C: 0x34)
                0x1B,
                0x2A,
                0x35,  # ESC 02/10 F (Mosaic D: 0x35)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/4 (0x64)
        self.macros[0x64] = bytes(
            [
                0x1B,
                0x28,
                0x32,  # ESC 02/8 F (Mosaic A: 0x32)
                0x1B,
                0x29,
                0x33,  # ESC 02/9 F (Mosaic B: 0x33)
                0x1B,
                0x2A,
                0x35,  # ESC 02/10 F (Mosaic D: 0x35)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/5 (0x65)
        self.macros[0x65] = bytes(
            [
                0x1B,
                0x28,
                0x32,  # ESC 02/8 F (Mosaic A: 0x32)
                0x1B,
                0x29,
                0x20,
                0x41,  # ESC 02/9 02/0 F (DRCS-1: 0x41)
                0x1B,
                0x2A,
                0x35,  # ESC 02/10 F (Mosaic D: 0x35)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/6 (0x66)
        self.macros[0x66] = bytes(
            [
                0x1B,
                0x28,
                0x20,
                0x41,  # ESC 02/8 02/0 F (DRCS-1: 0x41)
                0x1B,
                0x29,
                0x20,
                0x42,  # ESC 02/9 02/0 F (DRCS-2: 0x42)
                0x1B,
                0x2A,
                0x20,
                0x43,  # ESC 02/10 02/0 F (DRCS-3: 0x43)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/7 (0x67)
        self.macros[0x67] = bytes(
            [
                0x1B,
                0x28,
                0x20,
                0x44,  # ESC 02/8 02/0 F (DRCS-4: 0x44)
                0x1B,
                0x29,
                0x20,
                0x45,  # ESC 02/9 02/0 F (DRCS-5: 0x45)
                0x1B,
                0x2A,
                0x20,
                0x46,  # ESC 02/10 02/0 F (DRCS-6: 0x46)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/8 (0x68)
        self.macros[0x68] = bytes(
            [
                0x1B,
                0x28,
                0x20,
                0x47,  # ESC 02/8 02/0 F (DRCS-7: 0x47)
                0x1B,
                0x29,
                0x20,
                0x48,  # ESC 02/9 02/0 F (DRCS-8: 0x48)
                0x1B,
                0x2A,
                0x20,
                0x49,  # ESC 02/10 02/0 F (DRCS-9: 0x49)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/9 (0x69)
        self.macros[0x69] = bytes(
            [
                0x1B,
                0x28,
                0x20,
                0x4A,  # ESC 02/8 02/0 F (DRCS-10: 0x4A)
                0x1B,
                0x29,
                0x20,
                0x4B,  # ESC 02/9 02/0 F (DRCS-11: 0x4B)
                0x1B,
                0x2A,
                0x20,
                0x4C,  # ESC 02/10 02/0 F (DRCS-12: 0x4C)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/10 (0x6A)
        self.macros[0x6A] = bytes(
            [
                0x1B,
                0x28,
                0x20,
                0x4D,  # ESC 02/8 02/0 F (DRCS-13: 0x4D)
                0x1B,
                0x29,
                0x20,
                0x4E,  # ESC 02/9 02/0 F (DRCS-14: 0x4E)
                0x1B,
                0x2A,
                0x20,
                0x4F,  # ESC 02/10 02/0 F (DRCS-15: 0x4F)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/11 (0x6B)
        self.macros[0x6B] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x20,
                0x42,  # ESC 02/9 02/0 F (DRCS-2: 0x42)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/12 (0x6C)
        self.macros[0x6C] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x20,
                0x43,  # ESC 02/9 02/0 F (DRCS-3: 0x43)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/13 (0x6D)
        self.macros[0x6D] = bytes(
            [
                0x1B,
                0x24,
                0x42,  # ESC 02/4 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x20,
                0x44,  # ESC 02/9 02/0 F (DRCS-4: 0x44)
                0x1B,
                0x2A,
                0x30,  # ESC 02/10 F (Hiragana: 0x30)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/14 (0x6E)
        self.macros[0x6E] = bytes(
            [
                0x1B,
                0x28,
                0x4A,  # ESC 02/8 F (Alphanumeric: 0x4A)
                0x1B,
                0x29,
                0x30,  # ESC 02/9 F (Hiragana: 0x30)
                0x1B,
                0x2A,
                0x42,  # ESC 02/10 F (Kanji: 0x42)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

        # 6/15 (0x6F)
        self.macros[0x6F] = bytes(
            [
                0x1B,
                0x28,
                0x42,  # ESC 02/8 F (Kanji: 0x42)
                0x1B,
                0x29,
                0x32,  # ESC 02/9 F (Mosaic A: 0x32)
                0x1B,
                0x2A,
                0x20,
                0x41,  # ESC 02/10 02/0 F (DRCS-1: 0x41)
                0x1B,
                0x2B,
                0x20,
                0x70,  # ESC 02/11 02/0 F (Macro: 0x70)
                0x0F,  # LS0
                0x1B,
                0x7D,  # ESC 07/13
            ]
        )

    def decode(self, data: bytes) -> str:
        """
        Decode ARIB STD-B24 encoded bytes into Unicode text

        Args:
            data: Input bytes to decode

        Returns:
            Decoded Unicode string
        """
        result: list[str] = []
        i = 0
        data_len = len(data)

        try:
            while i < data_len:
                byte = data[i]

                # Skip invalid bytes
                if not (0x00 <= byte <= 0xFF):
                    i += 1
                    result.append(self.REPLACEMENT_CHAR)
                    continue

                # Process control codes
                if self.is_control_code(byte):
                    try:
                        handler = self.control_handlers.get(ControlCode(byte))
                        if handler:
                            i = handler(data, i)
                    except (ValueError, IndexError):
                        pass
                    i += 1
                    continue

                # Determine character set and decode
                try:
                    if byte < 0x80:
                        char_set = (
                            self.state.single_shift
                            if self.state.single_shift
                            else self.state.gl
                        )
                        self.state.single_shift = None
                    else:
                        char_set = self.state.gr
                        byte &= 0x7F

                    char = (
                        self._decode_kanji(byte, data[i + 1])
                        if char_set == CharacterClass.KANJI
                        else self._decode_single_byte(byte, char_set)
                    )

                    result.append(char)
                    i += 2 if char_set == CharacterClass.KANJI else 1

                except (IndexError, KeyError):
                    result.append(self.REPLACEMENT_CHAR)
                    i += 1

        except Exception as e:
            print(f"Unexpected error during decoding: {e}")

        return "".join(result)

    @staticmethod
    def is_control_code(byte: int) -> bool:
        """Check if byte is a control code"""
        return byte <= 0x20 or byte == 0x7F

    def _decode_kanji(self, first_byte: int, second_byte: int) -> str:
        """Decode a kanji character from two bytes"""
        if not (0x21 <= first_byte <= 0x7E and 0x21 <= second_byte <= 0x7E):
            return self.REPLACEMENT_CHAR

        arib_code = (first_byte << 8) | second_byte
        return self.kanji_map.get(arib_code, self.REPLACEMENT_CHAR)

    def _create_jis_sequence(
        self, plane: int, first_byte: int, second_byte: int
    ) -> bytes:
        """
        Create JIS escape sequence for given plane and bytes

        Args:
            plane: JIS X 0213 plane (1 or 2)
            first_byte: First byte of character
            second_byte: Second byte of character

        Returns:
            JIS escape sequence bytes
        """
        if plane == 1:
            return bytes(
                [
                    0x1B,
                    0x24,
                    0x42,  # ESC $ B
                    first_byte,
                    second_byte,
                    0x1B,
                    0x28,
                    0x42,  # ESC ( B
                ]
            )
        else:
            return bytes(
                [
                    0x1B,
                    0x24,
                    0x28,
                    0x51,  # ESC $ ( Q
                    first_byte,
                    second_byte,
                    0x1B,
                    0x28,
                    0x42,  # ESC ( B
                ]
            )

    def _decode_single_byte(self, byte: int, char_set: CharacterClass) -> str:
        """Decode a single byte character"""
        if not (0x21 <= byte <= 0x7E):
            return self.REPLACEMENT_CHAR

        match char_set:
            case CharacterClass.ALPHANUMERIC:
                return self.alphanumeric_map.get(byte, self.REPLACEMENT_CHAR)
            case CharacterClass.HIRAGANA:
                return self.hiragana_map.get(byte, self.REPLACEMENT_CHAR)
            case CharacterClass.KATAKANA:
                return self.katakana_map.get(byte, self.REPLACEMENT_CHAR)
            case (
                CharacterClass.MOSAIC_A
                | CharacterClass.MOSAIC_B
                | CharacterClass.MOSAIC_C
                | CharacterClass.MOSAIC_D
            ):
                return self.mosaic_maps[char_set].get(byte, self.REPLACEMENT_CHAR)
            case _ if 0x40 <= char_set.value <= 0x4F:
                drcs_map = self.state.drcs_maps.get(char_set, {})
                return drcs_map.get(byte, self.REPLACEMENT_CHAR)
            case _:
                return self.REPLACEMENT_CHAR

    def load_drcs(self, drcs_class: CharacterClass, drcs_data: dict[int, str]) -> None:
        """Load DRCS pattern data for a specific character set

        Args:
            drcs_class: DRCS character class to load
            drcs_data: Dictionary mapping character codes to pattern data
        """
        if CharacterClass.DRCS_0 <= drcs_class <= CharacterClass.DRCS_15:
            self.state.drcs_maps[drcs_class] = drcs_data

    def _handle_apb(self, data: bytes, pos: int) -> int:
        """Handle Active Position Backward"""
        x, y = self.state.position
        self.state.position = (max(0, x - 1), y)
        return pos

    def _handle_apf(self, data: bytes, pos: int) -> int:
        """Handle Active Position Forward"""
        x, y = self.state.position
        self.state.position = (x + 1, y)
        return pos

    def _handle_apd(self, data: bytes, pos: int) -> int:
        """Handle Active Position Down"""
        x, y = self.state.position
        self.state.position = (x, y + 1)
        return pos

    def _handle_apu(self, data: bytes, pos: int) -> int:
        """Handle Active Position Up"""
        x, y = self.state.position
        self.state.position = (x, max(0, y - 1))
        return pos

    def _handle_apr(self, data: bytes, pos: int) -> int:
        """Handle Active Position Return"""
        _, y = self.state.position
        self.state.position = (0, y + 1)
        return pos

    def _handle_papf(self, data: bytes, pos: int) -> int:
        """Handle Parameterized Active Position Forward"""
        if pos + 1 >= len(data):
            return pos

        p1 = data[pos + 1] & 0x7F  # Clear MSB if set
        x, y = self.state.position
        self.state.position = (x + p1, y)
        return pos + 1

    def _handle_aps(self, data: bytes, pos: int) -> int:
        """Handle Active Position Set"""
        if pos + 2 >= len(data):
            return pos

        p1, p2 = data[pos + 1 : pos + 3]
        self.state.position = (p2, p1)
        return pos + 2

    def _handle_cs(self, data: bytes, pos: int) -> int:
        """Handle Clear Screen"""
        self.state.buffer.clear()
        self.state.position = (0, 0)
        return pos

    def _handle_esc(self, data: bytes, pos: int) -> int:
        """Handle Escape sequences"""
        if pos + 2 >= len(data):
            return pos

        next_byte = data[pos + 1]
        if next_byte not in (0x24, 0x28, 0x29, 0x2A, 0x2B):
            return pos + 1

        match next_byte:
            case 0x24:  # 02/4
                if pos + 2 >= len(data):
                    return pos
                self._handle_character_set_designation(data[pos + 2], 0)
                return pos + 2

            case 0x28 | 0x29 | 0x2A | 0x2B as byte:  # 02/8-02/11
                g_set = byte - 0x28  # Calculate G-set number (0-3)
                if pos + 2 >= len(data):
                    return pos

                if data[pos + 2] == 0x20:  # 02/0
                    if pos + 3 >= len(data):
                        return pos
                    self._handle_character_set_designation(0x20, g_set)
                    self._handle_character_set_designation(data[pos + 3], g_set)
                    return pos + 3
                else:
                    self._handle_character_set_designation(data[pos + 2], g_set)
                    return pos + 2

        return pos + 1

    def _handle_ls1(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 1"""
        self.state.gl = self.state.g1
        self.state.single_shift = None
        return pos

    def _handle_ls0(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 0"""
        self.state.gl = self.state.g0
        self.state.single_shift = None
        return pos

    def _handle_ss2(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 2"""
        self.state.single_shift = self.state.g2
        return pos

    def _handle_ss3(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 3"""
        self.state.single_shift = self.state.g3
        return pos

    def _handle_col(self, data: bytes, pos: int) -> int:
        """Handle Color Control"""
        return pos + 1 if pos + 1 < len(data) else pos

    def _handle_pol(self, data: bytes, pos: int) -> int:
        """Handle Pattern Polarity Control"""
        return pos + 1 if pos + 1 < len(data) else pos

    def _handle_szx(self, data: bytes, pos: int) -> int:
        """Handle Set Character Size"""
        return pos + 1 if pos + 1 < len(data) else pos

    def _handle_cdc(self, data: bytes, pos: int) -> int:
        """Handle Character Deformation Control"""
        return pos + 1 if pos + 1 < len(data) else pos

    def _handle_wmm(self, data: bytes, pos: int) -> int:
        """Handle Writing Mode Modification"""
        return pos + 1 if pos + 1 < len(data) else pos

    def _handle_time(self, data: bytes, pos: int) -> int:
        """Handle Time Control"""
        return pos + 2 if pos + 2 < len(data) else pos

    def _handle_macro(self, data: bytes, pos: int) -> int:
        """Handle macro execution with stack management"""
        if pos + 1 >= len(data):
            return pos

        macro_id = data[pos + 1]
        if macro_id not in self.macros:
            return pos + 1

        # Prevent excessive recursion
        if len(self.state.macro_stack) >= self.MAX_MACRO_DEPTH:
            return pos + 1

        # Save current state
        saved_state = DecoderState(
            g0=self.state.g0,
            g1=self.state.g1,
            g2=self.state.g2,
            g3=self.state.g3,
            single_shift=self.state.single_shift,
            drcs_maps=self.state.drcs_maps.copy(),
        )

        try:
            # Execute macro
            self.state.macro_stack.append(self.macros[macro_id])
            self.decode(self.macros[macro_id])
        finally:
            # Restore state
            self.state = saved_state
            self.state.macro_stack.pop()

        return pos + 1

    def _handle_rpc(self, data: bytes, pos: int) -> int:
        """Handle Repeat Character"""
        if pos + 1 >= len(data):
            return pos

        repeat_count = data[pos + 1]
        if self.state.buffer and self.state.buffer[-1]:
            last_char = self.state.buffer[-1][-1]
            for _ in range(repeat_count - 1):
                self._insert_character(last_char)

        return pos + 1

    def _handle_stl(self, data: bytes, pos: int) -> int:
        """Handle Start Lining"""
        return pos

    def _handle_spl(self, data: bytes, pos: int) -> int:
        """Handle Stop Lining"""
        return pos

    def _handle_hlc(self, data: bytes, pos: int) -> int:
        """Handle High-Level Control sequence"""
        if pos + 4 >= len(data) or data[pos] != 0x5B or data[pos + 4] != 0x4D:
            return pos
        return pos + 4

    def _handle_csi(self, data: bytes, pos: int) -> int:
        """Handle Control Sequence Introducer"""
        if pos + 1 >= len(data):
            return pos

        current_pos = pos + 2
        params: list[int] = []

        while current_pos < len(data):
            byte = data[current_pos]

            match byte:
                case b if 0x30 <= b <= 0x39:  # Digit
                    param = 0
                    while current_pos < len(data) and 0x30 <= data[current_pos] <= 0x39:
                        param = param * 10 + (data[current_pos] - 0x30)
                        current_pos += 1
                    params.append(param)

                case 0x3B:  # Parameter separator
                    current_pos += 1

                case _:  # Command byte
                    self._handle_csi_command(byte, params)
                    break

        return current_pos

    def _handle_csi_command(self, command: int, params: list[int]) -> None:
        """Handle specific CSI commands with parameters"""
        pass  # Implement specific CSI command handling as needed

    def _handle_flc(self, data: bytes, pos: int) -> int:
        """Handle Flashing Control
        Format: FLC <flash_mode>
        """
        if pos + 1 >= len(data):
            return pos
        flash_mode = data[pos + 1]
        # Set flashing mode
        # self.flash_mode = flash_mode
        return pos + 1

    def _handle_character_set_designation(self, set_byte: int, g_set: int) -> None:
        """Handle character set designation"""
        if set_byte == 0x20:
            self.state.expecting_drcs = True
            return

        char_class = CharacterClass.KANJI
        if self.state.expecting_drcs:
            self.state.expecting_drcs = False
            if 0x40 <= set_byte <= 0x4F:
                char_class = CharacterClass(
                    CharacterClass.DRCS_0.value + (set_byte - 0x40)
                )
        else:
            try:
                char_class = CharacterClass(set_byte)
            except ValueError:
                return

        match g_set:
            case 0:
                self.state.g0 = char_class
            case 1:
                self.state.g1 = char_class
            case 2:
                self.state.g2 = char_class
            case 3:
                self.state.g3 = char_class

    def _insert_character(self, char: str) -> None:
        """Insert character at current position"""
        x, y = self.state.position

        # Ensure buffer has enough rows
        while len(self.state.buffer) <= y:
            self.state.buffer.append([])

        # Ensure current row has enough columns
        line = self.state.buffer[y]
        while len(line) <= x:
            line.append(" ")

        # Insert character and update position
        line[x] = char
        self.state.position = (x + 1, y)

    def reset(self) -> None:
        """Reset decoder state to initial values"""
        self.state = DecoderState()


class AribString:
    """Helper class for building ARIB encoded strings"""

    def __init__(self) -> None:
        self.data = bytearray()

    def add_control(self, code: ControlCode) -> Self:
        """Add control code"""
        self.data.append(code.value)
        return self

    def add_ascii(self, text: str) -> Self:
        """Add ASCII text"""
        self.data.extend(text.encode("ascii"))
        return self

    def set_g0(self, char_class: CharacterClass) -> Self:
        """Set G0 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x28, self._get_character_set_byte(char_class)]
        )
        return self

    def set_g1(self, char_class: CharacterClass) -> Self:
        """Set G1 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x29, self._get_character_set_byte(char_class)]
        )
        return self

    def set_g2(self, char_class: CharacterClass) -> Self:
        """Set G2 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x2A, self._get_character_set_byte(char_class)]
        )
        return self

    def set_g3(self, char_class: CharacterClass) -> Self:
        """Set G3 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x2B, self._get_character_set_byte(char_class)]
        )
        return self

    @staticmethod
    def _get_character_set_byte(char_class: CharacterClass) -> int:
        """Get character set designation byte"""
        match char_class:
            case CharacterClass.KANJI:
                return 0x42
            case CharacterClass.ALPHANUMERIC:
                return 0x4A
            case CharacterClass.HIRAGANA:
                return 0x30
            case CharacterClass.KATAKANA:
                return 0x31
            case CharacterClass.MOSAIC_A:
                return 0x32
            case CharacterClass.MOSAIC_B:
                return 0x33
            case CharacterClass.MOSAIC_C:
                return 0x34
            case CharacterClass.MOSAIC_D:
                return 0x35
            case _ if CharacterClass.DRCS_1 <= char_class <= CharacterClass.DRCS_15:
                return 0x40 + (char_class.value - CharacterClass.DRCS_0.value)
            case _:
                return 0x42  # Default to Kanji

    def get_bytes(self) -> bytes:
        """Get encoded bytes"""
        return bytes(self.data)
