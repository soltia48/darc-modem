import enum
from typing import Any, TypeVar

from bitstring import ConstBitStream, ReadError

from .arib_string import AribStringDecoder

TEnum = TypeVar("TEnum", bound="SafeIntEnumMixin")


class SafeIntEnumMixin(enum.IntEnum):
    """IntEnum that never raises *ValueError* on construction.

    When an undefined integer value is supplied, ``UNKNOWN`` is returned if the
    subclass defines it; otherwise the first declared member is used as a
    fallback. This behaviour enables loss-tolerant parsing - decoders can keep
    working even when the upstream source introduces new values.
    """

    @classmethod
    def _missing_(cls: type[TEnum], value: Any) -> TEnum:
        return getattr(cls, "UNKNOWN", next(iter(cls)))  # type: ignore[arg-type]


class BitstreamParseError(RuntimeError):
    """Raised when the bitstream ends unexpectedly while parsing a field."""


class BitReader:
    """Small convenience wrapper around :class:`bitstring.ConstBitStream`.

    It removes boilerplate *try/except* blocks and exposes only the operations
    required by the decoders - keeping the public surface minimal helps avoid
    misuse.
    """

    def __init__(self, bs: ConstBitStream) -> None:
        self._bs = bs

    # ------------------------------------------------------------------ #
    # Primitive reads                                                    #
    # ------------------------------------------------------------------ #
    def u(self, bits: int) -> int:
        """Read an **unsigned** integer of *bits* length."""
        try:
            return self._bs.read(f"uint:{bits}")
        except ReadError as err:
            raise BitstreamParseError("unexpected end of stream") from err

    def flag(self) -> bool:
        """Read a single-bit boolean."""
        return bool(self.u(1))

    def readlist(self, fmt: str) -> tuple[Any, ...]:
        """Read a list per *fmt* and return it as a tuple.

        Returning tuples keeps type checkers happy because the callers usually
        immediately unpack the result.
        """
        try:
            return tuple(self._bs.readlist(fmt))  # type: ignore[arg-type]
        except ReadError as err:
            raise BitstreamParseError("unexpected end of stream") from err

    # ------------------------------------------------------------------ #
    # Properties                                                         #
    # ------------------------------------------------------------------ #
    @property
    def pos(self) -> int:
        """Current read position in *bits*."""
        return self._bs.pos

    @pos.setter
    def pos(self, value: int) -> None:
        self._bs.pos = value

    @property
    def len(self) -> int:
        """Total length of the underlying stream in *bits*."""
        return self._bs.len

    # ------------------------------------------------------------------ #
    # Convenience                                                        #
    # ------------------------------------------------------------------ #
    def align_byte(self) -> None:
        """Advance the cursor to the next byte boundary if not already aligned."""
        mis = self.pos % 8
        if mis:
            self._bs.read(f"pad:{8 - mis}")


# --------------------------------------------------------------------------- #
# Units with built-in conversion helpers                                      #
# --------------------------------------------------------------------------- #
class DistanceUnit(SafeIntEnumMixin):
    """Distance step used by several extensions."""

    TEN_M = 0
    HUNDRED_M = 1
    ONE_KM = 2
    UNDEFINED = 3

    def decode(self, raw: int) -> int | None:
        """Convert *raw* value to **metres** or return *None* when undefined."""
        if self is DistanceUnit.TEN_M:
            return raw * 10
        if self is DistanceUnit.HUNDRED_M:
            return raw * 100
        if self is DistanceUnit.ONE_KM:
            return raw * 1_000
        return None


class TimeUnit(SafeIntEnumMixin):
    """Time step used by travel-time extensions."""

    SEC_10 = 0
    MINUTE = 1

    def decode(self, raw: int) -> int | None:
        """Convert *raw* value to **seconds** or *None* when reserved/unknown."""
        if raw in (0, 126, 127):
            return None
        mult = 10 if self is TimeUnit.SEC_10 else 60
        return raw * mult


class LinkType(SafeIntEnumMixin):
    """Logical road link category used by multiple data units."""

    EXPRESSWAY = 0
    URBAN_EXPRESSWAY = 1
    ARTERIAL = 2
    OTHER = 3


# --------------------------------------------------------------------------- #
# ARIB string helper                                                          #
# --------------------------------------------------------------------------- #


def read_name(reader: BitReader) -> str:
    """Read a length-prefixed ARIB string from *reader*.

    Format: 1-byte length in **bytes**, followed by *length* bytes encoded per
    ARIB STD-B24. Returns an empty string when *length* equals zero.
    """
    length = reader.u(8)
    if length == 0:
        return ""
    data = reader._bs.read(length * 8).bytes  # type: ignore[attr-defined]
    return AribStringDecoder().decode(data)
