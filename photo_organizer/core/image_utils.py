from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


PROCESSABLE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.webp'}
RAW_EXTENSIONS = {'.raw', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2',
                  '.dng', '.raf', '.orf', '.rw2', '.pef', '.3fr', '.erf', '.kdc',
                  '.dcr', '.mrw', '.x3f'}


def is_processable_image(filepath):
    """判断文件格式是否可以被 Pillow 处理（JPG/PNG 等）"""
    ext = Path(filepath).suffix.lower()
    return ext in PROCESSABLE_EXTENSIONS


def is_raw_format(filepath):
    """判断是否为 RAW 格式"""
    ext = Path(filepath).suffix.lower()
    return ext in RAW_EXTENSIONS


def get_safe_output_path(input_path, output_dir):
    """为不可处理格式确定输出路径（保持原扩展名，如为RAW则输出为JPG）"""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    if is_raw_format(input_path):
        return output_dir / f'{input_path.stem}.jpg'
    return output_dir / input_path.name


def add_watermark(image_path, output_path, text, position='bottom-right', opacity=128, font_size=36):
    img = Image.open(image_path).convert('RGBA')
    txt_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)

    try:
        font = ImageFont.truetype('arial.ttf', font_size)
    except (IOError, OSError):
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    width, height = img.size
    margin = 20

    if position == 'bottom-right':
        x = width - text_width - margin
        y = height - text_height - margin
    elif position == 'bottom-left':
        x = margin
        y = height - text_height - margin
    elif position == 'top-right':
        x = width - text_width - margin
        y = margin
    elif position == 'top-left':
        x = margin
        y = margin
    elif position == 'center':
        x = (width - text_width) // 2
        y = (height - text_height) // 2
    else:
        x = width - text_width - margin
        y = height - text_height - margin

    draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))

    result = Image.alpha_composite(img, txt_layer)
    output_path = Path(output_path)
    if output_path.suffix.lower() in ['.jpg', '.jpeg']:
        result = result.convert('RGB')
    result.save(output_path)
    return output_path


def create_thumbnail(image_path, output_path, max_size=(800, 800), quality=85):
    img = Image.open(image_path)
    img.thumbnail(max_size, Image.LANCZOS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in ['.jpg', '.jpeg']:
        img.save(output_path, quality=quality, optimize=True)
    else:
        img.save(output_path)
    return output_path


def get_image_dimensions(image_path):
    img = Image.open(image_path)
    return img.size


def get_orientation(image_path):
    width, height = get_image_dimensions(image_path)
    if width > height:
        return 'landscape'
    elif height > width:
        return 'portrait'
    else:
        return 'square'
