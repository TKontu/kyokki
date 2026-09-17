"""Render the Kyokki mark to PNG with no third-party dependencies.

The mark: a white fridge on the brand-blue ground, a divider between freezer and fridge, and
a handle on each door. Drawn at 4x and box-downsampled so the rounded corners are smooth.
"""
import pathlib, struct, zlib

BRAND = (0x22, 0x8b, 0xe6)
WHITE = (0xff, 0xff, 0xff)
SS = 4  # supersampling factor


def rounded_rect(x, y, w, h, r):
    """Predicate: is the point inside this rounded rectangle?

    Clamp the point into the inner rectangle and measure the distance to that clamped
    point - the standard rounded-rect distance test, correct at every corner.
    """
    def inside(px, py):
        if px < x or px > x + w or py < y or py > y + h:
            return False
        cx = min(max(px, x + r), x + w - r)
        cy = min(max(py, y + r), y + h - r)
        dx, dy = px - cx, py - cy
        return dx * dx + dy * dy <= r * r
    return inside


def render(size: int) -> bytes:
    n = size * SS
    u = n / 100.0  # one percent of the icon, in supersampled pixels

    body_w, body_h = 46 * u, 62 * u
    body_x, body_y = (n - body_w) / 2, (n - body_h) / 2
    body_r = 6 * u
    in_body = rounded_rect(body_x, body_y, body_w, body_h, body_r)

    divider_y = body_y + body_h * 0.34
    divider_h = max(2.0, 2.5 * u)

    pad = 4 * u
    handle_w, handle_r = 3 * u, 1.5 * u
    handle_x = body_x + body_w - pad - handle_w
    freezer_handle = rounded_rect(handle_x, divider_y - pad - 10 * u, handle_w, 10 * u, handle_r)
    fridge_handle = rounded_rect(handle_x, divider_y + divider_h + pad, handle_w, 14 * u, handle_r)

    # Supersampled colour buffer, then box-downsample to `size`
    rows = []
    acc = [[0, 0, 0] for _ in range(size)]
    out = bytearray()
    for sy in range(n):
        y = sy + 0.5
        row = []
        for sx in range(n):
            x = sx + 0.5
            if in_body(x, y):
                if divider_y <= y < divider_y + divider_h:
                    c = BRAND
                elif freezer_handle(x, y) or fridge_handle(x, y):
                    c = BRAND
                else:
                    c = WHITE
            else:
                c = BRAND
            row.append(c)
        rows.append(row)

    for oy in range(size):
        acc = [[0, 0, 0] for _ in range(size)]
        for sy in range(oy * SS, (oy + 1) * SS):
            row = rows[sy]
            for ox in range(size):
                a = acc[ox]
                for sx in range(ox * SS, (ox + 1) * SS):
                    c = row[sx]
                    a[0] += c[0]; a[1] += c[1]; a[2] += c[2]
        out.append(0)  # PNG filter type 0 for this scanline
        d = SS * SS
        for ox in range(size):
            a = acc[ox]
            out += bytes((a[0] // d, a[1] // d, a[2] // d))
    return bytes(out)


def write_png(path: pathlib.Path, size: int) -> None:
    raw = render(size)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))  # 8-bit RGB
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"{path.name}  {size}x{size}  {len(png)} bytes")


# Run from anywhere: python frontend/scripts/make_icons.py
root = pathlib.Path(__file__).resolve().parent.parent / "public" / "icons"
write_png(root / "icon-192.png", 192)
write_png(root / "icon-512.png", 512)
write_png(root / "apple-icon-180.png", 180)
