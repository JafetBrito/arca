"""Genera recursos/arca.ico (un arca sobre las olas). Requiere Pillow solo al compilar."""

from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill="#1f3a5f")
# casa del arca
d.rectangle((370, 330, 654, 520), fill="#f4d58d")
d.polygon([(330, 340), (512, 200), (694, 340)], fill="#e8b04b")
d.rectangle((485, 410, 539, 520), fill="#1f3a5f")
# casco
d.polygon([(190, 520), (834, 520), (730, 690), (294, 690)], fill="#ffffff")
d.rectangle((190, 520, 834, 555), fill="#c9d6e8")
# olas
for y, color in ((740, "#7ec8e3"), (820, "#4fa3c7")):
    for x in range(140, 900, 150):
        d.arc((x, y - 50, x + 150, y + 50), 200, 340, fill=color, width=34)

salida = Path(__file__).resolve().parent.parent / "recursos" / "arca.ico"
salida.parent.mkdir(exist_ok=True)
img.save(salida, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icono creado:", salida)
