import click
from pathlib import Path

from photo_organizer.core.exif_utils import get_rating
from photo_organizer.core.file_utils import list_image_files, copy_file, ensure_directory
from photo_organizer.core.config import apply_preset_to_options


def read_selection_list(list_file):
    """从清单文件读取选中的文件名列表"""
    selected = set()
    list_file = Path(list_file)
    if not list_file.exists():
        return selected
    with open(list_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                selected.add(line)
    return selected


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', required=True, type=click.Path(file_okay=False, dir_okay=True),
              help='输出目录')
@click.option('--min-rating', default=3, type=int,
              help='最低星标数 (默认: 3)，设为0则不按星标筛选')
@click.option('--list-file', '-l', type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help='手动筛选清单文件，每行一个文件名')
@click.option('--mode', default='union',
              type=click.Choice(['union', 'intersection', 'rating-only', 'list-only']),
              help='筛选模式: union(并集), intersection(交集), rating-only(仅星标), list-only(仅清单) (默认: union)')
@click.option('--keep-original/--move', default=True,
              help='保留原图或移动文件 (默认: 保留)')
@click.option('--recursive/--no-recursive', default=False,
              help='是否递归扫描子目录 (默认: 否)')
@click.option('--preset', '-p', help='使用预设配置名')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际复制文件')
def select_cmd(source_dir, output, min_rating, list_file, mode,
               keep_original, recursive, preset, dry_run):
    """读取星标或手动清单筛选精修图"""
    if preset:
        applied = apply_preset_to_options(
            preset,
            output=output, min_rating=min_rating, mode=mode
        )
        output = applied.get('output', output)
        min_rating = applied.get('min_rating', min_rating)
        mode = applied.get('mode', mode)
    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    selected_files = set()
    list_selected = set()

    if list_file:
        list_selected = read_selection_list(list_file)
        click.echo(f'清单文件包含 {len(list_selected)} 个文件名')

    with click.progressbar(image_files, label='筛选中') as files:
        for filepath in files:
            filename = filepath.name
            stem = filepath.stem

            rating_match = False
            list_match = False

            if mode in ['rating-only', 'union', 'intersection'] and min_rating > 0:
                try:
                    rating = get_rating(filepath)
                    if rating >= min_rating:
                        rating_match = True
                except Exception:
                    pass

            if mode in ['list-only', 'union', 'intersection'] and list_selected:
                if filename in list_selected or stem in list_selected:
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
