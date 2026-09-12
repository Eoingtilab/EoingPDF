"""Package supplied artwork as multi-resolution Windows icons."""
from pathlib import Path
from PIL import Image, ImageOps

root = Path(__file__).resolve().parents[1]
for name in ('app_icon', 'pdf_icon'):
    with Image.open(root / f'assets/{name}.png') as source:
        artwork = ImageOps.contain(source.convert('RGBA'), (256, 256), Image.Resampling.LANCZOS)
        image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        image.alpha_composite(artwork, ((256 - artwork.width) // 2, (256 - artwork.height) // 2))
        image.save(root / f'assets/{name}.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
