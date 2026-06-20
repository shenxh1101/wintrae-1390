import click
import json
from pathlib import Path

from photo_organizer.core.exif_utils import get_capture_date
from photo_organizer.core.file_utils import list_image_files, copy_file, ensure_directory
from photo_organizer.core.naming import generate_filename, DEFAULT_TEMPLATE
from photo_organizer.core.config import resolve_preset


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', default=None, help='输出目录')
@click.option('--client', '-c', default=None, help='客户名称')
@click.option('--session', '-s', default=None, help='场次编号 (默认: 1)')
@click.option('--start-num', default=1, type=int, help='起始序号 (默认: 1)')
@click.option('--template', default=None,
              help=f'命名模板 (默认: {DEFAULT_TEMPLATE})')
@click.option('--sort-by', default='date',
              type=click.Choice(['date', 'name', 'size']),
              help='排序方式 (默认: date)')
@click.option('--keep-original/--move', default=True,
              help='保留原图或移动文件 (默认: 保留)')
@click.option('--recursive/--no-recursive', default=False,
              help='是否递归扫描子目录 (默认: 否)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--save-mapping/--no-save-mapping', default=True,
              help='是否保存原名到新名的映射文件 (默认: 是)')
@click.option('--mapping-file', default=None,
              help='映射文件输出路径 (默认: 输出目录/.rename_mapping.json)')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际重命名')
def rename_cmd(source_dir, output, client, session, start_num, template,
               sort_by, keep_original, recursive, preset, save_mapping,
               mapping_file, dry_run):
    """依据客户名、场次、序号批量重命名照片"""
    resolved = resolve_preset(
        preset,
        {'output': output, 'client': client, 'session': session,
         'start_num': start_num, 'template': template},
        {'output': None, 'client': None, 'session': '1',
         'start_num': 1, 'template': DEFAULT_TEMPLATE}
    )
    output = resolved['output']
    client = resolved['client']
    session = resolved['session']
    start_num = resolved['start_num']
    template = resolved['template']

    if not output:
        click.echo('错误: 请指定输出目录 (--output 或在 preset 中配置)')
        return
    if not client:
        click.echo('错误: 请指定客户名称 (--client 或在 preset 中配置)')
        return

    source_dir = Path(source_dir)
    output = Path(output)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    if sort_by == 'date':
        image_files.sort(key=lambda f: get_capture_date(f) or f.stat().st_mtime)
    elif sort_by == 'name':
        image_files.sort(key=lambda f: f.name)
    elif sort_by == 'size':
        image_files.sort(key=lambda f: f.stat().st_size)

    renamed_count = 0
    skipped_count = 0
    rename_mapping = {}

    with click.progressbar(enumerate(image_files, start=start_num),
                           length=len(image_files),
                           label='重命名中') as files:
        for seq, filepath in files:
            try:
                ext = filepath.suffix.lower()
                new_filename = generate_filename(
                    template,
                    client=client,
                    session=session,
                    seq=seq,
                    ext=''
                )
                new_filename = f"{new_filename}{ext}"

                dest_path = output / new_filename

                if not dry_run:
                    ensure_directory(output)
                    if dest_path.exists():
                        skipped_count += 1
                        continue
                    copy_file(filepath, dest_path, keep_original=keep_original)

                try:
                    rel_path = filepath.relative_to(source_dir)
                except ValueError:
                    rel_path = Path(filepath.name)
                rename_mapping[str(rel_path)] = new_filename
                rename_mapping[filepath.name] = new_filename
                rename_mapping[filepath.stem] = new_filename

                renamed_count += 1

            except Exception as e:
                click.echo(f'\n处理 {filepath.name} 时出错: {e}')
                skipped_count += 1

    if save_mapping and rename_mapping and not dry_run:
        if mapping_file:
            map_path = Path(mapping_file)
        else:
            map_path = output / '.rename_mapping.json'
        ensure_directory(map_path.parent)
        map_data = {
            'source_dir': str(source_dir),
            'output_dir': str(output),
            'client': client,
            'session': str(session),
            'template': template,
            'mapping': rename_mapping,
        }
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump(map_data, f, ensure_ascii=False, indent=2)
        click.echo(f'  映射文件: {map_path}')

    click.echo(f'\n重命名完成:')
    click.echo(f'  成功: {renamed_count} 张')
    click.echo(f'  跳过: {skipped_count} 张')
    click.echo(f'  输出目录: {output}')
    click.echo(f'  命名模板: {template}')
    if renamed_count > 0:
        sample = generate_filename(
            template,
            client=client,
            session=session,
            seq=start_num,
            ext=image_files[0].suffix.lower()
        )
        click.echo(f'  示例文件名: {sample}')
