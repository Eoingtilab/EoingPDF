"""Create the small EoingPDF application mark from bundled typography."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=56, fill='#4b70ed')
font = ImageFont.truetype(str(root / 'assets/fonts/Pretendard-Regular.ttf'), 218)
draw.text((128, 119), 'e', font=font, anchor='mm', fill='white', stroke_width=2)
image.save(root / 'assets/app_icon.png')
image.save(root / 'assets/app_icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
