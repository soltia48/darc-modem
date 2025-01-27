from enum import Enum, auto
from importlib.resources import files
import unicodedata


class CharacterClass(Enum):
    KANJI = 1
    ALPHANUMERIC = 2
    HIRAGANA = 3
    KATAKANA = 4
    MOSAIC_A = 5
    MOSAIC_B = 6
    MOSAIC_C = 7
    MOSAIC_D = 8
    MACRO = 9
    DRCS_1 = 10
    DRCS_2 = 11
    DRCS_3 = 12
    DRCS_4 = 13
    DRCS_5 = 14
    DRCS_6 = 15
    DRCS_7 = 16
    DRCS_8 = 17
    DRCS_9 = 18
    DRCS_10 = 19
    DRCS_11 = 20
    DRCS_12 = 21
    DRCS_13 = 22
    DRCS_14 = 23
    DRCS_15 = 24


class ControlCode(Enum):
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


class AribDecoder:
    def __init__(self) -> None:
        self.reset_state()
        self._init_character_sets()
        self._init_control_sequences()
        self._init_macros()

    def reset_state(self) -> None:
        """Reset decoder state to initial values"""
        self.g0 = CharacterClass.KANJI
        self.g1 = CharacterClass.ALPHANUMERIC
        self.g2 = CharacterClass.HIRAGANA
        self.g3 = CharacterClass.KATAKANA
        self.gl = self.g0  # Left side G set
        self.gr = self.g2  # Right side G set
        self.single_shift: CharacterClass | None = None
        self.drcs_maps: dict[CharacterClass, dict[int, str]] = {}
        self.position: tuple[int, int] = (0, 0)
        self.buffer: list[list[str]] = []

    def _init_character_sets(self) -> None:
        """Initialize character set mapping tables"""
        # Kanji mapping (JIS X 0213:2004)
        self.kanji_map: dict[int, str] = self._create_kanji_map()

        # Alphanumeric mapping
        self.alphanumeric_map: dict[int, str] = {i: chr(i) for i in range(0x21, 0x7F)}

        # Hiragana mapping
        self.hiragana_map: dict[int, str] = self._create_hiragana_map()

        # Katakana mapping
        self.katakana_map: dict[int, str] = self._create_katakana_map()

        # Mosaic mapping
        self.mosaic_maps: dict[CharacterClass, dict[int, str]] = {
            CharacterClass.MOSAIC_A: {},
            CharacterClass.MOSAIC_B: {},
            CharacterClass.MOSAIC_C: {},
            CharacterClass.MOSAIC_D: {},
        }

    def _create_kanji_map(self) -> dict[int, str]:
        """Initialize using JIS X 0213:2004 standard mappings"""
        kanji_map: dict[int, str] = {}

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

    def _create_hiragana_map(self) -> dict[int, str]:
        """Generate hiragana mapping"""
        hiragana_map: dict[int, str] = {}

        # Map using Unicode ranges
        hiragana_start = 0x3041  # Unicode for ぁ
        arib_start = 0x21

        # Map ARIB codes to Unicode hiragana
        for i in range(83):  # Total number of hiragana characters in ARIB
            unicode_char = chr(hiragana_start + i)
            if unicodedata.category(unicode_char).startswith("Lo"):
                hiragana_map[arib_start + i] = unicode_char

        # Add special cases
        hiragana_map[0x52] = "ゔ"

        return hiragana_map

    def _create_katakana_map(self) -> dict[int, str]:
        """Generate katakana mapping"""
        katakana_map: dict[int, str] = {}

        # Map using Unicode ranges
        katakana_start = 0x30A1  # Unicode for ァ
        arib_start = 0x21

        # Map ARIB codes to Unicode katakana
        for i in range(83):
            unicode_char = chr(katakana_start + i)
            if unicodedata.category(unicode_char).startswith("Lo"):
                katakana_map[arib_start + i] = unicode_char

        # Add special cases
        katakana_map[0x52] = "ヴ"

        return katakana_map

    def _init_control_sequences(self) -> None:
        """Initialize control sequence handlers"""
        self.control_handlers: dict[ControlCode, type[bytes | int]] = {
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
            ControlCode.CDC: self._handle_wmm,
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

    def decode(self, data: bytes) -> str:
        """Decode ARIB STD-B3 encoded bytes into Unicode text"""
        result: list[str] = []
        i = 0

        while i < len(data):
            byte = data[i]

            # Handle control codes
            if byte <= 0x20 or byte == 0x7F:
                handler = self.control_handlers.get(ControlCode(byte))
                if handler:
                    i = handler(data, i)
                i += 1
                continue

            # Handle character sets
            if byte < 0x80:  # GL area
                char_set = self.gl
                if self.single_shift:
                    char_set = self.single_shift
                    self.single_shift = None
            else:  # GR area
                char_set = self.gr
                byte &= 0x7F

            # Handle Kanji (2-byte character)
            if char_set == CharacterClass.KANJI:
                if i + 1 >= len(data):
                    break

                first_byte = byte
                second_byte = data[i + 1]
                char = self._decode_kanji(first_byte, second_byte)
                i += 2
            else:
                # Handle single-byte character sets
                char = self._decode_single_byte(byte, char_set)
                i += 1

            result.append(char)

        return "".join(result)

    def _decode_kanji(self, first_byte: int, second_byte: int) -> str:
        """Decode a kanji character from two bytes"""
        if not (0x21 <= first_byte <= 0x7E and 0x21 <= second_byte <= 0x7E):
            return "〓"

        # Check cacheed kanji
        arib_code = (first_byte << 8) | second_byte
        if arib_code in self.kanji_map:
            return self.kanji_map[arib_code]

        try:
            # Detect JIS X 0213 plane
            plane = 1
            if 0x21 <= first_byte <= 0x2F:
                plane = 1
            elif 0x75 <= first_byte <= 0x7E:
                plane = 2

            # Use JIS X 0213 encoding
            if plane == 1:
                jis_seq = bytes(
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
                jis_seq = bytes(
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

            char = jis_seq.decode("iso2022_jp_2004").strip()
            if char and not char.startswith("\x1b"):
                self.kanji_map[arib_code] = char
                return char
        except UnicodeDecodeError:
            pass

        return "〓"

    def _decode_single_byte(self, byte: int, char_set: CharacterClass) -> str:
        """Decode a single byte according to the specified character set"""
        match char_set:
            case CharacterClass.ALPHANUMERIC:
                return self.alphanumeric_map.get(byte, "?")
            case CharacterClass.HIRAGANA:
                return self.hiragana_map.get(byte, "?")
            case CharacterClass.KATAKANA:
                return self.katakana_map.get(byte, "?")
            case (
                CharacterClass.MOSAIC_A
                | CharacterClass.MOSAIC_B
                | CharacterClass.MOSAIC_C
                | CharacterClass.MOSAIC_D
            ):
                return self.mosaic_maps[char_set].get(byte, "?")
            case _ if CharacterClass.DRCS_0 <= char_set <= CharacterClass.DRCS_15:
                drcs_map = self.drcs_maps.get(char_set, {})
                return drcs_map.get(byte, "?")
            case _:
                return "?"

    # Control code handlers remain mostly the same, just updating type hints
    def _handle_apb(self, data: bytes, pos: int) -> int:
        """Handle Active Position Backward"""
        x, y = self.position
        self.position = (max(0, x - 1), y)
        return pos

    def _handle_apf(self, data: bytes, pos: int) -> int:
        """Handle Active Position Forward"""
        x, y = self.position
        self.position = (x + 1, y)
        return pos

    def _handle_apd(self, data: bytes, pos: int) -> int:
        """Handle Active Position Down"""
        x, y = self.position
        self.position = (x, y + 1)
        return pos

    def _handle_apu(self, data: bytes, pos: int) -> int:
        """Handle Active Position Up"""
        x, y = self.position
        self.position = (x, max(0, y - 1))
        return pos

    def _handle_apr(self, data: bytes, pos: int) -> int:
        """Handle Active Position Return"""
        x, y = self.position
        self.position = (0, y + 1)
        return pos

    def _handle_papf(self, data: bytes, pos: int) -> int:
        """Handle Parameterized Active Position Forward"""
        if pos + 1 >= len(data):
            return pos
        p1 = data[pos + 1]
        if p1 >= 0x80:
            p1 &= 0x7F
        x, y = self.position
        self.position = (x + p1, y)
        return pos + 1

    def _handle_aps(self, data: bytes, pos: int) -> int:
        """Handle Active Position Set"""
        if pos + 2 >= len(data):
            return pos
        p1 = data[pos + 1]
        p2 = data[pos + 2]
        self.position = (p2, p1)
        return pos + 2

    def _handle_cs(self, data: bytes, pos: int) -> int:
        """Handle Clear Screen"""
        self.buffer = []
        self.position = (0, 0)
        return pos

    def _handle_esc(self, data: bytes, pos: int) -> int:
        """Handle Escape sequences"""
        if pos + 1 >= len(data):
            return pos

        next_byte = data[pos + 1]
        if next_byte == 0x24:  # 2-byte character set
            if pos + 2 >= len(data):
                return pos
            set_byte = data[pos + 2]
            self._handle_character_set_designation(set_byte, 2)
            return pos + 2
        elif next_byte == 0x28:  # G0 designation
            if pos + 2 >= len(data):
                return pos
            set_byte = data[pos + 2]
            self._handle_character_set_designation(set_byte, 0)
            return pos + 2
        elif next_byte == 0x29:  # G1 designation
            if pos + 2 >= len(data):
                return pos
            set_byte = data[pos + 2]
            self._handle_character_set_designation(set_byte, 1)
            return pos + 2
        elif next_byte == 0x2A:  # G2 designation
            if pos + 2 >= len(data):
                return pos
            set_byte = data[pos + 2]
            self._handle_character_set_designation(set_byte, 2)
            return pos + 2
        elif next_byte == 0x2B:  # G3 designation
            if pos + 2 >= len(data):
                return pos
            set_byte = data[pos + 2]
            self._handle_character_set_designation(set_byte, 3)
            return pos + 2
        elif next_byte == 0x6E:  # LS2
            self.gl = self.g2
            return pos + 1
        elif next_byte == 0x6F:  # LS3
            self.gl = self.g3
            return pos + 1
        elif next_byte == 0x7E:  # LS1R
            self.gr = self.g1
            return pos + 1
        elif next_byte == 0x7D:  # LS2R
            self.gr = self.g2
            return pos + 1
        elif next_byte == 0x7C:  # LS3R
            self.gr = self.g3
            return pos + 1

        return pos + 1

    def _handle_ls1(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 1"""
        self.gl = self.g1
        # Reset character set
        self.single_shift = None
        return pos

    def _handle_ls0(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 0"""
        self.gl = self.g0
        # Reset character set
        self.single_shift = None
        return pos

    def _handle_ss2(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 2"""
        self.single_shift = self.g2
        return pos

    def _handle_ss3(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 3"""
        self.single_shift = self.g3
        return pos

    def _handle_col(self, data: bytes, pos: int) -> int:
        """Handle Color Control
        Format: COL <color_params>
        """
        if pos + 1 >= len(data):
            return pos
        color_param = data[pos + 1]
        # Set text color based on parameter
        # self.current_color = color_param
        return pos + 1

    def _handle_pol(self, data: bytes, pos: int) -> int:
        """Handle Pattern Polarity Control
        Format: POL <polarity>
        """
        if pos + 1 >= len(data):
            return pos
        polarity = data[pos + 1]
        # Set pattern polarity (normal/reverse)
        # self.pattern_polarity = polarity
        return pos + 1

    def _handle_szx(self, data: bytes, pos: int) -> int:
        """
        Handle Set Character Size (SZX) control code
        Format: SZX <size>
        """
        if pos + 1 >= len(data):
            return pos

        size_param = data[pos + 1]
        return pos + 1

    def _handle_cdc(self, data: bytes, pos: int) -> int:
        """Handle Character Deformation Control
        Format: CDC <deformation>
        """
        if pos + 1 >= len(data):
            return pos
        deformation = data[pos + 1]
        # Set character deformation (normal/deformed)
        # self.char_deformation = deformation
        return pos + 1

    def _handle_wmm(self, data: bytes, pos: int) -> int:
        """
        Handle Writing Mode Modification control code
        Format: CDC <direction>
        """
        if pos + 1 >= len(data):
            return pos

        return pos + 1

    def _handle_time(self, data: bytes, pos: int) -> int:
        """Handle Time control code
        Format: TIME <hour> <minute>
        """
        if pos + 2 >= len(data):
            return pos
        hour = data[pos + 1]
        minute = data[pos + 2]
        # Store time information if needed
        # self.current_time = (hour, minute)
        return pos + 2

    def _handle_macro(self, data: bytes, pos: int) -> int:
        """Handle macro execution"""
        if pos + 2 >= len(data):
            return pos

        macro_id = data[pos + 1]
        macro_control = data[pos + 2]

        if macro_control == 0x40:  # 開始
            self.macro_buffer = bytearray()
            self.recording_macro = macro_id
        elif macro_control == 0x41:  # 終了
            if hasattr(self, "recording_macro") and self.recording_macro == macro_id:
                self.macros[macro_id] = bytes(self.macro_buffer)
                delattr(self, "recording_macro")
        elif macro_control == 0x42:  # 実行
            if macro_id in self.macros:
                self.decode(self.macros[macro_id])

        return pos + 2

    def _handle_rpc(self, data: bytes, pos: int) -> int:
        """Handle Repeat Character
        Format: RPC <count>
        """
        if pos + 1 >= len(data):
            return pos
        repeat_count = data[pos + 1]

        # If there's a previous character, repeat it
        if self.buffer and self.buffer[-1]:
            last_char = self.buffer[-1][-1]
            for _ in range(repeat_count - 1):  # -1 because one instance already exists
                self.insert_character(last_char)

        return pos + 1

    def _handle_stl(self, data: bytes, pos: int) -> int:
        """Handle Start Lining
        Format: STL
        """
        # Start underlining or other line decorations
        # self.lining_mode = True
        return pos

    def _handle_spl(self, data: bytes, pos: int) -> int:
        """Handle Stop Lining
        Format: SPL
        """
        # Stop underlining or other line decorations
        # self.lining_mode = False
        return pos

    def _handle_hlc(self, data: bytes, pos: int) -> int:
        """Handle High-Level Control sequence
        Format: HLC <classification> <instruction1> <instruction2>
        """
        if pos + 4 >= len(data):
            return pos

        # Check if this is a valid HLC sequence (ESC [ ... M)
        if data[pos] != 0x5B or data[pos + 4] != 0x4D:
            return pos

        p1 = data[pos + 1]  # Classification
        p2 = data[pos + 2]  # Instruction 1
        p3 = data[pos + 3]  # Instruction 2

        return pos + 4

    def _handle_csi(self, data: bytes, pos: int) -> int:
        """Handle Control Sequence Introducer
        Format: CSI <params> <command>
        """
        if pos + 1 >= len(data):
            return pos

        # Skip CSI bytes (0x1B 0x5B)
        current_pos = pos + 2
        params: list[int] = []

        # Parse parameters until command byte
        while current_pos < len(data):
            byte = data[current_pos]
            if 0x30 <= byte <= 0x39:  # Digit
                param = 0
                while current_pos < len(data) and 0x30 <= data[current_pos] <= 0x39:
                    param = param * 10 + (data[current_pos] - 0x30)
                    current_pos += 1
                params.append(param)
            elif byte == 0x3B:  # Parameter separator
                current_pos += 1
                continue
            else:  # Command byte
                command = byte
                # Handle CSI command with params
                self._handle_csi_command(command, params)
                break

        return current_pos

    def _handle_csi_command(self, command: int, params: list[int]) -> None:
        """Handle specific CSI commands with parameters"""
        # Implement specific CSI command handling here
        pass

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
        char_class = None
        set_byte &= 0x7F

        match set_byte:
            case 0x42:  # Kanji
                char_class = CharacterClass.KANJI
            case 0x4A:  # Alphanumeric
                char_class = CharacterClass.ALPHANUMERIC
            case 0x30:  # Hiragana
                char_class = CharacterClass.HIRAGANA
            case 0x31:  # Katakana
                char_class = CharacterClass.KATAKANA
            case 0x32:  # Mosaic A
                char_class = CharacterClass.MOSAIC_A
            case 0x33:  # Mosaic B
                char_class = CharacterClass.MOSAIC_B
            case 0x34:  # Mosaic C
                char_class = CharacterClass.MOSAIC_C
            case 0x35:  # Mosaic D
                char_class = CharacterClass.MOSAIC_D
            case _ if 0x40 <= set_byte <= 0x4F:  # DRCS
                char_class = CharacterClass(
                    CharacterClass.DRCS_1.value + (set_byte - 0x40)
                )

        if char_class is not None:
            match g_set:
                case 0:
                    self.g0 = char_class
                case 1:
                    self.g1 = char_class
                case 2:
                    self.g2 = char_class
                case 3:
                    self.g3 = char_class

    def load_drcs(
        self, drcs_class: CharacterClass, drcs_data: dict[int, bytes]
    ) -> None:
        """
        Load DRCS pattern data for a specific DRCS character set

        Args:
            drcs_class: The DRCS character class to load
            drcs_data: Dictionary mapping character codes to pattern data
        """
        if CharacterClass.DRCS_0 <= drcs_class <= CharacterClass.DRCS_15:
            self.drcs_maps[drcs_class] = drcs_data

    def register_macro(self, macro_id: int, macro_data: bytes) -> None:
        """
        Register a new macro definition

        Args:
            macro_id: Identifier for the macro
            macro_data: Bytes containing the macro definition
        """
        self.macros[macro_id] = macro_data

    def insert_character(self, char: str) -> None:
        """Insert character at current position"""
        x, y = self.position
        while len(self.buffer) <= y:
            self.buffer.append([])
        line = self.buffer[y]
        while len(line) <= x:
            line.append(" ")
        line[x] = char
        self.position = (x + 1, y)

    @staticmethod
    def is_control_code(byte: int) -> bool:
        """Check if byte is a control code"""
        return byte <= 0x20 or byte == 0x7F

    @staticmethod
    def is_gl_code(byte: int) -> bool:
        """Check if byte is in GL area"""
        return 0x21 <= byte <= 0x7E

    @staticmethod
    def is_gr_code(byte: int) -> bool:
        """Check if byte is in GR area"""
        return 0xA1 <= byte <= 0xFE


class AribString:
    """Helper class for building ARIB encoded strings"""

    def __init__(self) -> None:
        self.data: bytearray = bytearray()

    def add_control(self, code: ControlCode) -> None:
        """Add control code"""
        self.data.append(code.value)

    def add_ascii(self, text: str) -> None:
        """Add ASCII text"""
        self.data.extend(text.encode("ascii"))

    def set_g0(self, char_class: CharacterClass) -> None:
        """Set G0 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x28, self._get_character_set_byte(char_class)]
        )

    def set_g1(self, char_class: CharacterClass) -> None:
        """Set G1 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x29, self._get_character_set_byte(char_class)]
        )

    def set_g2(self, char_class: CharacterClass) -> None:
        """Set G2 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x2A, self._get_character_set_byte(char_class)]
        )

    def set_g3(self, char_class: CharacterClass) -> None:
        """Set G3 character set"""
        self.data.extend(
            [ControlCode.ESC.value, 0x2B, self._get_character_set_byte(char_class)]
        )

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
