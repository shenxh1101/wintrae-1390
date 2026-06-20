import click
import os
import json
from pathlib import Path
from datetime import datetime

from photo_organizer.core.file_utils import get_file_hash, ensure_directory, list_image_files
from photo_organizer.core.config import resolve_preset


def parse_checksum_file(checksum_path):
    """解析 MD5 校验文件，返回 {relative_path: md5} 字典"""
    checksums = {}
    checksum_path = Path(checksum_path)
    if not checksum_path.exists():
        return checksums

    with open(checksum_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                file_hash, rel_path = parts
                checksums[rel_path.strip()] = file_hash.strip()

    return checksums


def find_checksum_file(directory):
    """在目录中查找校验文件（优先排除 photos_checksums 和 manifest）"""
    directory = Path(directory)
    if not directory.exists():
        return None

    candidates = sorted(directory.glob('*_checksums.md5'))
    candidates = [c for c in candidates if 'photos' not in c.name.lower()]

    if not candidates:
        candidates = sorted(directory.glob('checksums.md5'))

    return candidates[0] if candidates else None


def scan_extra_files(base_dir, expected_files, include_extensions=None):
    """扫描目录中多余的文件（存在但不在校验清单中）"""
    base_dir = Path(base_dir)
    expected_set = set(expected_files)
    extra_files = []

    for root, dirs, files in os.walk(base_dir):
        root_path = Path(root)
        for file in files:
            file_path = root_path / file
            rel_path = file_path.relative_to(base_dir)
            rel_path_str = str(rel_path)

            if rel_path_str.endswith('_checksums.md5'):
                continue
            if rel_path_str.endswith('_manifest.json'):
                continue
            if rel_path_str.endswith('_manifest.txt'):
                continue
            if rel_path_str.endswith('_verify_report.txt'):
                continue

            if include_extensions:
                if file_path.suffix.lower() not in include_extensions:
                    continue

            if rel_path_str not in expected_set:
                extra_files.append(rel_path_str)

    return sorted(extra_files)


def verify_files(checksums, base_dir):
    """根据校验字典验证文件

    Returns:
        (ok_count, failed_count, missing_count, errors_dict, ok_files)
        errors_dict: {'mismatch': [...], 'missing': [...], 'error': [...]}
    """
    base_dir = Path(base_dir)
    ok = 0
    failed = 0
    missing = 0
    errors = {'mismatch': [], 'missing': [], 'error': []}
    ok_files = []

    for rel_path, expected_hash in checksums.items():
        file_path = base_dir / rel_path
        if not file_path.exists():
            missing += 1
            errors['missing'].append((rel_path, None))
            continue

        try:
            actual_hash = get_file_hash(file_path)
            if actual_hash == expected_hash:
                ok += 1
                ok_files.append((rel_path, actual_hash))
            else:
                failed += 1
                errors['mismatch'].append((rel_path, (expected_hash, actual_hash)))
        except Exception as e:
            failed += 1
            errors['error'].append((rel_path, str(e)))

    return ok, failed, missing, errors, ok_files


def load_manifest(directory):
    """加载目录中的 manifest 文件"""
    directory = Path(directory)
    candidates = sorted(directory.glob('*_manifest.json'))
    if not candidates:
        return None
    try:
        with open(candidates[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


@click.command()
@click.argument('check_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--checksum-file', '-c', default=None,
              help='校验文件路径 (默认在 CHECK_DIR 中自动查找 *_checksums.md5)')
@click.option('--report', 'output', default=None,
              help='验证报告输出文件路径 (默认: {name}_verify_report.txt)')
@click.option('--check-extra/--no-check-extra', default=True,
              help='是否检查多余文件 (默认: 是)')
@click.option('--verbose', '-v', is_flag=True,
              help='显示详细信息 (包括校验通过的文件)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
def verify_cmd(check_dir, checksum_file, output, check_extra, verbose, preset):
    """验证压缩包和照片的完整性

    根据统一 MD5 校验文件检查文件是否被改动、丢失或多余。
    直接指向交付目录即可，无需额外参数。

    CHECK_DIR: 交付目录（包含 *_checksums.md5 和待验证文件）
    """
    check_dir = Path(check_dir)

    if not checksum_file:
        checksum_file = find_checksum_file(check_dir)
        if not checksum_file:
            click.echo(f'错误: 在 {check_dir} 中未找到校验文件 (*_checksums.md5)')
            click.echo('请使用 --checksum-file 指定，或先运行 pack / delivery 命令生成校验文件')
            return

    checksum_file = Path(checksum_file)
    if not checksum_file.exists():
        click.echo(f'错误: 校验文件不存在: {checksum_file}')
        return

    manifest = load_manifest(check_dir)

    click.echo('=' * 60)
    click.echo('照片交付完整性校验')
    click.echo('=' * 60)
    if manifest:
        click.echo(f'客户: {manifest.get("client", "(未设置)")} | 场次: {manifest.get("session", "(未设置)")}')
    click.echo(f'交付目录: {check_dir}')
    click.echo(f'校验文件: {checksum_file.name}')
    click.echo(f'校验时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    click.echo('')

    checksums = parse_checksum_file(checksum_file)
    if not checksums:
        click.echo('校验文件为空或格式无效')
        return

    click.echo(f'待校验文件数: {len(checksums)}')
    click.echo('')

    base = check_dir
    ok, failed, missing, errors, ok_files = verify_files(checksums, base)

    extra_files = []
    extra_count = 0
    if check_extra:
        extra_files = scan_extra_files(base, checksums.keys())
        extra_count = len(extra_files)

    click.echo('=' * 50)
    click.echo('校验结果汇总')
    click.echo('=' * 50)
    click.echo(f'  [OK] 通过: {ok}')
    click.echo(f'  [FAIL] 被改动: {failed}')
    click.echo(f'  [MISS] 缺失: {missing}')
    if check_extra:
        click.echo(f'  [EXTRA] 多余文件: {extra_count}')
    click.echo(f'  [TOTAL] 总计: {len(checksums)}')
    click.echo('')

    has_issues = failed > 0 or missing > 0 or extra_count > 0

    if missing > 0:
        click.echo('【缺失文件】')
        click.echo('-' * 50)
        for rel_path, _ in errors['missing']:
            click.echo(f'  [MISSING]  {rel_path}')
        click.echo('')

    if failed > 0:
        if errors['mismatch']:
            click.echo('【被改动文件】')
            click.echo('-' * 50)
            for rel_path, (expected, actual) in errors['mismatch']:
                click.echo(f'  [MISMATCH] {rel_path}')
                click.echo(f'             期望: {expected}')
                click.echo(f'             实际: {actual}')
            click.echo('')
        if errors['error']:
            click.echo('【读取错误】')
            click.echo('-' * 50)
            for rel_path, err_msg in errors['error']:
                click.echo(f'  [ERROR]    {rel_path}: {err_msg}')
            click.echo('')

    if extra_count > 0:
        click.echo('【多余文件】（不在交付清单中）')
        click.echo('-' * 50)
        for rel_path in extra_files:
            file_path = base / rel_path
            try:
                size_kb = file_path.stat().st_size / 1024
                click.echo(f'  [EXTRA]    {rel_path}  ({size_kb:.1f} KB)')
            except Exception:
                click.echo(f'  [EXTRA]    {rel_path}')
        click.echo('')

    if verbose and ok_files:
        click.echo('【校验通过的文件】')
        click.echo('-' * 50)
        for rel_path, file_hash in ok_files:
            click.echo(f'  [OK]       {rel_path}  {file_hash}')
        click.echo('')

    report_path = None
    if output or has_issues:
        if not output:
            name = checksum_file.stem.replace('_checksums', '')
            output = check_dir / f'{name}_verify_report.txt'
        output = Path(output)
        ensure_directory(output.parent)

        with open(output, 'w', encoding='utf-8') as f:
            f.write('照片交付完整性校验报告\n')
            f.write('=' * 60 + '\n')
            f.write(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            if manifest:
                f.write(f'客户: {manifest.get("client", "(未设置)")}\n')
                f.write(f'场次: {manifest.get("session", "(未设置)")}\n')
            f.write(f'交付目录: {check_dir}\n')
            f.write(f'校验文件: {checksum_file.name}\n')
            f.write('\n')
            f.write('【校验结果汇总】\n')
            f.write(f'  通过: {ok}\n')
            f.write(f'  被改动: {failed}\n')
            f.write(f'  缺失: {missing}\n')
            if check_extra:
                f.write(f'  多余文件: {extra_count}\n')
            f.write(f'  总计校验: {len(checksums)}\n')
            f.write('\n')

            if missing > 0:
                f.write('【缺失文件】\n')
                for rel_path, _ in errors['missing']:
                    f.write(f'  [MISSING]  {rel_path}\n')
                f.write('\n')

            if failed > 0:
                if errors['mismatch']:
                    f.write('【被改动文件】\n')
                    for rel_path, (expected, actual) in errors['mismatch']:
                        f.write(f'  [MISMATCH] {rel_path}  expected={expected} actual={actual}\n')
                if errors['error']:
                    f.write('【读取错误】\n')
                    for rel_path, err_msg in errors['error']:
                        f.write(f'  [ERROR]    {rel_path}: {err_msg}\n')
                f.write('\n')

            if extra_count > 0:
                f.write('【多余文件】\n')
                for rel_path in extra_files:
                    file_path = base / rel_path
                    try:
                        size_kb = file_path.stat().st_size / 1024
                        f.write(f'  [EXTRA]    {rel_path}  ({size_kb:.1f} KB)\n')
                    except Exception:
                        f.write(f'  [EXTRA]    {rel_path}\n')
                f.write('\n')

            if verbose and ok_files:
                f.write('【校验通过的文件】\n')
                for rel_path, file_hash in ok_files:
                    f.write(f'  [OK]       {rel_path}  {file_hash}\n')

            f.write('\n')
            f.write('=' * 60 + '\n')
            if has_issues:
                f.write('结论: 校验未通过，存在问题需要处理\n')
            else:
                f.write('结论: 校验通过，所有文件完整\n')

        report_path = output
        click.echo(f'校验报告已保存到: {report_path}')

    if has_issues:
        click.echo('[FAIL] 校验未通过! 存在问题需要处理')
        click.echo(f'       详细报告: {report_path if report_path else "(未生成)"}')
        return
    else:
        click.echo('[OK] 校验通过，所有文件完整。')
