from enum import Enum, auto
import unicodedata


class CharacterClass(Enum):
    KANJI = auto()
    ALPHANUMERIC = auto()
    HIRAGANA = auto()
    KATAKANA = auto()
    MOSAIC_A = auto()
    MOSAIC_B = auto()
    MOSAIC_C = auto()
    MOSAIC_D = auto()
    DRCS_0 = auto()
    DRCS_1 = auto()
    DRCS_2 = auto()
    DRCS_3 = auto()
    DRCS_4 = auto()
    DRCS_5 = auto()
    DRCS_6 = auto()
    DRCS_7 = auto()
    DRCS_8 = auto()
    DRCS_9 = auto()
    DRCS_10 = auto()
    DRCS_11 = auto()
    DRCS_12 = auto()
    DRCS_13 = auto()
    DRCS_14 = auto()
    DRCS_15 = auto()


class ControlCode(Enum):
    NUL = 0x00  # Null
    BEL = 0x07  # Bell
    APB = 0x08  # Active Position Backward
    APF = 0x09  # Active Position Forward
    APD = 0x0A  # Active Position Down
    APU = 0x0B  # Active Position Up
    CS = 0x0C  # Clear Screen
    APR = 0x0D  # Active Position Return
    LS1 = 0x0E  # Locking Shift 1
    LS0 = 0x0F  # Locking Shift 0
    PAPF = 0x16  # Parameterized Active Position Forward
    CAN = 0x18  # Cancel
    SS2 = 0x19  # Single Shift 2
    ESC = 0x1B  # Escape
    APS = 0x1C  # Active Position Set
    SS3 = 0x1D  # Single Shift 3
    RS = 0x1E  # Record Separator
    US = 0x1F  # Unit Separator
    SP = 0x20  # Space
    DEL = 0x7F  # Delete


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
            ControlCode.CS: self._handle_cs,
            ControlCode.APR: self._handle_apr,
            ControlCode.LS0: self._handle_ls0,
            ControlCode.LS1: self._handle_ls1,
            ControlCode.PAPF: self._handle_papf,
            ControlCode.SS2: self._handle_ss2,
            ControlCode.SS3: self._handle_ss3,
            ControlCode.ESC: self._handle_esc,
            ControlCode.APS: self._handle_aps,
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

        arib_code = (first_byte << 8) | second_byte
        char = self.kanji_map.get(arib_code)

        if char is None:
            try:
                jis_seq = bytes(
                    [
                        0x1B,
                        0x24,
                        0x42,  # ESC $ B
                        first_byte,
                        second_byte,  # Character bytes
                        0x1B,
                        0x28,
                        0x42,  # ESC ( B
                    ]
                )
                char = jis_seq.decode("iso2022_jp_2004").strip()
                if char and not char.startswith("\x1b"):
                    self.kanji_map[arib_code] = char
                else:
                    char = "〓"
            except UnicodeDecodeError:
                char = "〓"

        return char

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

    def _handle_cs(self, data: bytes, pos: int) -> int:
        """Handle Clear Screen"""
        self.buffer = []
        self.position = (0, 0)
        return pos

    def _handle_apr(self, data: bytes, pos: int) -> int:
        """Handle Active Position Return"""
        x, y = self.position
        self.position = (0, y + 1)
        return pos

    def _handle_ls0(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 0"""
        self.gl = self.g0
        return pos

    def _handle_ls1(self, data: bytes, pos: int) -> int:
        """Handle Locking Shift 1"""
        self.gl = self.g1
        return pos

    def _handle_papf(self, data: bytes, pos: int) -> int:
        """Handle Parameterized Active Position Forward"""
        if pos + 1 >= len(data):
            return pos
        p1 = data[pos + 1]
        x, y = self.position
        self.position = (x + p1, y)
        return pos + 1

    def _handle_ss2(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 2"""
        self.single_shift = self.g2
        return pos

    def _handle_ss3(self, data: bytes, pos: int) -> int:
        """Handle Single Shift 3"""
        self.single_shift = self.g3
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

        return pos + 1

    def _handle_aps(self, data: bytes, pos: int) -> int:
        """Handle Active Position Set"""
        if pos + 2 >= len(data):
            return pos
        p1 = data[pos + 1]
        p2 = data[pos + 2]
        self.position = (p2, p1)
        return pos + 2

    def _handle_character_set_designation(self, set_byte: int, g_set: int) -> None:
        """Handle character set designation"""
        char_class = None

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
                    CharacterClass.DRCS_0.value + (set_byte - 0x40)
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

    def _handle_macro(self, data: bytes, pos: int) -> int:
        """Handle macro execution"""
        if pos + 1 >= len(data):
            return pos

        macro_id = data[pos + 1]
        if macro_id in self.macros:
            macro_data = self.macros[macro_id]
            # Execute macro by processing its data
            self.decode(macro_data)

        return pos + 1

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
            case _ if CharacterClass.DRCS_0 <= char_class <= CharacterClass.DRCS_15:
                return 0x40 + (char_class.value - CharacterClass.DRCS_0.value)
            case _:
                return 0x42  # Default to Kanji

    def get_bytes(self) -> bytes:
        """Get encoded bytes"""
        return bytes(self.data)
