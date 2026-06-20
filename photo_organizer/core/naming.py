import re
from datetime import datetime
from pathlib import Path


DEFAULT_TEMPLATE = '{client}_{session}_{seq:04d}'


def parse_template(template, **kwargs):
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"命名模板缺少必要参数: {e}")


def extract_sequence(filename):
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return None


def generate_filename(template, client, session, seq, ext, **kwargs):
    name = parse_template(
        template,
        client=client,
        session=session,
        seq=seq,
        **kwargs
    )
    return f"{name}{ext}"


def parse_date_folder(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str, '%Y%m%d')
        except ValueError:
            return None
