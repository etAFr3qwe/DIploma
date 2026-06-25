from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path


SAMPLE_SOLUTIONS = {
    "equation": {
        "name": "boris_kovalev_oge_equation_attempt_1.png",
        "lines": [
            "Борис Ковалёв, ОГЭ математика",
            "x^2 - 7x + 10 = 0",
            "D = 49 - 40 = 9",
            "x1 = (7 - 3) / 2 = 2",
            "x2 = (7 + 3) / 2 = 5",
            "Ответ: 2; 5",
        ],
        "fallback_lines": [
            "BORIS KOVALEV OGE MATH",
            "X^2 - 7X + 10 = 0",
            "D = 49 - 40 = 9",
            "X1 = (7 - 3) / 2 = 2",
            "X2 = (7 + 3) / 2 = 5",
            "ANSWER: 2; 5",
        ],
    },
    "probability": {
        "name": "boris_kovalev_oge_probability_attempt_1.png",
        "lines": [
            "Борис Ковалёв, вероятность",
            "Синих = 7, зелёных = 5",
            "Всего = 12",
            "Я записал P = 7 / 12",
            "Нужно проверить событие",
            "Ответ: 7/12",
        ],
        "fallback_lines": [
            "BORIS KOVALEV PROBABILITY",
            "BLUE = 7, GREEN = 5",
            "TOTAL = 12",
            "I WROTE P = 7 / 12",
            "CHECK EVENT CAREFULLY",
            "ANSWER: 7/12",
        ],
    },
    "geometry": {
        "name": "boris_kovalev_oge_geometry_attempt_1.png",
        "lines": [
            "Борис Ковалёв, геометрия",
            "Прямоугольный треугольник",
            "9^2 + 12^2 = c^2",
            "81 + 144 = 225",
            "c = sqrt(225)",
            "Ответ записан неразборчиво",
        ],
        "fallback_lines": [
            "BORIS KOVALEV GEOMETRY",
            "RIGHT TRIANGLE",
            "9^2 + 12^2 = C^2",
            "81 + 144 = 225",
            "C = SQRT(225)",
            "ANSWER IS UNCLEAR",
        ],
    },
}


def ensure_sample_handwritten_solutions(upload_dir: str | Path = "uploads/sample") -> dict[str, dict[str, str]]:
    """Create stable PNG files that look like scanned student solutions."""
    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, str]] = {}
    for index, (key, spec) in enumerate(SAMPLE_SOLUTIONS.items(), start=1):
        path = target_dir / spec["name"]
        _write_solution_image(path, spec["lines"], seed=100 + index, fallback_lines=spec["fallback_lines"])
        result[key] = {"path": str(path).replace("\\", "/"), "name": spec["name"]}
    return result


def _write_solution_image(path: Path, lines: list[str], seed: int, fallback_lines: list[str]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont

        rng = random.Random(seed)
        width, height = 1100, 760
        image = Image.new("RGB", (width, height), (248, 250, 247))
        draw = ImageDraw.Draw(image)

        for y in range(60, height - 40, 34):
            draw.line((50, y, width - 50, y), fill=(222, 232, 230), width=1)
        for x in range(70, width - 50, 34):
            draw.line((x, 40, x, height - 50), fill=(236, 242, 241), width=1)

        font = _load_font(30)
        small_font = _load_font(24)
        x_base = 120
        y = 105
        for line in lines:
            x = x_base + rng.randint(-12, 18)
            draw.text((x + 1, y + 1), line, font=font, fill=(210, 218, 218))
            draw.text((x, y), line, font=font, fill=(30, 68, 78))
            if rng.random() > 0.55:
                draw.line((x - 4, y + 34, x + rng.randint(80, 260), y + 35), fill=(35, 86, 96), width=2)
            y += rng.randint(72, 86)

        draw.text((width - 360, height - 80), "попытка сохранена", font=small_font, fill=(110, 130, 130))
        image = image.filter(ImageFilter.GaussianBlur(radius=0.15))
        image = image.rotate(rng.uniform(-0.45, 0.45), resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(248, 250, 247))
        image.save(path, "PNG", optimize=True)
        return
    except Exception:
        _write_basic_png(path, seed, fallback_lines)


def _load_font(size: int):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/segoepr.ttf",
        "C:/Windows/Fonts/segoesc.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _write_basic_png(path: Path, seed: int, lines: list[str]) -> None:
    rng = random.Random(seed)
    width, height = 900, 620
    pixels = bytearray([248, 250, 247] * width * height)

    def set_pixel(x: int, y: int, color: tuple[int, int, int] = (24, 73, 82)) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset : offset + 3] = bytes(color)

    def draw_line(x0: int, y0: int, x1: int, y1: int, thickness: int = 2) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for tx in range(-thickness, thickness + 1):
                for ty in range(-thickness, thickness + 1):
                    set_pixel(x0 + tx, y0 + ty)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    for y in range(55, height - 40, 32):
        for x in range(45, width - 45):
            set_pixel(x, y, (226, 235, 233))
    for y in range(95, height - 90, 72):
        x = 95 + rng.randint(-10, 18)
        draw_line(x, y, x + 520 + rng.randint(-40, 50), y + rng.randint(-6, 8), 1)
        draw_line(x + 30, y + 28, x + 390 + rng.randint(-30, 60), y + 24 + rng.randint(-6, 8), 1)
    draw_line(95, height - 110, 420, height - 112, 2)

    y = 95
    for line in lines:
        _draw_bitmap_text(set_pixel, 95 + rng.randint(-5, 10), y + rng.randint(-3, 4), line, scale=4)
        y += 74

    raw_rows = []
    row_size = width * 3
    for y in range(height):
        start = y * row_size
        raw_rows.append(b"\x00" + bytes(pixels[start : start + row_size]))
    raw = b"".join(raw_rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, level=9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


FONT_5X7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "=": ["00000", "11111", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "^": ["00100", "01010", "10001", "00000", "00000", "00000", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    ";": ["00000", "00100", "00100", "00000", "00100", "00100", "01000"],
    ",": ["00000", "00000", "00000", "00000", "00100", "00100", "01000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00100", "00100"],
}


def _draw_bitmap_text(set_pixel, x: int, y: int, text: str, scale: int = 3) -> None:
    cursor = x
    color = (25, 70, 80)
    for char in text.upper():
        if char == " ":
            cursor += 4 * scale
            continue
        pattern = FONT_5X7.get(char)
        if pattern is None:
            cursor += 4 * scale
            continue
        for row_index, row in enumerate(pattern):
            for col_index, value in enumerate(row):
                if value == "1":
                    for dx in range(scale):
                        for dy in range(scale):
                            set_pixel(cursor + col_index * scale + dx, y + row_index * scale + dy, color)
        cursor += 7 * scale


if __name__ == "__main__":
    created = ensure_sample_handwritten_solutions()
    for item in created.values():
        print(item["path"])
