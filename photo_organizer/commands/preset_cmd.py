import json
import click
from pathlib import Path

from photo_organizer.core.config import (
    load_presets, save_preset, delete_preset,
    list_presets, get_preset,
    load_project_config, save_project_config,
    DEFAULT_PROJECT_CONFIG
)


@click.group()
def preset_cmd():
    """管理预设配置 (preset)"""
    pass


@preset_cmd.command(name='list')
def preset_list():
    """列出所有预设"""
    presets = list_presets()
    if not presets:
        click.echo('没有保存的预设')
        return
    click.echo(f'共 {len(presets)} 个预设:')
    for name in sorted(presets):
        click.echo(f'  - {name}')


@preset_cmd.command(name='show')
@click.argument('name')
def preset_show(name):
    """显示预设详情"""
    preset = get_preset(name)
    if not preset:
        click.echo(f'预设 "{name}" 不存在')
        return
    click.echo(f'预设: {name}')
    click.echo(json.dumps(preset, ensure_ascii=False, indent=2))


@preset_cmd.command(name='save')
@click.argument('name')
@click.option('--client', help='客户名称')
@click.option('--session', help='场次编号')
@click.option('--template', help='命名模板')
@click.option('--watermark-text', 'watermark_text', help='水印文字')
@click.option('--output', '-o', help='输出目录')
@click.option('--base-dir', help='压缩包内基础目录')
@click.option('--pack-name', 'pack_name', help='打包名称')
@click.option('--group-by', 'group_by', help='导入分组方式')
@click.option('--force', '-f', is_flag=True, help='覆盖已存在的预设')
def preset_save(name, client, session, template, watermark_text,
                 output, base_dir, pack_name, group_by, force):
    """保存预设配置"""
    existing = get_preset(name)
    if existing and not force:
        click.echo(f'预设 "{name}" 已存在，使用 --force 覆盖')
        return

    config = {}
    if client:
        config['client'] = client
    if session:
        config['session'] = session
    if template:
        config['template'] = template
    if watermark_text:
        config['text'] = watermark_text
    if output:
        config['output'] = output
    if base_dir:
        config['base_dir'] = base_dir
    if pack_name:
        config['name'] = pack_name
    if group_by:
        config['group_by'] = group_by

    if not config:
        click.echo('没有提供任何配置项，使用 --help 查看可用选项')
        return

    save_preset(name, config)
    click.echo(f'预设 "{name}" 已保存')
    click.echo(json.dumps(config, ensure_ascii=False, indent=2))


@preset_cmd.command(name='delete')
@click.argument('name')
@click.option('--yes', '-y', is_flag=True, help='确认删除')
def preset_delete(name, yes):
    """删除预设"""
    preset = get_preset(name)
    if not preset:
        click.echo(f'预设 "{name}" 不存在')
        return

    if not yes:
        click.confirm(f'确定要删除预设 "{name}" 吗?', abort=True)

    if delete_preset(name):
        click.echo(f'预设 "{name}" 已删除')
    else:
        click.echo(f'删除预设 "{name}" 失败')


@preset_cmd.command(name='init-project')
@click.option('--preset', '-p', help='基于已有的 preset 初始化项目配置')
@click.option('--client', help='客户名称')
@click.option('--session', help='场次编号')
@click.option('--template', help='命名模板')
@click.option('--watermark-text', 'watermark_text', help='水印文字')
@click.option('--output', '-o', help='输出目录')
@click.option('--project-dir', default='.',
              help='项目目录 (默认: 当前目录)')
def preset_init_project(preset, client, session, template, watermark_text,
                         output, project_dir):
    """在当前项目目录生成 photo_project.json 配置文件"""
    config = {}

    if preset:
        preset_config = get_preset(preset)
        if preset_config:
            config.update(preset_config)
        else:
            click.echo(f'警告: 预设 "{preset}" 不存在')

    if client:
        config['client'] = client
    if session:
        config['session'] = session
    if template:
        config['template'] = template
    if watermark_text:
        config['text'] = watermark_text
    if output:
        config['output'] = output

    path = save_project_config(config, project_dir)
    click.echo(f'项目配置已保存到: {path}')
    if config:
        click.echo(json.dumps(config, ensure_ascii=False, indent=2))
    else:
        click.echo('(空配置，可手动编辑该文件)')
