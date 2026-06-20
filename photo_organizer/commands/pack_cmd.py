import os
import zipfile
import click
from pathlib import Path

from photo_organizer.core.file_utils import list_image_files, ensure_directory, get_file_hash
from photo_organizer.core.config import resolve_preset


def write_checksum_file(file_list, output_dir, checksum_filename='checksums.md5'):
    """为文件列表生成 MD5 校验文件

    输出格式: <md5>  <相对路径或文件名>
    """
    output_dir = Path(output_dir)
    ensure_directory(output_dir)
    checksum_path = output_dir / checksum_filename

    with open(checksum_path, 'w', encoding='utf-8') as f:
        for filepath in sorted(file_list):
            filepath = Path(filepath)
            try:
                file_hash = get_file_hash(filepath)
                rel_path = filepath.relative_to(output_dir) if filepath.is_relative_to(output_dir) else filepath.name
                f.write(f'{file_hash}  {rel_path}\n')
            except Exception:
                continue

    return checksum_path


def create_zip_from_dir(source_dir, output_file, subdirs=None, exclude_dirs=None, base_dir=None):
    """创建 zip 压缩包

    Args:
        subdirs: 指定时只打包这些子目录的内容，根目录文件不会被打包
        exclude_dirs: 排除的子目录名列表
        base_dir: 压缩包内基础目录名
    """
    source_dir = Path(source_dir)
    output_file = Path(output_file)
    ensure_directory(output_file.parent)

    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            root_path = Path(root)
            rel_root = root_path.relative_to(source_dir)
            rel_root_parts = rel_root.parts

            if subdirs is not None:
                if not rel_root_parts:
                    continue
                if rel_root_parts[0] not in subdirs:
                    continue

            if exclude_dirs:
                if rel_root_parts and rel_root_parts[0] in exclude_dirs:
                    continue

            for file in files:
                file_path = root_path / file
                arcname = file_path.relative_to(source_dir)
                if base_dir:
                    arcname = Path(base_dir) / arcname
                zf.write(file_path, arcname)

    return output_file


def create_zip_from_file_list(file_list, output_file, strip_prefix=None, base_dir=None):
    output_file = Path(output_file)
    ensure_directory(output_file.parent)

    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_list:
            file_path = Path(file_path)
            if strip_prefix:
                try:
                    arcname = file_path.relative_to(strip_prefix)
                except ValueError:
                    arcname = file_path.name
            else:
                arcname = file_path.name
            if base_dir:
                arcname = Path(base_dir) / arcname
            zf.write(file_path, arcname)

    return output_file


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', default=None, help='输出目录')
@click.option('--name', '-n', default=None, help='压缩包名称 (默认: delivery)')
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
@click.option('--square-dir', default='square', help='方图文件夹名 (默认: square)')
@click.option('--include-original/--no-include-original', default=True,
              help='是否包含原图 (默认: 是)')
@click.option('--base-dir', default=None, help='压缩包内基础目录名')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--generate-checksums/--no-checksums', default=True,
              help='是否生成 MD5 校验文件 (默认: 是)')
@click.option('--checksum-photos/--no-checksum-photos', default=False,
              help='是否同时为源照片生成校验 (默认: 否，仅校验 zip)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际创建压缩包')
def pack_cmd(source_dir, output, name, format, include_thumbs, thumbs_dir,
              split_by_orientation, landscape_dir, portrait_dir, square_dir,
              include_original, base_dir, preset, generate_checksums,
              checksum_photos, dry_run):
    """打包交付压缩包"""
    resolved = resolve_preset(
        preset,
        {'output': output, 'name': name, 'base_dir': base_dir},
        {'output': None, 'name': 'delivery', 'base_dir': None}
    )
    output = resolved['output']
    name = resolved['name']
    base_dir = resolved['base_dir']

    if not output:
        click.echo('错误: 请指定输出目录 (--output 或在 preset 中配置)')
        return

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
        landscape_dir_path = source_dir / landscape_dir
        portrait_dir_path = source_dir / portrait_dir
        square_dir_path = source_dir / square_dir

        if landscape_dir_path.exists():
            landscape_files = list_image_files(landscape_dir_path, recursive=True)
            if landscape_files:
                zip_name = f'{name}_{landscape_dir}.zip'
                zip_path = output / zip_name
                if not dry_run:
                    create_zip_from_dir(
                        source_dir, zip_path,
                        subdirs=[landscape_dir],
                        exclude_dirs=[thumbs_dir],
                        base_dir=base_dir
                    )
                created_packages.append((zip_name, len(landscape_files)))
                click.echo(f'  {zip_name}: {len(landscape_files)} 张横图')

        if portrait_dir_path.exists():
            portrait_files = list_image_files(portrait_dir_path, recursive=True)
            if portrait_files:
                zip_name = f'{name}_{portrait_dir}.zip'
                zip_path = output / zip_name
                if not dry_run:
                    create_zip_from_dir(
                        source_dir, zip_path,
                        subdirs=[portrait_dir],
                        exclude_dirs=[thumbs_dir],
                        base_dir=base_dir
                    )
                created_packages.append((zip_name, len(portrait_files)))
                click.echo(f'  {zip_name}: {len(portrait_files)} 张竖图')

        if square_dir_path.exists():
            square_files = list_image_files(square_dir_path, recursive=True)
            if square_files:
                zip_name = f'{name}_{square_dir}.zip'
                zip_path = output / zip_name
                if not dry_run:
                    create_zip_from_dir(
                        source_dir, zip_path,
                        subdirs=[square_dir],
                        exclude_dirs=[thumbs_dir],
                        base_dir=base_dir
                    )
                created_packages.append((zip_name, len(square_files)))
                click.echo(f'  {zip_name}: {len(square_files)} 张方图')
    else:
        zip_name = f'{name}.zip'
        zip_path = output / zip_name
        if not dry_run:
            create_zip_from_dir(
                source_dir, zip_path,
                exclude_dirs=[thumbs_dir] if not include_thumbs else None,
                base_dir=base_dir
            )
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
                    create_zip_from_dir(
                        thumbs_path, zip_path,
                        base_dir=base_dir
                    )
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

    if not dry_run and generate_checksums:
        zip_paths = [output / pkg_name for pkg_name, _ in created_packages if (output / pkg_name).exists()]
        if zip_paths:
            checksum_path = write_checksum_file(zip_paths, output, checksum_filename=f'{name}_checksums.md5')
            click.echo(f'  已生成压缩包校验文件: {checksum_path}')

        if checksum_photos:
            photo_checksum_path = write_checksum_file(
                image_files, output, checksum_filename=f'{name}_photos_checksums.md5'
            )
            click.echo(f'  已生成照片校验文件: {photo_checksum_path}')
