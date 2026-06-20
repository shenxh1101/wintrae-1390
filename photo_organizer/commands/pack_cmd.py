import os
import zipfile
import click
from pathlib import Path

from photo_organizer.core.file_utils import list_image_files, ensure_directory


def create_zip(source_dir, output_file, include_pattern=None, base_dir=None):
    """创建 zip 压缩包"""
    source_dir = Path(source_dir)
    output_file = Path(output_file)
    ensure_directory(output_file.parent)

    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                if include_pattern and file_path.suffix.lower() not in include_pattern:
                    continue
                arcname = file_path.relative_to(source_dir)
                if base_dir:
                    arcname = Path(base_dir) / arcname
                zf.write(file_path, arcname)

    return output_file


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', required=True, type=click.Path(file_okay=False, dir_okay=True),
              help='输出目录')
@click.option('--name', '-n', default='delivery', help='压缩包名称 (默认: delivery)')
@click.option('--format', '-f', default='zip',
              type=click.Choice(['zip']),
              help='压缩格式 (默认: zip)')
@click.option('--include-thumbs/--no-thumbs', default=True,
              help='是否包含缩略图 (默认: 是)')
@click.option('--thumbs-dir', default='thumbs', help='缩略图目录名 (默认: thumbs)')
@click.option('--split-by-orientation/--no-split-by-orientation', default=False,
              help='是否按横竖构图分别打包 (默认: 否)')
@click.option('--landscape-dir', default='landscape', help='横图文件夹名 (默认: landscape)')
@click.option('--portrait-dir', default='portrait', help='竖图文件夹名 (默认: portrait)')
@click.option('--include-original/--no-include-original', default=True,
              help='是否包含原图 (默认: 是)')
@click.option('--base-dir', help='压缩包内基础目录名')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际创建压缩包')
def pack_cmd(source_dir, output, name, format, include_thumbs, thumbs_dir,
              split_by_orientation, landscape_dir, portrait_dir,
              include_original, base_dir, dry_run):
    """打包交付压缩包"""
    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'源目录: {source_dir}')

    image_files = list_image_files(source_dir, recursive=True)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    if not dry_run:
        ensure_directory(output)

    created_packages = []

    if split_by_orientation:
        landscape_files = [f for f in image_files if landscape_dir in f.parts]
        portrait_files = [f for f in image_files if portrait_dir in f.parts]

        if landscape_files:
            zip_name = f'{name}_{landscape_dir}.zip'
            zip_path = output / zip_name
            if not dry_run:
                create_zip(source_dir, zip_path, base_dir=base_dir)
            created_packages.append((zip_name, len(landscape_files)))
            click.echo(f'  {zip_name}: {len(landscape_files)} 张')

        if portrait_files:
            zip_name = f'{name}_{portrait_dir}.zip'
            zip_path = output / zip_name
            if not dry_run:
                create_zip(source_dir, zip_path, base_dir=base_dir)
            created_packages.append((zip_name, len(portrait_files)))
            click.echo(f'  {zip_name}: {len(portrait_files)} 张')
    else:
        zip_name = f'{name}.zip'
        zip_path = output / zip_name
        if not dry_run:
            create_zip(source_dir, zip_path, base_dir=base_dir)
        created_packages.append((zip_name, len(image_files)))
        click.echo(f'  {zip_name}: {len(image_files)} 张')

    if include_thumbs:
        thumbs_path = source_dir / thumbs_dir
        if thumbs_path.exists():
            thumb_files = list_image_files(thumbs_path, recursive=True)
            if thumb_files:
                zip_name = f'{name}_{thumbs_dir}.zip'
                zip_path = output / zip_name
                if not dry_run:
                    create_zip(thumbs_path, zip_path, base_dir=base_dir)
                created_packages.append((zip_name, len(thumb_files)))
                click.echo(f'  {zip_name}: {len(thumb_files)} 张 (缩略图)')

    click.echo(f'\n打包完成:')
    click.echo(f'  生成 {len(created_packages)} 个压缩包')
    click.echo(f'  输出目录: {output}')
    for pkg_name, count in created_packages:
        pkg_path = output / pkg_name
        if not dry_run and pkg_path.exists():
            size_mb = pkg_path.stat().st_size / (1024 * 1024)
            click.echo(f'  - {pkg_name}: {count} 张, {size_mb:.2f} MB')
