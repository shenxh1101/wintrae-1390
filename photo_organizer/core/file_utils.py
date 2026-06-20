import os
import shutil
import hashlib
from pathlib import Path
from .exif_utils import is_image_file


def list_image_files(directory, recursive=True):
    image_files = []
    directory = Path(directory)
    if not directory.exists():
        return image_files
    if recursive:
        for root, dirs, files in os.walk(directory):
            for f in files:
                filepath = Path(root) / f
                if is_image_file(filepath):
                    image_files.append(filepath)
    else:
        for f in directory.iterdir():
            if f.is_file() and is_image_file(f):
                image_files.append(f)
    return sorted(image_files)


def get_file_hash(filepath, block_size=65536):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            hasher.update(block)
    return hasher.hexdigest()


def find_duplicate_files(file_list):
    hash_map = {}
    duplicates = []
    for filepath in file_list:
        file_hash = get_file_hash(filepath)
        if file_hash in hash_map:
            duplicates.append((hash_map[file_hash], filepath))
        else:
            hash_map[file_hash] = filepath
    return duplicates


def ensure_directory(directory):
    Path(directory).mkdir(parents=True, exist_ok=True)


def copy_file(src, dst, keep_original=True):
    dst = Path(dst)
    ensure_directory(dst.parent)
    if keep_original:
        shutil.copy2(src, dst)
    else:
        shutil.move(str(src), str(dst))
    return dst


def safe_filename(name):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip()
