import os
import click
from pathlib import Path
from datetime import datetime

from photo_organizer.core.exif_utils import get_capture_date, get_camera_model, get_camera_serial
from photo_organizer.core.file_utils import list_image_files, copy_file, ensure_directory


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', required=True, type=click.Path(file_okay=False, dir_okay=True),
              help='输出目录')
@click.option('--group-by', default='date,camera',
              help='分组方式，可用值: date, camera, date,camera (默认: date,camera)')
@click.option('--date-format', default='%Y-%m-%d',
              help='日期文件夹格式 (默认: %%Y-%%m-%%d)')
@click.option('--keep-original/--move', default=True,
              help='保留原图或移动文件 (默认: 保留)')
@click.option('--recursive/--no-recursive', default=True,
              help='是否递归扫描子目录 (默认: 是)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际复制文件')
def import_cmd(source_dir, output, group_by, date_format, keep_original, recursive, dry_run):
    """按拍摄日期和相机编号导入照片"""
    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    group_options = [g.strip() for g in group_by.split(',')]
    imported_count = 0
    skipped_count = 0

    with click.progressbar(image_files, label='导入中') as files:
        for filepath in files:
            try:
                capture_date = get_capture_date(filepath)
                camera_model = get_camera_model(filepath)
                camera_serial = get_camera_serial(filepath)

                rel_path_parts = []

                if 'date' in group_options:
                    if capture_date:
                        date_folder = capture_date.strftime(date_format)
                    else:
                        date_folder = 'unknown_date'
                    rel_path_parts.append(date_folder)

                if 'camera' in group_options:
                    camera_folder = 'unknown_camera'
                    if camera_model:
                        camera_folder = camera_model.replace('/', '_')
                        if camera_serial:
                            camera_folder = f'{camera_folder}_{camera_serial}'
                    rel_path_parts.append(camera_folder)

                if not rel_path_parts:
                    rel_path_parts.append('all')

                dest_dir = output / Path(*rel_path_parts)
                dest_path = dest_dir / filepath.name

                if not dry_run:
                    ensure_directory(dest_dir)
                    if dest_path.exists():
                        skipped_count += 1
                        continue
                    copy_file(filepath, dest_path, keep_original=keep_original)

                imported_count += 1

            except Exception as e:
                click.echo(f'\n处理 {filepath.name} 时出错: {e}')
                skipped_count += 1

    click.echo(f'\n导入完成:')
    click.echo(f'  成功: {imported_count} 张')
    click.echo(f'  跳过: {skipped_count} 张')
    click.echo(f'  输出目录: {output}')
