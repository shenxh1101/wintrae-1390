import click
import os
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


def verify_files(checksums, base_dir):
    """根据校验字典验证文件

    Returns:
        (ok_count, failed_count, missing_count, errors_list)
    """
    base_dir = Path(base_dir)
    ok = 0
    failed = 0
    missing = 0
    errors = []

    for rel_path, expected_hash in checksums.items():
        file_path = base_dir / rel_path
        if not file_path.exists():
            missing += 1
            errors.append(('missing', rel_path, None))
            continue

        try:
            actual_hash = get_file_hash(file_path)
            if actual_hash == expected_hash:
                ok += 1
            else:
                failed += 1
                errors.append(('mismatch', rel_path, (expected_hash, actual_hash)))
        except Exception as e:
            failed += 1
            errors.append(('error', rel_path, str(e)))

    return ok, failed, missing, errors


@click.command()
@click.argument('check_dir', type=click.Path(exists=True, file_okay=True, dir_okay=True))
@click.option('--checksum-file', '-c', default=None,
              help='校验文件路径 (默认在 CHECK_DIR 中查找 *_checksums.md5)')
@click.option('--checksum-photos/--no-checksum-photos', default=False,
              help='同时校验源照片 (需要 *_photos_checksums.md5)')
@click.option('--photo-dir', default=None,
              help='照片所在目录 (默认使用校验文件所在目录)')
@click.option('--report', 'output', default=None,
              help='验证报告输出文件路径')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息 (包括校验通过的文件)')
@click.option('--preset', '-p', default=None, help='使用预设配置名')
def verify_cmd(check_dir, checksum_file, checksum_photos, photo_dir, output, verbose, preset):
    """验证压缩包和照片的完整性

    根据 MD5 校验文件检查文件是否被改动或丢失。

    CHECK_DIR: 包含校验文件和待验证文件的目录
    """
    # verify 的 --report 是报告文件，和项目配置中的 output（工作目录）不同
    # 因此不从项目配置解析 output，避免误读为工作目录
    check_dir = Path(check_dir)

    if not checksum_file:
        candidates = sorted(check_dir.glob('*_checksums.md5'))
        if checksum_photos:
            candidates = [c for c in candidates if 'photos' not in c.name]
        if candidates:
            checksum_file = candidates[0]
        else:
            click.echo(f'错误: 在 {check_dir} 中未找到校验文件 (*_checksums.md5)')
            click.echo('请使用 --checksum-file 指定，或先运行 pack 命令生成校验文件')
            return

    checksum_file = Path(checksum_file)
    if not checksum_file.exists():
        click.echo(f'错误: 校验文件不存在: {checksum_file}')
        return

    click.echo(f'校验文件: {checksum_file}')
    checksums = parse_checksum_file(checksum_file)
    if not checksums:
        click.echo('校验文件为空或格式无效')
        return

    click.echo(f'待校验文件数: {len(checksums)}')

    base = photo_dir if photo_dir else checksum_file.parent
    ok, failed, missing, errors = verify_files(checksums, base)

    click.echo('')
    click.echo('=' * 50)
    click.echo('校验结果')
    click.echo('=' * 50)
    click.echo(f'  通过: {ok}')
    click.echo(f'  校验失败: {failed}')
    click.echo(f'  缺失文件: {missing}')
    click.echo(f'  总计: {len(checksums)}')
    click.echo('')

    if errors:
        click.echo('问题详情:')
        for err_type, rel_path, extra in errors:
            if err_type == 'missing':
                click.echo(f'  [MISSING]  {rel_path}')
            elif err_type == 'mismatch':
                expected, actual = extra
                click.echo(f'  [MISMATCH] {rel_path}')
                click.echo(f'             期望: {expected}')
                click.echo(f'             实际: {actual}')
            elif err_type == 'error':
                click.echo(f'  [ERROR]    {rel_path}: {extra}')
        click.echo('')

    if verbose:
        verified_rel_paths = set()
        for rel_path in sorted(checksums.keys()):
            file_path = Path(base) / rel_path
            if file_path.exists():
                try:
                    actual_hash = get_file_hash(file_path)
                    if actual_hash == checksums[rel_path]:
                        click.echo(f'  [OK] {rel_path}  {actual_hash}')
                        verified_rel_paths.add(rel_path)
                except Exception:
                    pass

    extra_ok = extra_failed = extra_missing = 0
    extra_errors = []
    if checksum_photos:
        photo_checksum_candidates = sorted(check_dir.glob('*_photos_checksums.md5'))
        if photo_checksum_candidates:
            photo_checksum = photo_checksum_candidates[0]
            click.echo(f'\n照片校验文件: {photo_checksum}')
            photo_checksums = parse_checksum_file(photo_checksum)
            if photo_checksums:
                click.echo(f'待校验照片数: {len(photo_checksums)}')
                photo_base = photo_dir if photo_dir else check_dir
                extra_ok, extra_failed, extra_missing, extra_errors = verify_files(photo_checksums, photo_base)
                click.echo(f'  照片通过: {extra_ok}, 失败: {extra_failed}, 缺失: {extra_missing}')
                if extra_errors:
                    for err_type, rel_path, extra in extra_errors:
                        if err_type == 'missing':
                            click.echo(f'  [MISSING]  {rel_path}')
                        elif err_type == 'mismatch':
                            click.echo(f'  [MISMATCH] {rel_path}')

    total_ok = ok + extra_ok
    total_fail = failed + extra_failed
    total_missing = missing + extra_missing

    if output:
        ensure_directory(Path(output).parent)
        with open(output, 'w', encoding='utf-8') as f:
            f.write('照片交付校验报告\n')
            f.write('=' * 50 + '\n')
            f.write(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'校验文件: {checksum_file}\n')
            f.write(f'校验目录: {base}\n')
            f.write(f'\n结果:\n')
            f.write(f'  通过: {total_ok}\n')
            f.write(f'  校验失败: {total_fail}\n')
            f.write(f'  缺失文件: {total_missing}\n')
            all_errors = errors + extra_errors
            if all_errors:
                f.write(f'\n问题详情:\n')
                for err_type, rel_path, extra in all_errors:
                    if err_type == 'missing':
                        f.write(f'  [MISSING]  {rel_path}\n')
                    elif err_type == 'mismatch':
                        expected, actual = extra
                        f.write(f'  [MISMATCH] {rel_path}  expected={expected} actual={actual}\n')
                    elif err_type == 'error':
                        f.write(f'  [ERROR]    {rel_path}: {extra}\n')
        click.echo(f'校验报告已保存到: {output}')

    if total_fail > 0 or total_missing > 0:
        click.echo('[FAIL] 校验未通过!')
        return
    else:
        click.echo('[OK] 校验通过，所有文件完整。')
