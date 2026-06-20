import os
import shutil
import zipfile
import click
import json
from pathlib import Path
from datetime import datetime

from photo_organizer.core.file_utils import ensure_directory
from photo_organizer.core.config import resolve_preset


ARCHIVE_DIR_NAMES = {
    'import': '01_imported',
    'rename': '02_renamed',
    'select': '03_selected',
    'watermark': '04_watermarked',
    'pack': '05_packed',
    'report': '06_report',
}

STATE_FILES = [
    '.delivery_state.json',
    '.rename_mapping.json',
]


def generate_archive_name(client=None, session=None, suffix=None):
    """生成归档目录名"""
    parts = []
    date_str = datetime.now().strftime('%Y%m%d')
    parts.append(date_str)
    if client:
        parts.append(client)
    if session:
        parts.append(session)
    if suffix:
        parts.append(suffix)
    return '_'.join(parts)


def collect_archive_items(work_dir, include_intermediate=True,
                          include_pack=True, include_report=True,
                          include_state=True):
    """收集需要归档的目录和文件"""
    work_dir = Path(work_dir)
    items = []

    dirs_to_check = []
    if include_intermediate:
        dirs_to_check.extend(['01_imported', '02_renamed', '03_selected', '04_watermarked'])
    if include_pack:
        dirs_to_check.append('05_packed')
    if include_report:
        dirs_to_check.append('06_report')

    for dir_name in dirs_to_check:
        dir_path = work_dir / dir_name
        if dir_path.exists():
            items.append(('dir', dir_path, dir_name))

    if include_state:
        for state_file in STATE_FILES:
            state_path = work_dir / state_file
            if state_path.exists():
                items.append(('file', state_path, state_file))

    project_config = work_dir.parent / 'photo_project.json'
    if project_config.exists():
        items.append(('file', project_config, 'photo_project.json'))

    return items


def create_zip_archive(items, archive_path, base_dir_name=None):
    """将项目打包为 zip 归档"""
    archive_path = Path(archive_path)
    ensure_directory(archive_path.parent)

    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item_type, item_path, rel_name in items:
            if item_type == 'dir':
                for root, dirs, files in os.walk(item_path):
                    root_path = Path(root)
                    for file in files:
                        file_path = root_path / file
                        arcname = file_path.relative_to(item_path.parent)
                        if base_dir_name:
                            arcname = Path(base_dir_name) / arcname
                        zf.write(file_path, arcname)
            elif item_type == 'file':
                arcname = Path(rel_name)
                if base_dir_name:
                    arcname = Path(base_dir_name) / arcname
                zf.write(item_path, arcname)

    return archive_path


def move_to_archive(items, archive_dir):
    """将项目移动到归档目录"""
    archive_dir = Path(archive_dir)
    ensure_directory(archive_dir)

    moved = []
    for item_type, item_path, rel_name in items:
        dest_path = archive_dir / rel_name
        try:
            if dest_path.exists():
                if dest_path.is_dir():
                    shutil.rmtree(dest_path)
                else:
                    dest_path.unlink()
            shutil.move(str(item_path), str(dest_path))
            moved.append((item_type, rel_name))
        except Exception as e:
            click.echo(f'  移动失败: {rel_name} - {e}')

    return moved


@click.command()
@click.option('--work-dir', '-o', 'work_dir', default=None,
              help='工作目录 (默认从项目配置读取 output)')
@click.option('--archive-dir', default='./archive',
              help='归档根目录 (默认: ./archive)')
@click.option('--name', '-n', default=None,
              help='归档名称 (默认: 日期_客户_场次)')
@click.option('--client', '-c', default=None, help='客户名称')
@click.option('--session', '-s', default=None, help='场次编号')
@click.option('--zip/--no-zip', default=True,
              help='是否打包为 zip 文件 (默认: 是)')
@click.option('--include-intermediate/--no-intermediate', default=True,
              help='是否包含中间目录 (01_imported ~ 04_watermarked) (默认: 是)')
@click.option('--include-pack/--no-pack', default=True,
              help='是否包含交付包 (05_packed) (默认: 是)')
@click.option('--include-report/--no-report', default=True,
              help='是否包含报告 (06_report) (默认: 是)')
@click.option('--include-state/--no-state', default=True,
              help='是否包含状态文件 (默认: 是)')
