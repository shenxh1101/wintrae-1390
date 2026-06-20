import re
import click
from pathlib import Path
from datetime import datetime

from photo_organizer.core.exif_utils import get_capture_date, get_camera_model, get_image_size
from photo_organizer.core.file_utils import list_image_files, find_duplicate_files, ensure_directory
from photo_organizer.core.naming import extract_sequence
from photo_organizer.core.config import resolve_preset


def find_missing_sequences(file_list, start_num=1):
    sequences = []
    seq_width = 4
    for filepath in file_list:
        seq = extract_sequence(filepath.stem)
        if seq is not None:
            sequences.append(seq)
            if filepath.stem:
                match = re.search(r'(\d+)\s*$', filepath.stem)
                if match:
                    seq_width = max(seq_width, len(match.group(1)))

    if not sequences:
        return [], seq_width

    sequences = sorted(set(sequences))
    min_seq = min(sequences) if start_num is None else min(start_num, sequences[0])
    max_seq = max(sequences)

    missing = []
    for i in range(min_seq, max_seq + 1):
        if i not in sequences:
            missing.append(i)

    return missing, seq_width


def generate_report_text(stats, missing_seqs, duplicates, file_list, output_file=None,
                         skipped_files=None, seq_width=4):
    lines = []
    lines.append('=' * 60)
    lines.append('照片整理报告')
    lines.append('=' * 60)
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    lines.append('【照片数量统计】')
    lines.append(f'  总照片数: {stats["total"]} 张')
    if 'by_extension' in stats:
        lines.append('  按格式:')
        for ext, count in sorted(stats['by_extension'].items()):
            lines.append(f'    {ext}: {count} 张')
    if 'by_date' in stats:
        lines.append('  按日期:')
        for date, count in sorted(stats['by_date'].items()):
            lines.append(f'    {date}: {count} 张')
    if 'by_camera' in stats:
        lines.append('  按相机:')
        for camera, count in sorted(stats['by_camera'].items()):
            lines.append(f'    {camera}: {count} 张')
    lines.append('')

    if missing_seqs:
        lines.append('【缺失编号】')
        lines.append(f'  共缺失 {len(missing_seqs)} 个编号:')
        formatted = ', '.join(f'{s:0{seq_width}d}' for s in missing_seqs)
        lines.append(f'  {formatted}')
        lines.append('')

    if skipped_files:
        lines.append('【跳过的文件】')
        lines.append(f'  共 {len(skipped_files)} 个文件被跳过:')
        for filepath, reason in skipped_files:
            lines.append(f'  - {filepath.name}: {reason}')
        lines.append('')

    if duplicates:
        lines.append('【重复文件】')
        lines.append(f'  发现 {len(duplicates)} 组重复文件:')
        for i, (f1, f2) in enumerate(duplicates, 1):
            lines.append(f'  第{i}组:')
            lines.append(f'    - {f1}')
            lines.append(f'    - {f2}')
        lines.append('')

    lines.append('【交付清单】')
    lines.append(f'  共 {len(file_list)} 张照片:')
    for i, filepath in enumerate(file_list, 1):
        filename = filepath.name
        size_kb = filepath.stat().st_size / 1024
        lines.append(f'  {i:4d}. {filename} ({size_kb:.1f} KB)')
    lines.append('')

    lines.append('=' * 60)
    lines.append('报告结束')
    lines.append('=' * 60)

    report_text = '\n'.join(lines)

    if output_file:
        ensure_directory(Path(output_file).parent)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)

    return report_text


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', default=None, help='报告输出文件路径')
@click.option('--start-num', default=1, type=int, help='起始序号 (默认: 1)')
@click.option('--check-duplicates/--no-check-duplicates', default=True,
              help='是否检测重复文件 (默认: 是)')
@click.option('--check-sequence/--no-check-sequence', default=True,
              help='是否检测缺失编号 (默认: 是)')
@click.option('--delivery-list/--no-delivery-list', default=True,
              help='是否生成交付清单 (默认: 是)')
@click.option('--recursive/--no-recursive', default=True,
              help='是否递归扫描子目录 (默认: 是)')
@click.option('--format', 'report_format', default='text',
              type=click.Choice(['text', 'csv']),
              help='报告格式 (默认: text)')
