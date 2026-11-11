#!/usr/bin/env python3
"""ikon.py - membuat ikon peluncur aplikasi dari bentuk robot di web/robot.svg (pakai Pillow).

Menghasilkan:
  res/mipmap-*/ic_launcher.png     ikon biasa (Android 7 - 7.1): kotak bulat gelap + robot
  res/mipmap-*/ic_launcher_fg.png  lapisan depan ikon adaptif (Android 8+), latar dari @color/ikon_latar
Jalankan ulang hanya kalau bentuk robot diubah:  python3 ikon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

DIR = Path(__file__).resolve().parent / "res"
LATAR = (0x11, 0x13, 0x17, 255)
SKALA_HALUS = 4  # gambar besar dulu lalu diperkecil supaya tepi halus

# Bentuk dari web/robot.svg (viewBox 20 6 160 106).
VB_X, VB_Y, VB_W, VB_H = 20, 6, 160, 106
KOTAK = [  # (x, y, w, h, rx, warna)
    (26, 52, 16, 28, 8, "#cfd5e2"),
    (158, 52, 16, 28, 8, "#cfd5e2"),
    (80, 12, 40, 16, 8, "#d6dbe7"),
    (34, 20, 132, 88, 36, "#f4f6fb"),
    (46, 33, 108, 62, 26, "#12293d"),
]
MATA = [(75, 68, 13), (125, 68, 13)]   # setengah lingkaran atas: pusat x, y, jari-jari
MULUT = ((92, 77), (100, 88), (108, 77))  # kurva kuadrat
CYAN = "#4fe3ff"


def robot(ukuran, lebar_isi):
    """Gambar robot di tengah kanvas persegi `ukuran`, lebar robot = `lebar_isi` piksel."""
    s = SKALA_HALUS
    n = ukuran * s
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = lebar_isi * s / VB_W
    ox = (n - VB_W * k) / 2 - VB_X * k
    oy = (n - VB_H * k) / 2 - VB_Y * k

    def p(x, y):
        return (ox + x * k, oy + y * k)

    for x, y, w, h, rx, warna in KOTAK:
        d.rounded_rectangle([p(x, y), p(x + w, y + h)], radius=rx * k, fill=warna)
    for cx, cy, r in MATA:
        d.pieslice([p(cx - r, cy - r), p(cx + r, cy + r)], 180, 360, fill=CYAN)
    (x0, y0), (x1, y1), (x2, y2) = MULUT
    titik = []
    for i in range(41):
        t = i / 40
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
        titik.append(p(x, y))
    d.polygon(titik, fill=CYAN)
    return img


def perkecil(img, ukuran):
    return img.resize((ukuran, ukuran), Image.LANCZOS)


def main():
    kepadatan = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for nama, f in kepadatan.items():
        folder = DIR / f"mipmap-{nama}"
        folder.mkdir(parents=True, exist_ok=True)

        # Ikon biasa 48dp: kotak bulat gelap, robot selebar ~78%.
        u = round(48 * f)
        n = u * SKALA_HALUS
        dasar = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        ImageDraw.Draw(dasar).rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 0.22, fill=LATAR)
        dasar.alpha_composite(robot(u, u * 0.78))
        perkecil(dasar, u).save(folder / "ic_launcher.png", optimize=True)

        # Lapisan depan ikon adaptif 108dp; area aman 66dp di tengah, robot selebar 60dp.
        u = round(108 * f)
        perkecil(robot(u, 60 * f), u).save(folder / "ic_launcher_fg.png", optimize=True)
        print("ikon", nama, "selesai")


if __name__ == "__main__":
    main()
