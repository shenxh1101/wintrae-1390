import os
import exifread
from datetime import datetime
from pathlib import Path


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.raw', '.cr2', '.nef', '.arw', '.dng'}


def is_image_file(filepath):
    ext = Path(filepath).suffix.lower()
    return ext in SUPPORTED_EXTENSIONS


def get_exif_data(filepath):
    with open(filepath, 'rb') as f:
        tags = exifread.process_file(f, details=False)
    return tags


def get_capture_date(filepath):
    tags = get_exif_data(filepath)
    date_tags = ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']
    for tag in date_tags:
        if tag in tags:
            date_str = str(tags[tag])
            try:
                return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                pass
    return None


def get_camera_model(filepath):
    tags = get_exif_data(filepath)
    if 'Image Model' in tags:
        return str(tags['Image Model']).strip()
    return None


def get_camera_serial(filepath):
    tags = get_exif_data(filepath)
    serial_tags = ['EXIF BodySerialNumber', 'Image BodySerialNumber']
    for tag in serial_tags:
        if tag in tags:
            return str(tags[tag]).strip()
    return None


def get_image_size(filepath):
    tags = get_exif_data(filepath)
    width = None
    height = None
    if 'EXIF ExifImageWidth' in tags:
        width = int(str(tags['EXIF ExifImageWidth']))
    if 'EXIF ExifImageLength' in tags:
        height = int(str(tags['EXIF ExifImageLength']))
    if not width or not height:
        if 'Image ImageWidth' in tags:
            width = int(str(tags['Image ImageWidth']))
        if 'Image ImageLength' in tags:
            height = int(str(tags['Image ImageLength']))
    return width, height


def get_image_orientation(filepath):
    width, height = get_image_size(filepath)
    if width is None or height is None:
        return 'unknown'
    if width > height:
        return 'landscape'
    elif height > width:
        return 'portrait'
    else:
        return 'square'


def get_rating(filepath):
    tags = get_exif_data(filepath)
    rating_tags = ['XMP xmp:Rating', 'EXIF Rating', 'Image Rating']
    for tag in rating_tags:
        if tag in tags:
            try:
                return int(str(tags[tag]))
            except ValueError:
                pass
    return 0
