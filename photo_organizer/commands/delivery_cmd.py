import json
import os
import sys
import click
from pathlib import Path
from datetime import datetime

from photo_organizer.core.file_utils import ensure_directory, list_image_files
from photo_organizer.core.config import resolve_preset, get_active_project_config
from photo_organizer.core.delivery_state import (
    DELIVERY_STEPS, load_state, save_state,
    mark_step_started, mark_step_completed, mark_step_failed,
    is_step_completed, get_pending_steps, is_delivery_complete, clear_state,
    get_completed_steps
)
from photo_organizer.core.naming import DEFAULT_TEMPLATE

from photo_organizer.commands.import_cmd import import_cmd
from photo_organizer.commands.rename_cmd import rename_cmd
from photo_organizer.commands.select_cmd import select_cmd
from photo_organizer.commands.watermark_cmd import watermark_cmd
from photo_organizer.commands.pack_cmd import pack_cmd
from photo_organizer.commands.report_cmd import report_cmd


STEP_LABELS = {
    'import': '第1步: 导入照片',
    'rename': '第2步: 批量重命名',
    'select': '第3步: 筛选精修图',
    'watermark': '第4步: 加水印/缩略图/横竖分类',
    'pack': '第5步: 打包交付',
    'report': '第6步: 生成整理报告',
}


@click.group(invoke_without_command=True)
@click.option('--output', '-o', default=None, help='工作/输出根目录')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--use-project-config/--no-project-config', default=True,
              help='是否读取项目目录的 photo_project.json (默认: 是)')
@click.pass_context
def delivery_cmd(ctx, output, preset, use_project_config):
    """完整交付流程: import -> rename -> select -> watermark -> pack -> report

    子命令:
      run     执行完整交付流程
      status  查看交付流程各步骤状态

    支持断点续跑: 再次执行同一命令会自动从上次失败处继续。
    已全部完成时再执行会直接提示，不会重复跑。如需重跑特定步骤，
    请使用 --from-step 或 --only-step 明确指定。
    """
    if ctx.invoked_subcommand is not None:
        return

    # 没有子命令时：尝试从项目配置读取 output，然后显示状态
    if not output:
        proj_dir_arg = None if use_project_config else '__disabled__'
        resolved = resolve_preset(
            preset,
            {'output': None},
            {'output': None},
            project_dir=proj_dir_arg
        )
        output = resolved.get('output')

    if output:
        ctx.invoke(delivery_status, output=output,
                   use_project_config=use_project_config, as_json=False)
    else:
        click.echo(ctx.get_help())
        click.echo('')
        click.echo('提示: 如已初始化项目配置 (photo_project.json)，在该目录运行可直接查看状态。')
        click.echo('      或通过 --output 指定工作目录: photo delivery -o <目录> status')


@delivery_cmd.command(name='run')
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True), required=True)
@click.option('--output', '-o', default=None, help='工作/输出根目录')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
@click.option('--use-project-config/--no-project-config', default=True,
              help='是否读取项目目录的 photo_project.json (默认: 是)')
@click.option('--client', '-c', default=None, help='客户名称')
@click.option('--session', '-s', default=None, help='场次编号')
@click.option('--template', default=None, help=f'命名模板 (默认: {DEFAULT_TEMPLATE})')
@click.option('--watermark-text', '-t', 'watermark_text', default=None, help='水印文字')
@click.option('--steps', help='要执行的步骤，逗号分隔: import,rename,select,watermark,pack,report')
@click.option('--from-step', 'from_step', type=click.Choice(DELIVERY_STEPS),
              help='从指定步骤开始执行（断点续跑/强制重跑）')
@click.option('--only-step', 'only_step', type=click.Choice(DELIVERY_STEPS),
              help='只执行单个步骤')
@click.option('--reset', is_flag=True,
              help='清除之前的流程状态，从头开始')
