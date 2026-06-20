import os
import json
import shutil
import zipfile
import click
from pathlib import Path
from datetime import datetime

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


def create_manifest(output_dir, name, client, session, created_packages,
                      photo_count, thumb_count, checksum_path,
                      zip_checksums=None):
    """生成交付 manifest 清单文件"""
    output_dir = Path(output_dir)
    ensure_directory(output_dir)
    manifest_path = output_dir / f'{name}_manifest.json'

    packages_info = []
    for pkg_name, count in created_packages:
        pkg_path = output_dir / pkg_name
        pkg_info = {
            'name': pkg_name,
            'file_count': count,
            'is_thumbs': 'thumb' in pkg_name.lower(),
        }
        if pkg_path.exists():
            pkg_info['size_bytes'] = pkg_path.stat().st_size
            pkg_info['size_mb'] = round(pkg_path.stat().st_size / (1024 * 1024), 2)
        if zip_checksums and pkg_name in zip_checksums:
            pkg_info['md5'] = zip_checksums[pkg_name]
        packages_info.append(pkg_info)

    manifest = {
        'client': client,
        'session': session,
        'delivery_name': name,
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_packages': len(created_packages),
            'total_photos': photo_count,
            'total_thumbs': thumb_count,
            'total_files': photo_count + thumb_count,
        },
        'packages': packages_info,
        'checksum_file': checksum_path.name if checksum_path else None,
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path, manifest


def format_manifest_text(manifest):
    """将 manifest 转为可读文本格式"""
    lines = []
    lines.append('=' * 60)
    lines.append('客户交付清单 (Manifest)')
    lines.append('=' * 60)
    lines.append(f'客户名称: {manifest["client"] or "(未设置)"}')
    lines.append(f'场次编号: {manifest["session"] or "(未设置)"}')
    lines.append(f'交付名称: {manifest["delivery_name"]}')
    lines.append(f'生成时间: {manifest["generated_at"]}')
    lines.append('')
    lines.append('【内容摘要】')
    s = manifest['summary']
    lines.append(f'  压缩包总数: {s["total_packages"]} 个')
    lines.append(f'  交付照片: {s["total_photos"]} 张')
    lines.append(f'  缩略图: {s["total_thumbs"]} 张')
    lines.append(f'  总计文件: {s["total_files"]} 张')
    lines.append('')
    lines.append('【交付包明细】')
    for i, pkg in enumerate(manifest['packages'], 1):
        type_label = '缩略图' if pkg.get('is_thumbs') else '照片'
        size_str = f'{pkg["size_mb"]:.2f} MB' if 'size_mb' in pkg else 'N/A'
        lines.append(f'  {i}. {pkg["name"]}')
        lines.append(f'     类型: {type_label} | 数量: {pkg["file_count"]} 张 | 大小: {size_str}')
        if 'md5' in pkg:
            lines.append(f'     MD5:  {pkg["md5"]}')
    if manifest.get('checksum_file'):
        lines.append('')
        lines.append(f'校验文件: {manifest["checksum_file"]}')
    lines.append('=' * 60)
    return '\n'.join(lines)


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
@click.option('--client', '-c', default=None, help='客户名称 (用于 manifest)')
@click.option('--session', '-s', default=None, help='场次编号 (用于 manifest)')
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
              help='是否生成统一 MD5 校验文件 (默认: 是，包含 zip+照片+缩略图)')
@click.option('--include-photos-in-checksum/--no-photos-in-checksum', default=True,
              help='校验文件是否包含源照片 (默认: 是)')
@click.option('--include-thumbs-in-checksum/--no-thumbs-in-checksum', default=True,
              help='校验文件是否包含缩略图 (默认: 是)')
@click.option('--generate-manifest/--no-manifest', default=True,
              help='是否生成交付 manifest 清单 (默认: 是)')
@click.option('--copy-photos-to-output/--no-copy-photos', default=True,
              help='是否复制照片和缩略图到交付目录 (默认: 是，便于 verify 检查)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际创建压缩包')