@click.option('--delete-source/--keep-source', default=False,
              help='归档后是否删除源文件 (仅在 --no-zip 时生效，默认: 否)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--dry-run', is_flag=True,
              help='试运行，不实际执行归档操作')
@click.option('--yes', '-y', is_flag=True,
              help='跳过确认提示')
def archive_cmd(work_dir, archive_dir, name, client, session, zip,
                include_intermediate, include_pack, include_report,
                include_state, delete_source, preset, dry_run, yes):
    """归档交付项目（中间目录、状态文件、交付包、报告）

    将指定工作目录的内容按项目归档，避免多个活动的交付文件混在一起。
    默认从项目配置读取 output 作为工作目录。
    """
    resolved = resolve_preset(
        preset,
        {'output': work_dir, 'client': client, 'session': session},
        {'output': None, 'client': None, 'session': None}
    )
    work_dir = resolved['output']
    client = resolved['client']
    session = resolved['session']

    if not work_dir:
        click.echo('错误: 请通过 --work-dir 指定工作目录，或在项目配置中设置 output')
        return

    work_dir = Path(work_dir)
    if not work_dir.exists():
        click.echo(f'错误: 工作目录不存在: {work_dir}')
        return

    archive_dir = Path(archive_dir)
    if not name:
        name = generate_archive_name(client, session)

    click.echo('=' * 60)
    click.echo('项目归档')
    click.echo('=' * 60)
    click.echo(f'工作目录: {work_dir}')
    click.echo(f'归档目录: {archive_dir}')
    click.echo(f'归档名称: {name}')
    if client or session:
        click.echo(f'客户: {client or "(未设置)"} | 场次: {session or "(未设置)"}')
    click.echo('')

    items = collect_archive_items(
        work_dir,
        include_intermediate=include_intermediate,
        include_pack=include_pack,
        include_report=include_report,
        include_state=include_state,
    )

    if not items:
        click.echo('没有找到可归档的内容')
        return

    click.echo('将归档以下内容:')
    dir_count = sum(1 for t, _, _ in items if t == 'dir')
    file_count = sum(1 for t, _, _ in items if t == 'file')
    click.echo(f'  目录: {dir_count} 个')
    click.echo(f'  文件: {file_count} 个')
    for item_type, item_path, rel_name in items:
        icon = '[DIR]' if item_type == 'dir' else '[FILE]'
        click.echo(f'    {icon} {rel_name}')
    click.echo('')

    if zip:
        archive_path = archive_dir / f'{name}.zip'
        click.echo(f'归档方式: 打包为 zip 文件')
        click.echo(f'目标文件: {archive_path}')
    else:
        archive_path = archive_dir / name
        click.echo(f'归档方式: 移动到归档目录')
        click.echo(f'目标目录: {archive_path}')
        if delete_source:
            click.echo(f'归档后将删除源文件')
    click.echo('')

    if not yes and not dry_run:
        confirm = click.confirm('确认执行归档?', default=True)
        if not confirm:
            click.echo('已取消')
            return

    if dry_run:
        click.echo('[试运行] 不会实际执行归档操作')
        return

    if archive_path.exists():
        if not yes:
            confirm = click.confirm(f'{archive_path} 已存在，是否覆盖?', default=False)
            if not confirm:
                click.echo('已取消')
                return
        if archive_path.is_dir():
            shutil.rmtree(archive_path)
        else:
            archive_path.unlink()

    ensure_directory(archive_dir)

    if zip:
        click.echo('\n正在创建 zip 归档...')
        create_zip_archive(items, archive_path, base_dir_name=name)
        size_mb = archive_path.stat().st_size / (1024 * 1024)
        click.echo(f'归档完成: {archive_path} ({size_mb:.2f} MB)')
    else:
        click.echo('\n正在移动文件...')
        moved = move_to_archive(items, archive_path)
        click.echo(f'归档完成，已移动 {len(moved)} 项到: {archive_path}')

        if delete_source:
            remaining = [p for _, p, _ in items if p.exists()]
            if remaining:
                click.echo('\n以下源文件未被移动，不会删除:')
                for p in remaining:
                    click.echo(f'  - {p}')
            else:
                if work_dir.exists() and not any(work_dir.iterdir()):
                    work_dir.rmdir()
                    click.echo(f'已删除空的工作目录: {work_dir}')

    click.echo('')
    click.echo('归档完成，可以安全地开始下一个项目了。')
