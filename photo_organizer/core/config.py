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
    """加载所有 preset"""
    ensure_config_dir()
    if DEFAULT_PRESETS_FILE.exists():
        with open(DEFAULT_PRESETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_presets(presets):
    """保存所有 preset"""
    ensure_config_dir()
    with open(DEFAULT_PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def get_preset(name):
    """获取单个 preset"""
    presets = load_presets()
    return presets.get(name)


def save_preset(name, config):
    """保存单个 preset"""
    presets = load_presets()
    presets[name] = config
    save_presets(presets)


def delete_preset(name):
    """删除 preset"""
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)
        return True
    return False


def list_presets():
    """列出所有 preset 名称"""
    return list(load_presets().keys())


def load_project_config(project_dir=None):
    """加载项目级配置文件"""
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    config_path = project_dir / DEFAULT_PROJECT_CONFIG
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_project_config(config, project_dir=None):
    """保存项目级配置文件"""
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    config_path = project_dir / DEFAULT_PROJECT_CONFIG
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config_path


def apply_preset_to_options(preset_name, **kwargs):
    """将 preset 中的配置应用到命令选项，命令行传入的参数优先级更高"""
    preset = get_preset(preset_name)
    if not preset:
        return kwargs

    result = dict(kwargs)
    for key, value in preset.items():
        if key not in result or result[key] is None:
            result[key] = value
    return result
