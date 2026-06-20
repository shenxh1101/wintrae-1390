import os
import sys
import click
import json
from pathlib import Path
from datetime import datetime

from photo_organizer.core.file_utils import ensure_directory, list_image_files
from photo_organizer.core.config import (
    apply_preset_to_options, get_preset,
    load_project_config
)
from photo_organizer.core.delivery_state import (
    DELIVERY_STEPS, load_state, save_state,
    mark_step_started, mark_step_completed, mark_step_failed,
    is_step_completed, get_pending_steps, clear_state
)
from photo_organizer.core.naming import DEFAULT_TEMPLATE

from photo_organizer.commands.import_cmd import import_cmd
from photo_organizer.commands.rename_cmd import rename_cmd
from photo_organizer.commands.select_cmd import select_cmd
from photo_organizer.commands.watermark_cmd import watermark_cmd
from photo_organizer.commands.pack_cmd import pack_cmd
from photo_organizer.commands.report_cmd import report_cmd


def _resolve_config_value(cli_value, preset_cfg, project_cfg, default=None):
    """按优先级解析配置值：CLI > preset > project config > default"""
    if cli_value is not None and cli_value != default:
        return cli_value
    if preset_cfg and cli_value in preset_cfg:
        return preset_cfg[cli_value] if False else preset_cfg
    if preset_cfg:
        return preset_cfg
    if project_cfg:
        return project_cfg
    return default


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', required=True, type=click.Path(file_okay=False, dir_okay=True),
              help='工作/输出根目录')
@click.option('--preset', '-p', help='使用预设配置名')
@click.option('--use-project-config/--no-project-config', default=True,
              help='是否读取项目目录的 photo_project.json (默认: 是)')
@click.option('--client', '-c', help='客户名称')
@click.option('--session', '-s', help='场次编号')
@click.option('--template', help=f'命名模板 (默认: {DEFAULT_TEMPLATE})')
@click.option('--watermark-text', '-t', 'watermark_text', help='水印文字')
@click.option('--steps', help='要执行的步骤，逗号分隔: import,rename,select,watermark,pack,report')
@click.option('--from-step', 'from_step', type=click.Choice(DELIVERY_STEPS),
              help='从指定步骤开始执行（断点续跑）')
@click.option('--only-step', 'only_step', type=click.Choice(DELIVERY_STEPS),
              help='只执行单个步骤')
@click.option('--reset', is_flag=True,
              help='清除之前的流程状态，从头开始')
