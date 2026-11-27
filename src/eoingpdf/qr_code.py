"""Offline pure-Python ISO/IEC 18004 QR code generator (Byte mode, EC level M)."""
from __future__ import annotations

import io
from PIL import Image

from .localization import tr

# Version -> (size, total_data_codewords, ec_per_block, group1_blocks, group1_data, group2_blocks, group2_data, alignment_centers)
_VERSIONS = {
    1: (21, 16, 10, 1, 16, 0, 0, ()),
    2: (25, 28, 16, 1, 28, 0, 0, (6, 18)),
    3: (29, 44, 26, 1, 44, 0, 0, (6, 22)),
    4: (33, 64, 18, 2, 32, 0, 0, (6, 26)),
    5: (37, 86, 24, 2, 43, 0, 0, (6, 30)),
    6: (41, 108, 16, 4, 27, 0, 0, (6, 34)),
    7: (45, 124, 18, 4, 31, 0, 0, (6, 22, 38)),
    8: (49, 154, 22, 2, 38, 2, 39, (6, 24, 42)),
    9: (53, 182, 22, 3, 36, 2, 37, (6, 26, 46)),
    10: (57, 216, 26, 4, 43, 1, 44, (6, 28, 50)),
}

_REMAINDER_BITS = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_val = 1
for _i in range(255):
    _GF_EXP[_i] = _val
    _GF_EXP[_i + 255] = _val
    _GF_LOG[_val] = _i
    _val <<= 1
    if _val & 0x100:
        _val ^= 0x11D


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        factor = _GF_EXP[i]
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, factor)
        poly = nxt
    return poly


def _rs_encode(data: list[int], ec_count: int) -> list[int]:
    gen = _rs_generator(ec_count)
    rem = list(data) + [0] * ec_count
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gf_mul(gen[j], coef)
    return rem[len(data):]


def _choose_version(byte_len: int) -> int:
    for version in range(1, 11):
        _, total_dc, *_ = _VERSIONS[version]
        count_bits = 8 if version <= 9 else 16
        capacity = (total_dc * 8 - 4 - count_bits) // 8
        if byte_len <= capacity:
            return version
    raise ValueError(tr('QR 코드 내용이 너무 깁니다. 213바이트 이하로 입력해 주세요.'))


