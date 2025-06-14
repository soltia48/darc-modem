import re
import threading
import time
from typing import Final

import serial

from .bit_operations import reverse_bits

_RX_RE: Final[re.Pattern[str]] = re.compile(
    r"rx:\s*([0-9a-f]{2}(?:\s+[0-9a-f]{2})*)",
    re.I,
)


def _parse_rx_hex(line: str) -> bytes:
    m = _RX_RE.search(line)
    if not m:
        raise ValueError(f"No valid 'RX:' line: {line!r}")
    return bytes.fromhex(m.group(1))


_SERIAL_LOCK = threading.Lock()
_SERIAL: serial.Serial | None = None


def _get_serial(
    port: str,
    baudrate: int,
    timeout: float = 0.1,
) -> serial.Serial:
    global _SERIAL
    if _SERIAL is None or not _SERIAL.is_open:
        _SERIAL = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
    return _SERIAL


def descramble(
    block_number: int,
    data: bytes,
    *,
    port: str = "/dev/ttyACM0",
    baudrate: int = 115_200,
    timeout: float = 5.0,
) -> bytes:
    data = reverse_bits(b"\xe0" + block_number.to_bytes(length=1)) + data
    cmd = " ".join(f"{b:02X}" for b in data) + "\r\n"

    with _SERIAL_LOCK:
        ser = _get_serial(port, baudrate, timeout)

        ser.reset_input_buffer()

        ser.write(cmd.encode("ascii"))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line_bytes = ser.readline()
            if not line_bytes:
                continue
            try:
                line = line_bytes.decode("ascii", errors="ignore").strip()
            except UnicodeDecodeError:
                continue

            if line.lower().startswith("rx:"):
                parsed = _parse_rx_hex(line)
                descrambled = parsed[2:]
                return descrambled

        raise TimeoutError(f"descramble(): No 'RX:' line within {timeout}s on {port}")
