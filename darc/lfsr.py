from typing import Generator


def lfsr(seed: int, polynomial: int) -> Generator[int, None, None]:
    """Galois Linear-Feedback Shift Register

    Args:
        seed (int): Seed
        polynomial (int): Polynomial

    Yields:
        Generator[int, None, None]: LFSR as a Generator
    """

    state = seed
    while True:
        lsb = state & 1
        state >>= 1
        if lsb != 0:
            state ^= polynomial
            yield 1
        else:
            yield 0