@click.option('--list-file', '-l', type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help='精修图筛选清单文件')
@click.option('--dry-run', is_flag=True, help='试运行，不实际执行文件操作')
@click.option('--yes', '-y', is_flag=True, help='跳过所有确认提示')
def delivery_cmd(source_dir, output, preset, use_project_config,
                 client, session, template, watermark_text,
                 steps, from_step, only_step, reset,
                 list_file, dry_run, yes):
    """完整交付流程：import → rename → select → watermark → pack → report

    支持断点续跑：再次执行同一命令会自动从上次失败或未完成的步骤继续。
    使用 --reset 清除状态从头开始。
    """
    source_dir = Path(source_dir)
    output = Path(output)

    if reset:
        clear_state(output)
        click.echo('已清除之前的流程状态')

    state = load_state(output)
    if not state.get('started_at'):
        state['started_at'] = datetime.now().isoformat()

    preset_cfg = get_preset(preset) if preset else {}
    project_cfg = load_project_config(source_dir) if use_project_config else {}
    project_cfg_output = load_project_config(output) if use_project_config else {}
    if project_cfg_output:
        project_cfg.update(project_cfg_output)

    def _get(key, default=None):
        if preset_cfg and key in preset_cfg:
            return preset_cfg[key]
        if project_cfg and key in project_cfg:
            return project_cfg[key]
        return default

    client = client or _get('client')
    session = session or _get('session', '1')
    template = template or _get('template', DEFAULT_TEMPLATE)
    watermark_text = watermark_text or _get('text')
    pack_name = _get('name', 'delivery')
    base_dir = _get('base_dir')
    group_by = _get('group_by', 'date,camera')

    if not client:
        if not yes:
            client = click.prompt('请输入客户名称', type=str)
        else:
            client = 'client'
    if not watermark_text:
        if not yes:
            watermark_text = click.prompt('请输入水印文字', type=str, default=client)
        else:
            watermark_text = client

    if only_step:
        selected_steps = [only_step]
    elif steps:
        selected_steps = [s.strip() for s in steps.split(',') if s.strip() in DELIVERY_STEPS]
    else:
        selected_steps = DELIVERY_STEPS.copy()

    if 'select' in selected_steps and not list_file:
        selected_steps.remove('select')
        click.echo('提示: 未提供 --list-file，跳过 select 步骤')

    pending = get_pending_steps(state, selected_steps, from_step)

    if not pending:
        click.echo('所有步骤均已完成！')
        if not yes and click.confirm('是否清除流程状态文件?', default=True):
            clear_state(output)
            click.echo('已清除状态文件')
        return

    ensure_directory(output)

    subdirs = {
        'import': output / '01_imported',
        'rename': output / '02_renamed',
        'select': output / '03_selected',
        'watermark': output / '04_watermarked',
        'pack': output / '05_packed',
        'report': output / '06_report',
    }

    click.echo('=' * 60)
    click.echo('照片交付流程')
    click.echo('=' * 60)
    click.echo(f'源目录: {source_dir}')
    click.echo(f'工作目录: {output}')
    click.echo(f'客户: {client} | 场次: {session}')
    click.echo(f'水印文字: "{watermark_text}"')
    if preset:
        click.echo(f'预设: {preset}')
    click.echo(f'待执行步骤: {" → ".join(pending)}')
    click.echo('=' * 60)

    if not yes and not click.confirm('开始执行?', default=True):
        click.echo('已取消')
        return

    for step in pending:
        step_label = {
            'import': '第1步: 导入照片',
            'rename': '第2步: 批量重命名',
            'select': '第3步: 筛选精修图',
            'watermark': '第4步: 加水印/缩略图/横竖分类',
            'pack': '第5步: 打包交付',
            'report': '第6步: 生成整理报告',
        }[step]

        click.echo(f'\n>>> {step_label} <<<')
        state = mark_step_started(state, step)
        save_state(output, state)

        try:
            if step == 'import':
                src = source_dir
                dst = subdirs['import']
                click.echo(f'  输入: {src}')
                click.echo(f'  输出: {dst}')
                if not dry_run:
                    from click.testing import CliRunner
                    runner = CliRunner()
                    result = runner.invoke(
                        import_cmd,
                        [str(src), '-o', str(dst), '--group-by', group_by]
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {'src': str(src), 'dst': str(dst)})

            elif step == 'rename':
                src = subdirs['import'] if subdirs['import'].exists() else source_dir
                dst = subdirs['rename']
                click.echo(f'  输入: {src}')
                click.echo(f'  输出: {dst}')
                if not dry_run:
                    from click.testing import CliRunner
                    runner = CliRunner()
                    result = runner.invoke(
                        rename_cmd,
                        [str(src), '-o', str(dst), '-c', client, '-s', str(session),
                         '--template', template]
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {'src': str(src), 'dst': str(dst)})

            elif step == 'select':
                src = subdirs['rename']
                dst = subdirs['select']
                click.echo(f'  输入: {src}')
                click.echo(f'  输出: {dst}')
                click.echo(f'  清单: {list_file}')
                if not dry_run:
                    from click.testing import CliRunner
                    runner = CliRunner()
                    result = runner.invoke(
                        select_cmd,
                        [str(src), '-o', str(dst), '-l', str(list_file),
                         '--mode', 'list-only']
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {'src': str(src), 'dst': str(dst)})

            elif step == 'watermark':
                src = subdirs['select'] if subdirs['select'].exists() else subdirs['rename']
                if not src.exists():
                    src = source_dir
                dst = subdirs['watermark']
                click.echo(f'  输入: {src}')
                click.echo(f'  输出: {dst}')
                skipped_log = output / 'skipped_files.txt'
                if not dry_run:
                    from click.testing import CliRunner
                    runner = CliRunner()
                    result = runner.invoke(
                        watermark_cmd,
                        [str(src), '-o', str(dst), '-t', watermark_text,
                         '--report-skipped', str(skipped_log)]
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'skipped_log': str(skipped_log)
                })

            elif step == 'pack':
                src = subdirs['watermark']
                dst = subdirs['pack']
                click.echo(f'  输入: {src}')
                click.echo(f'  输出: {dst}')
                if not dry_run:
                    from click.testing import CliRunner
                    runner = CliRunner()
                    base_dir_arg = []
                    if base_dir:
                        base_dir_arg = ['--base-dir', base_dir]
                    result = runner.invoke(
                        pack_cmd,
                        [str(src), '-o', str(dst), '-n', pack_name,
                         '--split-by-orientation'] + base_dir_arg
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {'src': str(src), 'dst': str(dst)})

            elif step == 'report':
                src = subdirs['watermark'] if subdirs['watermark'].exists() else subdirs['rename']
                if not src.exists():
                    src = source_dir
                dst = subdirs['report']
                report_file = dst / f'{client}_delivery_report.txt'
                click.echo(f'  扫描目录: {src}')
                click.echo(f'  报告输出: {report_file}')
                if not dry_run:
                    ensure_directory(dst)
                    skipped_files_arg = []
                    skipped_log = output / 'skipped_files.txt'
                    if skipped_log.exists():
                        with open(skipped_log, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if '|' in line:
                                    fp, reason = line.split('|', 1)
                                    skipped_files_arg.extend(['--skipped-files', fp, reason])
                    from click.testing import CliRunner
                    runner = CliRunner()
                    cmd_args = [str(src), '-o', str(report_file),
                                '--group-by-date', '--group-by-camera'] + skipped_files_arg
                    result = runner.invoke(report_cmd, cmd_args)
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                state = mark_step_completed(state, step, {
                    'scan_dir': str(src), 'report_file': str(report_file)
                })

            save_state(output, state)
            click.echo(f'  [OK] 步骤完成')

        except Exception as e:
            state = mark_step_failed(state, step, str(e))
            save_state(output, state)
            click.echo(f'  [FAIL] 步骤失败: {e}')
            click.echo(f'\n流程中断！修复问题后再次执行相同命令即可从该步骤继续。')
            click.echo(f'或使用 --from-step {step} 从该步骤重试，--reset 从头开始。')
            sys.exit(1)

    state['completed_at'] = datetime.now().isoformat()
    save_state(output, state)

    click.echo('\n' + '=' * 60)
    click.echo('全部完成！')
    click.echo('=' * 60)
    click.echo(f'工作目录: {output}')
    if subdirs['pack'].exists():
        click.echo(f'交付压缩包: {subdirs["pack"]}')
    if subdirs['report'].exists():
        report_file = subdirs['report'] / f'{client}_delivery_report.txt'
        if report_file.exists():
            click.echo(f'整理报告: {report_file}')
    click.echo(f'流程状态: {output}/.delivery_state.json')
    click.echo('=' * 60)
