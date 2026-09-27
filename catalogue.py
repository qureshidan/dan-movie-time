"""Parse channel posts without executing content or following arbitrary URLs."""
import re
from urllib.parse import urlsplit


def telegram_target(url):
    try:
        parsed = urlsplit(url or '')
        if parsed.scheme != 'https' or parsed.netloc.lower() not in ('t.me', 'telegram.me'):
            return None
        parts = parsed.path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'c' and parts[1].isdigit() and parts[2].isdigit():
            peer, post = int('-100' + parts[1]), int(parts[2])
        elif len(parts) == 2 and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}', parts[0]) and parts[1].isdigit():
            peer, post = parts[0], int(parts[1])
        else:
            return None
        return {'peer': peer, 'post': post} if post > 0 else None
    except (ValueError, TypeError):
        return None


def parse_post(message):
    caption = message.raw_text or ''
    def field(label):
        match = re.search(r'(?:^|\n)[^\w\n]*' + label + r'\s*:\s*([^\n]+)', caption, re.I)
        return match.group(1).strip() if match else ''
    series_title = field('Series Name')
    title = field('Movie Name') or series_title
    if not title or not message.photo:
        return None
    sources, seen = [], set()
    for row in message.buttons or []:
        for button in row:
            target = telegram_target(getattr(button, 'url', None))
            if not target:
                continue
            key = (target['peer'], target['post'])
            if key not in seen:
                seen.add(key)
                sources.append(dict(target, label=getattr(button, 'text', '') or 'Play'))
    if not sources:
        return None
    synopsis = re.split(r'(?:Movie|Series)-SYNOPSIS/PLOT\s*:', caption, flags=re.I)
    return {'id': message.id, 'title': title, 'kind': 'series' if series_title else 'movie', 'year': field('Release Year'),
            'genre': field('Genre'), 'language': field('Language'), 'quality': field('Quality'),
            'rating': field('IMDb Rating'), 'subtitle': field('Subtitle'), 'size': field('Size'),
            'synopsis': synopsis[-1].strip() if len(synopsis) > 1 else '',
            'caption': caption, 'sources': sources}


def parse_episode(message, peer, series):
    file = getattr(message, 'file', None)
    if not getattr(message, 'document', None) or not file or not file.size:
        return None
    name = file.name or ''
    if not (file.mime_type or '').startswith('video/') and not name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.ts')):
        return None
    caption = message.raw_text or ''
    title = caption.splitlines()[0].strip() if caption.strip() else name or f'{series} — Episode {message.id}'
    match = re.search(r'\bS(\d+)\s*E(\d+)\b', title, re.I)
    return {'id': f'episode_{abs(peer)}_{message.id}', 'kind': 'episode', 'series': series,
            'season': int(match[1]) if match else 0, 'episode': int(match[2]) if match else message.id,
            'title': title, 'year': '', 'genre': series, 'language': '', 'quality': '', 'rating': '',
            'subtitle': '', 'size': f'{file.size / (1024 ** 2):.0f} MB', 'synopsis': caption,
            'caption': caption, 'sources': [{'peer': peer, 'post': message.id, 'label': 'Play episode'}]}


def parse_split_series(poster, button_post, first_episode=None):
    """Recognise an adjacent image + EP-button post, with title from its video."""
    from types import SimpleNamespace
    if not poster.photo or button_post.id != poster.id + 1:
        return None
    buttons = [b for row in button_post.buttons or [] for b in row]
    if not buttons or any(not re.fullmatch(r'EP(?:ISODE)?\s*\d+', b.text.strip(), re.I) or not telegram_target(getattr(b, 'url', None)) for b in buttons):
        return None
    ordered = sorted(buttons, key=lambda b: int(re.search(r'\d+', b.text)[0]))
    if (poster.raw_text or '').strip():
        result = parse_post(SimpleNamespace(id=poster.id, photo=poster.photo,
                            raw_text=poster.raw_text, buttons=[ordered]))
        if not result or result['kind'] != 'series':
            return None
        result['episode_count'] = len(result['sources'])
        return result
    if first_episode is None:
        return None
    caption = (first_episode.raw_text or '').strip()
    match = re.match(r'(.+?)\s+S\d+\s*E\d+\b', caption, re.I)
    if not match or not getattr(first_episode, 'document', None):
        return None
    title = re.sub(r'\s+Unknown Year$', '', match[1], flags=re.I).strip()
    ordered = sorted(buttons, key=lambda b: int(re.search(r'\d+', b.text)[0]))
    result = parse_post(SimpleNamespace(id=poster.id, photo=poster.photo,
                        raw_text='Series Name: ' + title, buttons=[ordered]))
    if result:
        result['episode_count'] = len(result['sources'])
    return result
