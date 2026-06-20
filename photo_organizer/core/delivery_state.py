import json
from pathlib import Path
from datetime import datetime


DELIVERY_STEPS = ['import', 'rename', 'select', 'watermark', 'pack', 'report']
STATE_FILENAME = '.delivery_state.json'


def get_state_path(output_dir):
    return Path(output_dir) / STATE_FILENAME


def load_state(output_dir):
    state_path = get_state_path(output_dir)
    if state_path.exists():
        with open(state_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'steps': {},
        'current_step': None,
        'started_at': None,
        'completed_at': None,
        'output_dir': str(output_dir)
    }


def save_state(output_dir, state):
    state_path = get_state_path(output_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_step_started(state, step_name):
    state['steps'][step_name] = {
        'status': 'running',
        'started_at': datetime.now().isoformat(),
        'completed_at': None
    }
    state['current_step'] = step_name
    return state


def mark_step_completed(state, step_name, extra_info=None):
    if step_name in state['steps']:
        state['steps'][step_name]['status'] = 'completed'
        state['steps'][step_name]['completed_at'] = datetime.now().isoformat()
        if extra_info:
            state['steps'][step_name]['info'] = extra_info
    state['current_step'] = None
    return state


def mark_step_failed(state, step_name, error_msg):
    if step_name in state['steps']:
        state['steps'][step_name]['status'] = 'failed'
        state['steps'][step_name]['error'] = str(error_msg)
        state['steps'][step_name]['failed_at'] = datetime.now().isoformat()
    state['current_step'] = None
    return state


def is_step_completed(state, step_name):
    return step_name in state['steps'] and state['steps'][step_name].get('status') == 'completed'


def get_completed_steps(state):
    return [name for name in DELIVERY_STEPS if is_step_completed(state, name)]


def get_pending_steps(state, selected_steps=None, start_from=None):
    """获取待执行步骤列表

    - 无 start_from 时: 只返回尚未完成的步骤
    - 有 start_from 时: 从该步骤开始返回（含已完成步骤，用于强制重跑）
    """
    steps = selected_steps if selected_steps else DELIVERY_STEPS

    if start_from and start_from in steps:
        return steps[steps.index(start_from):]

    return [s for s in steps if not is_step_completed(state, s)]


def is_delivery_complete(state, selected_steps=None):
    """检查交付流程是否全部完成"""
    steps = selected_steps if selected_steps else DELIVERY_STEPS
    return all(is_step_completed(state, s) for s in steps)


def clear_state(output_dir):
    state_path = get_state_path(output_dir)
    if state_path.exists():
        state_path.unlink()