@click.option('--group-by-date/--no-group-by-date', default=False,
              help='是否按日期统计 (默认: 否)')
@click.option('--group-by-camera/--no-group-by-camera', default=False,
              help='是否按相机统计 (默认: 否)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--skipped-files', 'skipped_files_opt', multiple=True,
              type=(click.Path(), str),
              help='跳过的文件列表 (用于报告记录)，格式: --skipped-files FILEPATH REASON')
def report_cmd(source_dir, output, start_num, check_duplicates, check_sequence,
               delivery_list, recursive, report_format, group_by_date, group_by_camera,
               preset, skipped_files_opt):
    """输出照片数量、缺失编号、重复文件和交付清单"""
    resolved = resolve_preset(
        preset,
        {'output': output, 'start_num': start_num},
        {'output': None, 'start_num': 1}
    )
    output = resolved['output']
    start_num = resolved['start_num']

    source_dir = Path(source_dir)

    click.echo(f'扫描目录: {source_dir}')
    image_files = list_image_files(source_dir, recursive=recursive)
    click.echo(f'找到 {len(image_files)} 张照片')

    if not image_files:
        click.echo('没有找到照片文件')
        return

    skipped_files = []
    if skipped_files_opt:
        for fp, reason in skipped_files_opt:
            skipped_files.append((Path(fp), reason))

    stats = {'total': len(image_files)}

    by_extension = {}
    for f in image_files:
        ext = f.suffix.lower()
        by_extension[ext] = by_extension.get(ext, 0) + 1
    stats['by_extension'] = by_extension

    if group_by_date:
        by_date = {}
        with click.progressbar(image_files, label='分析日期') as files:
            for f in files:
                date = get_capture_date(f)
                if date:
                    date_str = date.strftime('%Y-%m-%d')
                else:
                    date_str = 'unknown'
                by_date[date_str] = by_date.get(date_str, 0) + 1
        stats['by_date'] = by_date

    if group_by_camera:
        by_camera = {}
        with click.progressbar(image_files, label='分析相机') as files:
            for f in files:
                camera = get_camera_model(f) or 'unknown'
                by_camera[camera] = by_camera.get(camera, 0) + 1
        stats['by_camera'] = by_camera

    missing_seqs = []
    seq_width = 4
    if check_sequence:
        click.echo('检查编号连续性...')
        missing_seqs, seq_width = find_missing_sequences(image_files, start_num=start_num)
        if missing_seqs:
            formatted = ', '.join(f'{s:0{seq_width}d}' for s in missing_seqs)
            click.echo(f'  发现 {len(missing_seqs)} 个缺失编号: {formatted}')
        else:
            click.echo('  编号连续，无缺失')

    duplicates = []
    if check_duplicates:
        click.echo('检测重复文件...')
        duplicates = find_duplicate_files(image_files)
        if duplicates:
            click.echo(f'  发现 {len(duplicates)} 组重复文件')
        else:
            click.echo('  未发现重复文件')

    click.echo('生成报告...')
    if report_format == 'text':
        report_text = generate_report_text(
            stats, missing_seqs, duplicates, image_files, output,
            skipped_files=skipped_files, seq_width=seq_width
        )
        if not output:
            click.echo('')
            click.echo(report_text)
    elif report_format == 'csv':
        if output:
            ensure_directory(Path(output).parent)
            with open(output, 'w', encoding='utf-8-sig') as f:
                f.write('序号,文件名,大小(KB),日期,相机,宽度,高度\n')
                for i, filepath in enumerate(image_files, 1):
                    try:
                        date = get_capture_date(filepath)
                        date_str = date.strftime('%Y-%m-%d %H:%M:%S') if date else ''
                        camera = get_camera_model(filepath) or ''
                        width, height = get_image_size(filepath)
                        size_kb = filepath.stat().st_size / 1024
                        f.write(f'{i},"{filepath.name}",{size_kb:.1f},"{date_str}","{camera}",{width or ""},{height or ""}\n')
                    except Exception:
                        pass
            click.echo(f'CSV 报告已保存到: {output}')
        else:
            click.echo('CSV 格式请指定 --output 参数')

    if output and report_format == 'text':
        click.echo(f'报告已保存到: {output}')