def pack_cmd(source_dir, output, name, client, session, format, include_thumbs, thumbs_dir,
              split_by_orientation, landscape_dir, portrait_dir, square_dir,
              include_original, base_dir, preset, generate_checksums,
              include_photos_in_checksum, include_thumbs_in_checksum,
              generate_manifest, copy_photos_to_output, dry_run):
    """打包交付压缩包（含统一校验和 manifest）"""
    resolved = resolve_preset(
        preset,
        {'output': output, 'name': name, 'base_dir': base_dir,
         'client': client, 'session': session},
        {'output': None, 'name': 'delivery', 'base_dir': None,
         'client': None, 'session': None}
    )
    output = resolved['output']
    name = resolved['name']
    base_dir = resolved['base_dir']
    client = resolved['client']
    session = resolved['session']

    if not output:
        click.echo('错误: 请指定输出目录 (--output 或在 preset/project 中配置)')
        return

    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'源目录: {source_dir}')

    all_photo_files = []
    all_thumb_files = []
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
            all_photo_files.extend(landscape_files)
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
            all_photo_files.extend(portrait_files)
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
            all_photo_files.extend(square_files)
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
        # 非横竖分离模式：收集除 thumbs 外的所有照片
        for f in image_files:
            f_path = Path(f)
            if thumbs_dir not in f_path.parts:
                all_photo_files.append(f_path)
        zip_name = f'{name}.zip'
        zip_path = output / zip_name
        if not dry_run:
            create_zip_from_dir(
                source_dir, zip_path,
                exclude_dirs=[thumbs_dir] if not include_thumbs else None,
                base_dir=base_dir
            )
        created_packages.append((zip_name, len(all_photo_files)))
        click.echo(f'  {zip_name}: {len(all_photo_files)} 张')

    if include_thumbs:
        thumbs_path = source_dir / thumbs_dir
        if thumbs_path.exists():
            thumb_files = list_image_files(thumbs_path, recursive=True)
            all_thumb_files.extend(thumb_files)
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
    zip_checksums = {}
    for pkg_name, count in created_packages:
        pkg_path = output / pkg_name
        if not dry_run and pkg_path.exists():
            size_mb = pkg_path.stat().st_size / (1024 * 1024)
            click.echo(f'  - {pkg_name}: {count} 张, {size_mb:.2f} MB')
            if generate_checksums:
                try:
                    zip_checksums[pkg_name] = get_file_hash(pkg_path)
                except Exception:
                    pass

    if not dry_run and copy_photos_to_output:
        click.echo('\n正在复制照片和缩略图到交付目录...')
        copied_photos = 0
        copied_thumbs = 0
        for photo_path in all_photo_files:
            photo_path = Path(photo_path)
            try:
                rel_path = photo_path.relative_to(source_dir)
                dest_path = output / 'photos' / rel_path
                ensure_directory(dest_path.parent)
                shutil.copy2(photo_path, dest_path)
                copied_photos += 1
            except Exception as e:
                click.echo(f'  复制失败: {photo_path.name} - {e}')
        for thumb_path in all_thumb_files:
            thumb_path = Path(thumb_path)
            try:
                rel_path = thumb_path.relative_to(source_dir)
                dest_path = output / 'photos' / rel_path
                ensure_directory(dest_path.parent)
                shutil.copy2(thumb_path, dest_path)
                copied_thumbs += 1
            except Exception as e:
                click.echo(f'  复制失败: {thumb_path.name} - {e}')
        click.echo(f'  已复制: {copied_photos} 张照片 + {copied_thumbs} 张缩略图 -> {output}/photos/')

    checksum_path = None
    if not dry_run and generate_checksums:
        checksum_files = []
        zip_paths = [output / pkg_name for pkg_name, _ in created_packages if (output / pkg_name).exists()]
        checksum_files.extend(zip_paths)
        if include_photos_in_checksum:
            if copy_photos_to_output:
                photos_output = output / 'photos'
                for photo_path in all_photo_files:
                    photo_path = Path(photo_path)
                    rel_path = photo_path.relative_to(source_dir)
                    dest_path = photos_output / rel_path
                    if dest_path.exists():
                        checksum_files.append(dest_path)
            else:
                checksum_files.extend(all_photo_files)
        if include_thumbs_in_checksum:
            if copy_photos_to_output:
                photos_output = output / 'photos'
                for thumb_path in all_thumb_files:
                    thumb_path = Path(thumb_path)
                    rel_path = thumb_path.relative_to(source_dir)
                    dest_path = photos_output / rel_path
                    if dest_path.exists():
                        checksum_files.append(dest_path)
            else:
                checksum_files.extend(all_thumb_files)

        if checksum_files:
            checksum_path = write_checksum_file(
                checksum_files, output,
                checksum_filename=f'{name}_checksums.md5'
            )
            click.echo(f'  已生成统一校验文件: {checksum_path}')
            click.echo(f'    包含: {len(zip_paths)} 个压缩包 + '
                       f'{len(all_photo_files) if include_photos_in_checksum else 0} 张照片 + '
                       f'{len(all_thumb_files) if include_thumbs_in_checksum else 0} 张缩略图')

    manifest_path = None
    manifest = None
    if not dry_run and generate_manifest:
        manifest_path, manifest = create_manifest(
            output_dir=output,
            name=name,
            client=client,
            session=session,
            created_packages=created_packages,
            photo_count=len(all_photo_files),
            thumb_count=len(all_thumb_files),
            checksum_path=checksum_path,
            zip_checksums=zip_checksums
        )
        click.echo(f'  已生成交付清单: {manifest_path}')

        text_manifest_path = output / f'{name}_manifest.txt'
        with open(text_manifest_path, 'w', encoding='utf-8') as f:
            f.write(format_manifest_text(manifest))
        click.echo(f'  已生成可读清单: {text_manifest_path}')
        click.echo('')
        click.echo(format_manifest_text(manifest))

    return {
        'packages': created_packages,
        'photo_count': len(all_photo_files),
        'thumb_count': len(all_thumb_files),
        'checksum_path': str(checksum_path) if checksum_path else None,
        'manifest_path': str(manifest_path) if manifest_path else None,
        'zip_checksums': zip_checksums,
    }
