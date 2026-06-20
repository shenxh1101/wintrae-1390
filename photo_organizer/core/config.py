import json
import os
from pathlib import Path


DEFAULT_CONFIG_DIR = Path.home() / '.photo_organizer'
DEFAULT_PRESETS_FILE = DEFAULT_CONFIG_DIR / 'presets.json'
DEFAULT_PROJECT_CONFIG = 'photo_project.json'


def get_default_config_dir():
    return DEFAULT_CONFIG_DIR


def ensure_config_dir():
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR


def load_presets():
    ensure_config_dir()
    if DEFAULT_PRESETS_FILE.exists():
        with open(DEFAULT_PRESETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_presets(presets):
    ensure_config_dir()
    with open(DEFAULT_PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def get_preset(name):
    presets = load_presets()
    return presets.get(name)


def save_preset(name, config):
    presets = load_presets()
    presets[name] = config
    save_presets(presets)


def delete_preset(name):
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)
        return True
    return False


def list_presets():
    return list(load_presets().keys())


def load_project_config(project_dir=None):
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    config_path = project_dir / DEFAULT_PROJECT_CONFIG
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_project_config(config, project_dir=None):
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    config_path = project_dir / DEFAULT_PROJECT_CONFIG
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config_path


def resolve_preset(preset_name, cli_kwargs, internal_defaults=None):
    """按优先级解析配置: CLI 显式传值 > preset > 内部默认值

    cli_kwargs 中值为 None 的参数表示用户未显式传入，
    会被 preset 中对应的值覆盖；preset 中也没有的再用 internal_defaults。

    Args:
        preset_name: preset 名称，为 None/空则跳过
        cli_kwargs: 命令行传入的参数字典，未设置的应为 None
        internal_defaults: 内部默认值字典

    Returns:
        解析后的参数字典
    """
    result = dict(cli_kwargs)
    preset_cfg = get_preset(preset_name) if preset_name else {}
    defaults = internal_defaults or {}

    for key, value in result.items():
        if value is None:
            if key in preset_cfg:
                result[key] = preset_cfg[key]
            elif key in defaults:
                result[key] = defaults[key]

    return result