def _encode_codewords(payload: bytes, version: int) -> list[int]:
    _, total_dc, ec_per_block, g1_blocks, g1_data, g2_blocks, g2_data, _ = _VERSIONS[version]
    count_bits = 8 if version <= 9 else 16
    bits: list[int] = []

    def push(val: int, length: int) -> None:
        for shift in range(length - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push(0b0100, 4)
    push(len(payload), count_bits)
    for byte in payload:
        push(byte, 8)
    max_bits = total_dc * 8
    term = min(4, max_bits - len(bits))
    push(0, term)
    while len(bits) % 8:
        bits.append(0)
    data = [int(''.join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad_bytes = (0xEC, 0x11)
    idx = 0
    while len(data) < total_dc:
        data.append(pad_bytes[idx % 2])
        idx += 1

    blocks_data: list[list[int]] = []
    blocks_ec: list[list[int]] = []
    cursor = 0
    for count, size in ((g1_blocks, g1_data), (g2_blocks, g2_data)):
        for _ in range(count):
            block = data[cursor:cursor + size]
            cursor += size
            blocks_data.append(block)
            blocks_ec.append(_rs_encode(block, ec_per_block))

    interleaved: list[int] = []
    max_data_len = max(len(b) for b in blocks_data)
    for i in range(max_data_len):
        for b in blocks_data:
            if i < len(b):
                interleaved.append(b[i])
    for i in range(ec_per_block):
        for ec in blocks_ec:
            interleaved.append(ec[i])
    return interleaved


def _place_finder(grid: list[list[int | None]], reserved: list[list[bool]], r0: int, c0: int) -> None:
    size = len(grid)
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = r0 + dr, c0 + dc
            if not (0 <= r < size and 0 <= c < size):
                continue
            reserved[r][c] = True
            if dr in (-1, 7) or dc in (-1, 7):
                grid[r][c] = 0
            elif dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4):
                grid[r][c] = 1
            else:
                grid[r][c] = 0


def _place_alignment(grid: list[list[int | None]], reserved: list[list[bool]], r0: int, c0: int) -> None:
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            r, c = r0 + dr, c0 + dc
            reserved[r][c] = True
            grid[r][c] = 1 if max(abs(dr), abs(dc)) in (0, 2) else 0


def _build_base_matrix(version: int) -> tuple[list[list[int | None]], list[list[bool]]]:
    size, *_rest, centers = _VERSIONS[version]
    grid: list[list[int | None]] = [[None] * size for _ in range(size)]
    reserved: list[list[bool]] = [[False] * size for _ in range(size)]

    _place_finder(grid, reserved, 0, 0)
    _place_finder(grid, reserved, 0, size - 7)
    _place_finder(grid, reserved, size - 7, 0)

    for r in centers:
        for c in centers:
            if reserved[r][c]:
                continue
            _place_alignment(grid, reserved, r, c)

    for i in range(8, size - 8):
        bit = 1 if i % 2 == 0 else 0
        if not reserved[6][i]:
            grid[6][i] = bit
            reserved[6][i] = True
        if not reserved[i][6]:
            grid[i][6] = bit
            reserved[i][6] = True

    grid[4 * version + 9][8] = 1
    reserved[4 * version + 9][8] = True

    for i in range(9):
        if i != 6:
            reserved[8][i] = True
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
    for i in range(7):
        reserved[size - 1 - i][8] = True

    if version >= 7:
        for i in range(6):
            for j in range(3):
                reserved[i][size - 11 + j] = True
                reserved[size - 11 + j][i] = True
    return grid, reserved


def _format_bits(mask_id: int) -> int:
    # EC level M = 0b00
    data = (0b00 << 3) | mask_id
    rem = data << 10
    gen = 0b10100110111
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= gen << (i - 10)
    return ((data << 10) | rem) ^ 0b101010000010010


def _version_bits(version: int) -> int:
    rem = version << 12
    gen = 0b1111100100101
    for i in range(17, 11, -1):
        if rem & (1 << i):
            rem ^= gen << (i - 12)
    return (version << 12) | rem


def _apply_format_and_version(grid: list[list[int]], version: int, mask_id: int) -> None:
    size = len(grid)
    fmt = _format_bits(mask_id)
    coords_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    coords_b = [(size - 1 - i, 8) for i in range(7)] + [(8, size - 8 + i) for i in range(8)]
    for i in range(15):
        bit = (fmt >> (14 - i)) & 1
        r1, c1 = coords_a[i]
        r2, c2 = coords_b[i]
        grid[r1][c1] = bit
        grid[r2][c2] = bit
    if version >= 7:
        vb = _version_bits(version)
        for i in range(18):
            bit = (vb >> i) & 1
            r = i // 3
            c = size - 11 + (i % 3)
            grid[r][c] = bit
            grid[c][r] = bit


def _mask_condition(mask_id: int, r: int, c: int) -> bool:
    if mask_id == 0:
        return (r + c) % 2 == 0
    if mask_id == 1:
        return r % 2 == 0
    if mask_id == 2:
        return c % 3 == 0
    if mask_id == 3:
        return (r + c) % 3 == 0
    if mask_id == 4:
        return (r // 2 + c // 3) % 2 == 0
    if mask_id == 5:
        return (r * c) % 2 + (r * c) % 3 == 0
    if mask_id == 6:
        return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


def _penalty(grid: list[list[int]]) -> int:
    size = len(grid)
    score = 0
    for line in list(grid) + [[grid[r][c] for r in range(size)] for c in range(size)]:
        run = 1
        for i in range(1, size):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for r in range(size - 1):
        for c in range(size - 1):
            val = grid[r][c]
            if val == grid[r][c + 1] == grid[r + 1][c] == grid[r + 1][c + 1]:
                score += 3
    for line in list(grid) + [[grid[r][c] for r in range(size)] for c in range(size)]:
        for i in range(size - 10):
            seg = line[i:i + 11]
            if seg == [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0] or seg == [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]:
                score += 40
    dark = sum(sum(row) for row in grid)
    percent = dark * 100 / (size * size)
    prev5 = int(percent // 5) * 5
    next5 = prev5 + 5
    score += min(abs(prev5 - 50), abs(next5 - 50)) * 2
    return score


def make_qr_matrix(text: str) -> list[list[int]]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(tr('QR 코드에 넣을 내용을 입력해 주세요.'))
    payload = text.encode('utf-8')
    version = _choose_version(len(payload))
    codewords = _encode_codewords(payload, version)
    stream_bits: list[int] = []
    for cw in codewords:
        for shift in range(7, -1, -1):
            stream_bits.append((cw >> shift) & 1)
    stream_bits.extend([0] * _REMAINDER_BITS[version])

    base, reserved = _build_base_matrix(version)
    size = len(base)
    bit_idx = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not reserved[r][c]:
                    base[r][c] = stream_bits[bit_idx] if bit_idx < len(stream_bits) else 0
                    bit_idx += 1
        upward = not upward
        col -= 2

    best_grid = None
    best_score = None
    for mask_id in range(8):
        candidate = [
            [
                (base[r][c] ^ 1 if (not reserved[r][c] and _mask_condition(mask_id, r, c)) else int(base[r][c] or 0))
                for c in range(size)
            ]
            for r in range(size)
        ]
        _apply_format_and_version(candidate, version, mask_id)
        score = _penalty(candidate)
        if best_score is None or score < best_score:
            best_score = score
            best_grid = candidate
    return best_grid


def make_qr_png(text: str, module_px: int = 10, quiet: int = 4) -> bytes:
    matrix = make_qr_matrix(text)
    n = len(matrix)
    side = (n + quiet * 2) * module_px
    image = Image.new('RGB', (side, side), 'white')
    pixels = image.load()
    for r, row in enumerate(matrix):
        for c, val in enumerate(row):
            if val:
                y0 = (r + quiet) * module_px
                x0 = (c + quiet) * module_px
                for dy in range(module_px):
                    for dx in range(module_px):
                        pixels[x0 + dx, y0 + dy] = (0, 0, 0)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
