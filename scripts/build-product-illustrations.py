"""Resize generated originals and build the N4 contact sheet (Pillow, dev-only).

This only formats already-generated illustrations; it does not synthesize images.
The per-SKU prompts and original paths are recorded in reports/n4-image-generation.json.
"""
from pathlib import Path
import argparse
import hashlib
import json
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def build(contact_sheet=False):
    manifest = ROOT / 'reports/n4-image-generation.json'
    record = json.loads(manifest.read_text(encoding='utf-8'))
    folder = ROOT / 'frontend/public/products'
    folder.mkdir(parents=True, exist_ok=True)
    ready = []
    for item in record['items']:
        if not item.get('source'):
            continue
        original = Path(item['source'])
        target = folder / f"{item['sku']}.webp"
        if not target.exists() or item.get('status') == 'generated':
            with Image.open(original) as opened:
                image = ImageOps.fit(opened.convert('RGB'), (256, 256), method=Image.Resampling.LANCZOS)
                for quality in [90, 85, 80, 75, 65]:
                    image.save(target, 'WEBP', quality=quality, method=6)
                    if target.stat().st_size < 30_000:
                        break
        with Image.open(target) as image:
            assert image.size == (256, 256), target
        assert target.stat().st_size < 30_000, target
        item.update(status='saved', asset=str(target.relative_to(ROOT)).replace('\\', '/'),
                    bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        ready.append(item)
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if contact_sheet:
        width, height = 176, 204
        columns = 10
        sheet = Image.new('RGB', (columns*width, ((len(ready)+columns-1)//columns)*height), '#f7f8f3')
        draw = ImageDraw.Draw(sheet)
        fontpath = Path('C:/Windows/Fonts/segoeui.ttf')
        font = ImageFont.truetype(str(fontpath), 12) if fontpath.exists() else ImageFont.load_default(size=12)
        for index, item in enumerate(ready):
            x, y = index % columns * width, index // columns * height
            with Image.open(folder / f"{item['sku']}.webp") as opened:
                thumb = opened.resize((152,152), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (x+12,y+4))
            label = item['sku']+' · '+item['name']
            draw.multiline_text((x+10,y+159), '\n'.join(textwrap.wrap(label, 25)[:3]), fill='#284f3d', font=font, spacing=1)
        path = ROOT / 'docs/screenshots/n4-contact-sheet.png'
        sheet.save(path)
    print(json.dumps({'saved':len(ready), 'total':len(record['items']), 'largest_bytes':max((i['bytes'] for i in ready),default=0), 'contact_sheet':contact_sheet}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--contact-sheet', action='store_true')
    args = parser.parse_args()
    build(args.contact_sheet)
