import csv
import json
import click
from pathlib import Path

from photo_organizer.core.exif_utils import get_rating
from photo_organizer.core.file_utils import list_image_files, copy_file, ensure_directory
from photo_organizer.core.config import resolve_preset


def load_rename_mapping(source_dir):
    """在 source_dir 或其上级目录查找 .rename_mapping.json"""
    source_dir = Path(source_dir)
    candidates = [source_dir / '.rename_mapping.json']
    # 尝试上一级目录
    if source_dir.parent.exists():
        candidates.append(source_dir.parent / '.rename_mapping.json')
    for p in candidates:
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('mapping', {})
            except Exception:
                pass
    return {}


def read_selection_list(list_file, source_dir=None):
    """读取筛选清单，支持纯文本（每行一个文件名/路径）和 CSV

    返回 (filename_set, subpath_set)
      - filename_set: 文件名集合（含带扩展名和不带扩展名）
      - subpath_set: 相对路径集合
    """
    filename_set = set()
    subpath_set = set()
    list_file = Path(list_file)
    if not list_file.exists():
        return filename_set, subpath_set

    ext = list_file.suffix.lower()
    is_csv = ext == '.csv'

    with open(list_file, 'r', encoding='utf-8-sig' if is_csv else 'utf-8') as f:
        if is_csv:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                # 取第一列非空值作为文件名/路径
                for cell in row:
                    cell = cell.strip()
                    if cell and not cell.startswith('#'):
                        _add_selection(cell, filename_set, subpath_set)
                        break
        else:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 支持逗号分隔（一行多个）
                for part in line.split(','):
                    part = part.strip().strip('"').strip("'")
                    if part:
                        _add_selection(part, filename_set, subpath_set)

    return filename_set, subpath_set


def _add_selection(entry, filename_set, subpath_set):
    """把一个选择条目加入集合

    会同时加入:
      - 完整字符串
      - basename（文件名部分）
      - stem（不带扩展名的文件名）
      - 含正斜杠和反斜杠两种表示的路径
    """
    filename_set.add(entry)
    p = Path(entry)
    filename_set.add(p.name)
    if p.stem:
        filename_set.add(p.stem)
    # 路径
    subpath_set.add(entry)
    subpath_set.add(entry.replace('\\', '/'))
    subpath_set.add(entry.replace('/', '\\'))
    # 如果有扩展名，也记录不带扩展名的路径
    if p.suffix:
        stem_path = str(p.with_suffix(''))
        subpath_set.add(stem_path)
        subpath_set.add(stem_path.replace('\\', '/'))


def check_file_match(filepath, source_dir, filename_set, subpath_set, rename_mapping):
    """判断文件是否匹配清单

    检查顺序:
      1. 文件名或 stem 是否在 filename_set 中
      2. 相对于 source_dir 的相对路径是否在 subpath_set 中
      3. rename_mapping 中原名是否指向当前文件名
    """
    filename = filepath.name
    stem = filepath.stem

    if filename in filename_set or stem in filename_set:
        return True

    try:
        rel_path = filepath.relative_to(source_dir)
        rel_str = str(rel_path)
        rel_posix = rel_path.as_posix()
        if rel_str in subpath_set or rel_posix in subpath_set:
            return True
        # 不带扩展名的相对路径
        rel_stem = str(rel_path.with_suffix(''))
        if rel_stem in subpath_set or rel_stem.replace('\\', '/') in subpath_set:
            return True
    except ValueError:
        pass

    # 通过 rename_mapping 匹配：清单中的原文件名 → 新文件名
    if rename_mapping:
        for orig_name, new_name in rename_mapping.items():
            if new_name == filename or Path(new_name).stem == stem:
                orig_path = Path(orig_name)
                if (orig_name in filename_set or orig_path.name in filename_set
                        or orig_path.stem in filename_set or orig_name in subpath_set):
                    return True

    return False


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', default=None, help='输出目录')
@click.option('--min-rating', default=3, type=int,
              help='最低星标数 (默认: 3)，设为0则不按星标筛选')
