import shutil
import click
from pathlib import Path

from photo_organizer.core.file_utils import list_image_files, ensure_directory
from photo_organizer.core.image_utils import (
    add_watermark, create_thumbnail, get_orientation,
    is_processable_image, is_raw_format
)
from photo_organizer.core.config import resolve_preset


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', default=None, help='输出目录')
@click.option('--text', '-t', default=None, help='水印文字')
@click.option('--position', default='bottom-right',
              type=click.Choice(['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center']),
              help='水印位置 (默认: bottom-right)')
@click.option('--opacity', default=128, type=click.IntRange(0, 255),
              help='水印透明度 0-255 (默认: 128)')
@click.option('--font-size', default=36, type=int, help='水印字体大小 (默认: 36)')
@click.option('--thumbnail/--no-thumbnail', default=True,
              help='是否生成缩略图 (默认: 是)')
@click.option('--thumbnail-size', default=800, type=int,
              help='缩略图最大尺寸 (默认: 800)')
@click.option('--thumbnail-dir', default='thumbs', help='缩略图子目录名 (默认: thumbs)')
@click.option('--split-orientation/--no-split-orientation', default=True,
              help='是否按横竖构图分文件夹 (默认: 是)')
@click.option('--landscape-dir', default='landscape', help='横图文件夹名 (默认: landscape)')
@click.option('--portrait-dir', default='portrait', help='竖图文件夹名 (默认: portrait)')
@click.option('--square-dir', default='square', help='方图文件夹名 (默认: square)')
@click.option('--raw-output-dir', default='raw_original',
              help='RAW 原片输出目录名 (默认: raw_original)')
@click.option('--copy-raw/--skip-raw', default=True,
              help='是否复制 RAW 原片到输出目录 (默认: 复制)')
@click.option('--recursive/--no-recursive', default=False,
              help='是否递归扫描子目录 (默认: 否)')
@click.option('--quality', default=85, type=click.IntRange(1, 100),
              help='JPEG 输出质量 (默认: 85)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--report-skipped', 'report_skipped_path',
              type=click.Path(file_okay=True, dir_okay=False),
              help='将跳过文件列表写入指定路径 (供后续 report 使用)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际处理文件')
def watermark_cmd(source_dir, output, text, position, opacity, font_size,
                  thumbnail, thumbnail_size, thumbnail_dir,
                  split_orientation, landscape_dir, portrait_dir, square_dir,
                  raw_output_dir, copy_raw,
                  recursive, quality, preset, report_skipped_path, dry_run):
    """统一加水印、生成缩略图、按横竖构图分文件夹

    JPG/PNG 等可处理格式会正常加水印和生成缩略图；
    RAW 原片会跳过水印处理，可选择复制到独立目录；
    其他不可处理格式会记录到跳过列表。
    """
    resolved = resolve_preset(
        preset,
        {'output': output, 'text': text, 'position': position,
         'opacity': opacity, 'font_size': font_size},
        {'output': None, 'text': None, 'position': 'bottom-right',
         'opacity': 128, 'font_size': 36}
    )
    output = resolved['output']
    text = resolved['text']
    position = resolved['position']
    opacity = resolved['opacity']
    font_size = resolved['font_size']

    if not output:
        click.echo('错误: 请指定输出目录 (--output 或在 preset 中配置)')
        return
    if not text:
        click.echo('错误: 请指定水印文字 (--text 或在 preset 中配置)')
        return

    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    processed_count = 0
    landscape_count = 0
    portrait_count = 0
    square_count = 0
    raw_count = 0
    skipped_files = []

    with click.progressbar(image_files, label='处理中') as files:
        for filepath in files:
            try:
                filename = filepath.name
                ext = filepath.suffix.lower()

                if is_raw_format(filepath):
                    if copy_raw and not dry_run:
                        raw_out_dir = output / raw_output_dir
                        ensure_directory(raw_out_dir)
                        shutil.copy2(filepath, raw_out_dir / filename)
                    raw_count += 1
                    skipped_files.append((filepath, 'RAW 原片，已跳过水印处理'))
                    continue

                if not is_processable_image(filepath):
                    skipped_files.append((filepath, f'不支持的格式 {ext}，跳过处理'))
                    continue

                orientation = get_orientation(filepath)

                if split_orientation:
                    if orientation == 'landscape':
                        subdir = landscape_dir
                        landscape_count += 1
                    elif orientation == 'portrait':
                        subdir = portrait_dir
                        portrait_count += 1
                    else:
                        subdir = square_dir
                        square_count += 1
                else:
                    subdir = ''

                main_output_dir = output / subdir if subdir else output
                thumb_output_dir = output / thumbnail_dir / subdir if subdir else output / thumbnail_dir

                if not dry_run:
                    ensure_directory(main_output_dir)
                    output_path = main_output_dir / filepath.name
                    try:
                        add_watermark(
                            filepath, output_path,
                            text=text,
                            position=position,
                            opacity=opacity,
                            font_size=font_size
                        )
                    except Exception as e:
                        skipped_files.append((filepath, f'水印处理失败: {e}'))
                        continue

                    if thumbnail:
                        ensure_directory(thumb_output_dir)
                        thumb_path = thumb_output_dir / filepath.name
                        try:
                            create_thumbnail(
                                output_path, thumb_path,
                                max_size=(thumbnail_size, thumbnail_size),
                                quality=quality
                            )
                        except Exception as e:
                            skipped_files.append((filepath, f'缩略图生成失败: {e}'))

                processed_count += 1

            except Exception as e:
                click.echo(f'\n处理 {filepath.name} 时出错: {e}')
                skipped_files.append((filepath, str(e)))

    if report_skipped_path and not dry_run:
        skipped_dir = Path(report_skipped_path).parent
        ensure_directory(skipped_dir)
        with open(report_skipped_path, 'w', encoding='utf-8') as f:
            for fp, reason in skipped_files:
                f.write(f'{fp}|{reason}\n')

    click.echo(f'\n处理完成:')
    click.echo(f'  总照片数: {len(image_files)}')
    click.echo(f'  成功加水印: {processed_count} 张')
    if split_orientation:
        click.echo(f'  横图: {landscape_count} 张')
        click.echo(f'  竖图: {portrait_count} 张')
        click.echo(f'  方图: {square_count} 张')
    if raw_count > 0:
        click.echo(f'  RAW 原片: {raw_count} 张 (已复制到 {raw_output_dir}/)')
    if skipped_files:
        click.echo(f'  跳过: {len(skipped_files)} 个文件')
        for fp, reason in skipped_files[:5]:
            click.echo(f'    - {fp.name}: {reason}')
        if len(skipped_files) > 5:
            click.echo(f'    ... 还有 {len(skipped_files) - 5} 个')
    if thumbnail:
        click.echo(f'  已生成缩略图')
    click.echo(f'  输出目录: {output}')