@click.option('--list-file', '-l', type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help='精修图筛选清单文件')
@click.option('--dry-run', is_flag=True, help='试运行，不实际执行文件操作')
@click.option('--yes', '-y', is_flag=True, help='跳过所有确认提示')
def delivery_run(source_dir, output, preset, use_project_config,
                 client, session, template, watermark_text,
                 steps, from_step, only_step, reset,
                 list_file, dry_run, yes):
    """执行完整交付流程 (import -> rename -> select -> watermark -> pack -> report)

    用法示例:
      photo delivery run ./raw_photos -o ./work -p my_preset -y
    """
    _run_delivery(
        source_dir=source_dir,
        output=output,
        preset=preset,
        use_project_config=use_project_config,
        client=client,
        session=session,
        template=template,
        watermark_text=watermark_text,
        steps=steps,
        from_step=from_step,
        only_step=only_step,
        reset=reset,
        list_file=list_file,
        dry_run=dry_run,
        yes=yes,
    )


def _run_delivery(source_dir, output, preset, use_project_config,
                  client, session, template, watermark_text,
                  steps, from_step, only_step, reset,
                  list_file, dry_run, yes):
    source_dir = Path(source_dir)

    proj_dir_arg = None if use_project_config else '__disabled__'
    resolved = resolve_preset(
        preset,
        {'output': output, 'client': client, 'session': session,
         'template': template, 'text': watermark_text,
         'name': None, 'base_dir': None, 'group_by': None},
        {'output': None, 'client': None, 'session': '1',
         'template': DEFAULT_TEMPLATE, 'text': None,
         'name': 'delivery', 'base_dir': None, 'group_by': 'date,camera'},
        project_dir=proj_dir_arg
    )
    output = resolved['output']
    client = resolved['client']
    session = resolved['session']
    template = resolved['template']
    watermark_text = resolved['text']
    pack_name = resolved['name']
    base_dir = resolved['base_dir']
    group_by = resolved['group_by']

    if not output:
        click.echo('错误: 请指定工作目录 (--output 或在 preset 中配置)')
        return

    output = Path(output)

    if reset:
        clear_state(output)
        click.echo('已清除之前的流程状态')

    state = load_state(output)
    if not state.get('started_at'):
        state['started_at'] = datetime.now().isoformat()

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

    if not from_step and not only_step and is_delivery_complete(state, selected_steps):
        click.echo('交付流程已全部完成，无需重复执行。')
        click.echo('如需重跑某一步，请使用 --from-step <步骤名> 或 --only-step <步骤名>。')
        click.echo('如需从头开始，请使用 --reset。')
        click.echo('查看当前状态: photo delivery status -o <工作目录>')
        return

    pending = get_pending_steps(state, selected_steps, from_step)

    if not pending:
        if from_step or only_step:
            pass
        else:
            click.echo('没有待执行的步骤。')
            click.echo('查看当前状态: photo delivery status -o <工作目录>')
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
    click.echo(f'待执行步骤: {" -> ".join(pending)}')
    click.echo('=' * 60)

    if not yes and not click.confirm('开始执行?', default=True):
        click.echo('已取消')
        return

    for step in pending:
        step_label = STEP_LABELS[step]

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
                file_count = len(list_image_files(dst, recursive=True)) if dst.exists() else 0
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'file_count': file_count, 'group_by': group_by
                })

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
                         '--template', template, '--recursive']
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                file_count = len(list_image_files(dst, recursive=True)) if dst.exists() else 0
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'file_count': file_count,
                    'client': client, 'session': str(session),
                    'template': template
                })

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
                         '--mode', 'list-only', '--recursive']
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                file_count = len(list_image_files(dst, recursive=True)) if dst.exists() else 0
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'file_count': file_count, 'list_file': str(list_file)
                })

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
                processed_count = 0
                raw_count = 0
                landscape_count = 0
                portrait_count = 0
                square_count = 0
                if dst.exists():
                    for or_dir in ['landscape', 'portrait', 'square']:
                        p = dst / or_dir
                        if p.exists():
                            n = len(list_image_files(p, recursive=True))
                            if or_dir == 'landscape':
                                landscape_count = n
                            elif or_dir == 'portrait':
                                portrait_count = n
                            else:
                                square_count = n
                            processed_count += n
                    raw_dir = dst / 'raw_original'
                    if raw_dir.exists():
                        raw_count = len(list_image_files(raw_dir, recursive=True))
                skipped_count = 0
                skipped_list = []
                if skipped_log.exists():
                    with open(skipped_log, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if '|' in line:
                                skipped_count += 1
                                fp, reason = line.split('|', 1)
                                skipped_list.append((fp, reason))
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'skipped_log': str(skipped_log),
                    'processed_count': processed_count,
                    'raw_count': raw_count,
                    'landscape_count': landscape_count,
                    'portrait_count': portrait_count,
                    'square_count': square_count,
                    'skipped_count': skipped_count,
                    'skipped_files': skipped_list,
                    'watermark_text': watermark_text
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
                    client_arg = ['-c', client] if client else []
                    session_arg = ['-s', session] if session else []
                    result = runner.invoke(
                        pack_cmd,
                        [str(src), '-o', str(dst), '-n', pack_name,
                         '--split-by-orientation'] + base_dir_arg + client_arg + session_arg
                    )
                    if result.exit_code != 0:
                        raise RuntimeError(result.output)
                    click.echo(result.output)
                zip_files = []
                photo_count = 0
                thumb_count = 0
                checksum_path = None
                manifest_path = None
                if dst.exists():
                    for zf in sorted(dst.glob('*.zip')):
                        size_mb = zf.stat().st_size / (1024 * 1024)
                        is_thumbs = 'thumb' in zf.name.lower()
                        zip_files.append({
                            'name': zf.name,
                            'path': str(zf),
                            'size_bytes': zf.stat().st_size,
                            'size_mb': round(size_mb, 2),
                            'is_thumbs': is_thumbs
                        })
                    for cs in sorted(dst.glob('*_checksums.md5')):
                        checksum_path = str(cs)
                    for mf in sorted(dst.glob('*_manifest.json')):
                        manifest_path = str(mf)
                        try:
                            with open(mf, 'r', encoding='utf-8') as f:
                                import json
                                manifest_data = json.load(f)
                                photo_count = manifest_data.get('summary', {}).get('total_photos', 0)
                                thumb_count = manifest_data.get('summary', {}).get('total_thumbs', 0)
                        except Exception:
                            pass
                state = mark_step_completed(state, step, {
                    'src': str(src), 'dst': str(dst),
                    'zip_files': zip_files,
                    'file_count': len(zip_files),
                    'photo_count': photo_count,
                    'thumb_count': thumb_count,
                    'pack_name': pack_name,
                    'split_by_orientation': True,
                    'checksum_path': checksum_path,
                    'manifest_path': manifest_path
                })

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
                    step_summary = json.dumps(state.get('steps', {}), ensure_ascii=False)
                    from click.testing import CliRunner
                    runner = CliRunner()
                    cmd_args = [str(src), '-o', str(report_file),
                                '--group-by-date', '--group-by-camera',
                                '--step-summary', step_summary] + skipped_files_arg
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
            click.echo(f'\n流程中断! 修复问题后再次执行相同命令即可从该步骤继续。')
            click.echo(f'或使用 --from-step {step} 从该步骤重试，--reset 从头开始。')
            click.echo(f'查看状态: photo delivery status -o {output}')
            sys.exit(1)

    state['completed_at'] = datetime.now().isoformat()
    save_state(output, state)

    click.echo('\n' + '=' * 60)
    click.echo('全部完成!')
    click.echo('=' * 60)
    click.echo(f'工作目录: {output}')
    if subdirs['pack'].exists():
        click.echo(f'交付压缩包: {subdirs["pack"]}')
    if subdirs['report'].exists():
        report_file = subdirs['report'] / f'{client}_delivery_report.txt'
        if report_file.exists():
            click.echo(f'整理报告: {report_file}')
    click.echo(f'流程状态: {output}/.delivery_state.json')
    click.echo('查看状态: photo delivery status -o <工作目录>')
    click.echo('=' * 60)


@delivery_cmd.command(name='status')
@click.option('--output', '-o', default=None, help='工作/输出根目录')
@click.option('--use-project-config/--no-project-config', default=True,
              help='是否读取项目目录的 photo_project.json 获取默认 output')
@click.option('--json', 'as_json', is_flag=True, help='以 JSON 格式输出状态')
def delivery_status(output, use_project_config, as_json):
    """查看交付流程各步骤的执行状态

    显示每一步的状态（完成/失败/待执行/运行中），
    失败时显示错误信息和继续执行的建议。
    """
    proj_dir_arg = None if use_project_config else '__disabled__'
    if not output:
        resolved = resolve_preset(
            None,
            {'output': None},
            {'output': None},
            project_dir=proj_dir_arg
        )
        output = resolved.get('output')

    if not output:
        click.echo('错误: 请通过 --output 指定工作目录，或在项目配置中设置 output')
        return

    output = Path(output)
    state = load_state(output)

    if as_json:
        click.echo(json.dumps(state, ensure_ascii=False, indent=2))
        return

    click.echo('=' * 60)
    click.echo('交付流程状态')
    click.echo('=' * 60)
    click.echo(f'工作目录: {output}')
    if state.get('started_at'):
        click.echo(f'开始时间: {state["started_at"]}')
    if state.get('completed_at'):
        click.echo(f'完成时间: {state["completed_at"]}')
    click.echo('')

    failed_step = None
    pending_first = None

    for step in DELIVERY_STEPS:
        step_data = state.get('steps', {}).get(step)
        label = STEP_LABELS.get(step, step)
        s = None

        if not step_data:
            status = '待执行'
            icon = '[--]'
            if not pending_first:
                pending_first = step
        else:
            s = step_data.get('status', 'unknown')
            if s == 'completed':
                status = '已完成'
                icon = '[OK]'
            elif s == 'running':
                status = '运行中'
                icon = '[..]'
            elif s == 'failed':
                status = '失败'
                icon = '[FAIL]'
                failed_step = step
            else:
                status = s
                icon = '[??]'

        line = f'  {icon} {label}'
        click.echo(line)

        info = step_data.get('info', {}) if step_data else {}
        if step_data and s == 'completed':
            extras = []
            if info.get('file_count') is not None:
                extras.append(f'{info["file_count"]} 张')
            if info.get('processed_count') is not None:
                extras.append(f'加水印 {info["processed_count"]} 张')
            if info.get('raw_count'):
                extras.append(f'RAW {info["raw_count"]} 张')
            if info.get('zip_files'):
                extras.append(f'{len(info["zip_files"])} 个压缩包')
            if extras:
                click.echo(f'       {", ".join(extras)}')
            if info.get('dst'):
                click.echo(f'       输出: {info["dst"]}')

        if step_data and s == 'failed':
            if step_data.get('error'):
                click.echo(f'       错误: {step_data["error"]}')

    click.echo('')

    if is_delivery_complete(state):
        click.echo('[OK] 交付流程已全部完成')
        click.echo('     如需重跑某一步: photo delivery run -o <工作目录> --from-step <步骤名> <源目录> ...')
        click.echo('     如需从头开始: photo delivery run -o <工作目录> --reset <源目录> ...')
    elif failed_step:
        click.echo(f'[FAIL] 流程在第 {DELIVERY_STEPS.index(failed_step) + 1} 步 "{STEP_LABELS.get(failed_step, failed_step)}" 中断')
        click.echo(f'     修复问题后:')
        click.echo(f'       photo delivery run -o {output} --from-step {failed_step} <源目录>')
        click.echo(f'     或只重跑该步:')
        click.echo(f'       photo delivery run -o {output} --only-step {failed_step} <源目录>')
    elif pending_first:
        click.echo(f'[--] 下一步: 第 {DELIVERY_STEPS.index(pending_first) + 1} 步 "{STEP_LABELS.get(pending_first, pending_first)}"')
        click.echo(f'     继续执行: photo delivery run -o {output} <源目录>')

    click.echo('')
    click.echo(f'状态文件: {output}/.delivery_state.json')
    click.echo('=' * 60)