@click.option('--list-file', '-l', type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help='手动筛选清单文件 (支持 .txt 或 .csv)')
@click.option('--mode', default=None,
              type=click.Choice(['union', 'intersection', 'rating-only', 'list-only']),
              help='筛选模式 (默认: union)')
@click.option('--keep-original/--move', default=True,
              help='保留原图或移动文件 (默认: 保留)')
@click.option('--recursive/--no-recursive', default=False,
              help='是否递归扫描子目录 (默认: 否)')
@click.option('--use-rename-mapping/--no-rename-mapping', default=True,
              help='是否使用 .rename_mapping.json 按原文件名匹配 (默认: 是)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际复制文件')
def select_cmd(source_dir, output, min_rating, list_file, mode,
               keep_original, recursive, use_rename_mapping, preset, dry_run):
    """读取星标或手动清单筛选精修图

    清单文件格式:
      - .txt: 每行一个文件名或相对路径（支持逗号分隔多个）
      - .csv: 读取第一列作为文件名/路径
      - 支持通过 .rename_mapping.json 按导入前的原文件名匹配
    """
    resolved = resolve_preset(
        preset,
        {'output': output, 'min_rating': min_rating, 'mode': mode},
        {'output': None, 'min_rating': 3, 'mode': 'union'}
    )
    output = resolved['output']
    min_rating = resolved['min_rating']
    mode = resolved['mode']

    if not output:
        click.echo('错误: 请指定输出目录 (--output 或在 preset 中配置)')
        return

    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    rename_mapping = {}
    if use_rename_mapping:
        rename_mapping = load_rename_mapping(source_dir)
        if rename_mapping:
            click.echo(f'已加载改名映射 ({len(rename_mapping)} 条)，支持按原文件名匹配')

    selected_files = set()
    list_selected_names = set()
    list_selected_paths = set()

    if list_file:
        list_selected_names, list_selected_paths = read_selection_list(list_file, source_dir)
        total_entries = len(list_selected_names) + len(list_selected_paths)
        click.echo(f'清单文件包含 {total_entries} 个匹配项 (支持文件名、路径、原名映射)')

    with click.progressbar(image_files, label='筛选中') as files:
        for filepath in files:
            rating_match = False
            list_match = False

            if mode in ['rating-only', 'union', 'intersection'] and min_rating > 0:
                try:
                    rating = get_rating(filepath)
                    if rating >= min_rating:
                        rating_match = True
                except Exception:
                    pass

            if mode in ['list-only', 'union', 'intersection'] and (list_selected_names or list_selected_paths):
                if check_file_match(filepath, source_dir, list_selected_names,
                                    list_selected_paths, rename_mapping):
                    list_match = True

            if mode == 'union':
                if rating_match or list_match:
                    selected_files.add(filepath)
            elif mode == 'intersection':
                if rating_match and list_match:
                    selected_files.add(filepath)
            elif mode == 'rating-only':
                if rating_match:
                    selected_files.add(filepath)
            elif mode == 'list-only':
                if list_match:
                    selected_files.add(filepath)

    click.echo(f'筛选出 {len(selected_files)} 张精修图')

    if not selected_files:
        click.echo('没有符合条件的照片')
        return

    selected_list = sorted(selected_files, key=lambda f: f.name)
    copied_count = 0

    with click.progressbar(selected_list, label='复制中') as files:
        for filepath in files:
            try:
                dest_path = output / filepath.name
                if not dry_run:
                    ensure_directory(output)
                    if dest_path.exists():
                        continue
                    copy_file(filepath, dest_path, keep_original=keep_original)
                copied_count += 1
            except Exception as e:
                click.echo(f'\n处理 {filepath.name} 时出错: {e}')

    click.echo(f'\n筛选完成:')
    click.echo(f'  总照片数: {len(image_files)}')
    click.echo(f'  选中: {len(selected_files)} 张')
    click.echo(f'  成功复制: {copied_count} 张')
    click.echo(f'  输出目录: {output}')
