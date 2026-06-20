import click
from pathlib import Path

from photo_organizer.core.file_utils import list_image_files, ensure_directory
from photo_organizer.core.image_utils import add_watermark, create_thumbnail, get_orientation


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', required=True, type=click.Path(file_okay=False, dir_okay=True),
              help='输出目录')
@click.option('--text', '-t', required=True, help='水印文字')
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
@click.option('--recursive/--no-recursive', default=False,
              help='是否递归扫描子目录 (默认: 否)')
@click.option('--quality', default=85, type=click.IntRange(1, 100),
              help='JPEG 输出质量 (默认: 85)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际处理文件')
def watermark_cmd(source_dir, output, text, position, opacity, font_size,
                  thumbnail, thumbnail_size, thumbnail_dir,
                  split_orientation, landscape_dir, portrait_dir, square_dir,
                  recursive, quality, dry_run):
    """统一加水印、生成缩略图、按横竖构图分文件夹"""
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

    with click.progressbar(image_files, label='处理中') as files:
        for filepath in files:
            try:
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
                    add_watermark(
                        filepath, output_path,
                        text=text,
                        position=position,
                        opacity=opacity,
                        font_size=font_size
                    )

                    if thumbnail:
                        ensure_directory(thumb_output_dir)
                        thumb_path = thumb_output_dir / filepath.name
                        create_thumbnail(
                            output_path, thumb_path,
                            max_size=(thumbnail_size, thumbnail_size),
                            quality=quality
                        )

                processed_count += 1

            except Exception as e:
                click.echo(f'\n处理 {filepath.name} 时出错: {e}')

    click.echo(f'\n处理完成:')
    click.echo(f'  总照片数: {len(image_files)}')
    click.echo(f'  成功处理: {processed_count} 张')
    if split_orientation:
        click.echo(f'  横图: {landscape_count} 张')
        click.echo(f'  竖图: {portrait_count} 张')
        click.echo(f'  方图: {square_count} 张')
    if thumbnail:
        click.echo(f'  已生成缩略图')
    click.echo(f'  输出目录: {output}')
