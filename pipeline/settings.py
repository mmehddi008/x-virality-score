"""Shared private profile overrides; compatible with the host Python runtime."""
import json
import os
import re
from pathlib import Path


def effective_config(slug, config):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', slug):
        raise ValueError('Invalid profile')
    cfg = dict(config)
    root = Path(os.environ.get('XVS_SETTINGS_ROOT', Path(__file__).resolve().parents[1]/'settings'))
    path = root/(slug+'.json')
    saved = {}
    if path.is_symlink():
        raise ValueError('Settings must not be a symlink')
    if path.exists():
        if path.stat().st_size > 32768:
            raise ValueError('Settings too large')
        saved = json.loads(path.read_text())
        if saved.get('profile_id') != slug:
            raise ValueError('Settings profile mismatch')
    model = saved.get('model', os.environ.get('INSIGHT_AI_MODEL') or 'sonnet')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}', model):
        raise ValueError('Invalid model ID')
    cfg['ai_model'] = model
    for key, default, maximum in [('draft_count',4,8),('research_days',7,7)]:
        value = saved.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('Invalid research setting')
        cfg[key] = value
    if saved.get('sources') is not None:
        sources = saved['sources']
        if not isinstance(sources,list) or not 1 <= len(sources) <= 20:
            raise ValueError('Use one to twenty sources')
        handles = set()
        for source in sources:
            handle = source.get('handle','')
            notes = source.get('notes','')
            if not isinstance(handle,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle) or handle.lower() in handles:
                raise ValueError('Invalid or duplicate source')
            if not isinstance(notes,str) or len(notes)>200 or re.search(r'[\u0600-\u06ff]',notes):
                raise ValueError('Source notes must be English')
            handles.add(handle.lower())
        cfg['accounts'] = sources
    return cfg


def shared_connection():
    """Central Trackpanel connection; legacy environment only before migration."""
    root = Path(os.environ.get('XVS_SETTINGS_ROOT', Path(__file__).resolve().parents[1]/'settings'))
    path = root/'shared-ai.json'
    if path.is_symlink():
        raise ValueError('Invalid shared AI settings')
    if path.exists():
        if path.stat().st_size > 16384:
            raise ValueError('Invalid shared AI settings')
        saved = json.loads(path.read_text())
        base, key = saved['endpoint'], saved['api_key']
        from urllib.parse import urlsplit
        u = urlsplit(base)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment or not isinstance(key,str) or not key or '\n' in key or '\r' in key:
            raise ValueError('Invalid shared AI connection')
        return base.rstrip('/'), key, saved.get('updated_at','')
    return os.environ['INSIGHT_AI_URL'].rstrip('/'), os.environ['INSIGHT_AI_KEY'], ''
