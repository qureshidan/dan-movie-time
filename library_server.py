"""Movie Time catalogue and paired LAN playback service."""
import asyncio
import contextlib
import hashlib
import html
import ipaddress
import json
import logging
import secrets
import socket
import time
from pathlib import Path

from aiohttp import web
from telethon.errors import RPCError
from catalogue import parse_post, parse_episode, parse_split_series, telegram_target
from ranges import byte_range

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('movie-time')


def save_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def lan_addresses():
    addresses = set()
    with contextlib.suppress(OSError):
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = ipaddress.ip_address(item[4][0])
            if address.is_private and not address.is_loopback and not address.is_link_local:
                addresses.add(str(address))
    return sorted(addresses)


class Library:
    def __init__(self, client, private, channel='examplechannel'):
        self.client, self.private, self.channel = client, private, channel
        private.mkdir(exist_ok=True)
        self.cache = private / 'catalogue.json'
        self.movies = {}
        if self.cache.exists():
            try:
                self.movies = {str(m['id']): m for m in json.loads(self.cache.read_text(encoding='utf-8'))}
            except (ValueError, KeyError, TypeError):
                LOG.warning('Catalogue cache unreadable; rebuilding from Telegram.')
        self.status = {'running': False, 'scanned': 0, 'error': None, 'updated': None}
        self.sync_task = None
        self.images = private / 'posters'
        self.images.mkdir(exist_ok=True)
        self.image_slots = asyncio.Semaphore(3)
        self.stream_slots = asyncio.Semaphore(3)
        self.last_sync = 0
        sources_path = private / 'sources.json'
        self.episode_channels = json.loads(sources_path.read_text(encoding='utf-8')).get('episode_channels', []) if sources_path.exists() else []

    def start_sync(self):
        if self.sync_task and not self.sync_task.done():
            return
        if time.monotonic() - self.last_sync < 30:
            return
        self.last_sync = time.monotonic()
        self.status.update(running=True, scanned=0, error=None)
        self.sync_task = asyncio.create_task(self.sync())

    async def sync(self):
        found = {}
        newer_message = None
        try:
            async for message in self.client.iter_messages(self.channel):
                self.status['scanned'] += 1
                movie = parse_post(message)
                if not movie and message.photo and newer_message and newer_message.id == message.id + 1 and newer_message.buttons:
                    first_button = newer_message.buttons[0][0]
                    target = telegram_target(getattr(first_button, 'url', None))
                    if target and first_button.text.upper().startswith('EP'):
                        try:
                            movie = parse_split_series(message, newer_message)
                            if movie is None and not (message.raw_text or '').strip():
                                episode = await self.client.get_messages(target['peer'], ids=target['post'])
                                if episode:
                                    movie = parse_split_series(message, newer_message, episode)
                        except (RPCError, ValueError):
                            LOG.warning('Could not resolve an adjacent episode-button post.')
                newer_message = message
                if movie:
                    found[str(movie['id'])] = movie
                    self.movies[str(movie['id'])] = movie
                if self.status['scanned'] % 100 == 0:
                    await asyncio.sleep(0)
            for channel in self.episode_channels:
                async for message in self.client.iter_messages(channel['peer']):
                    self.status['scanned'] += 1
                    episode = parse_episode(message, channel['peer'], channel['title'])
                    if episode:
                        found[episode['id']] = episode
                        self.movies[episode['id']] = episode
            # A series poster points into an episode channel; expand it into
            # an ordered episode picker rather than playing only that one link.
            for series in list(found.values()):
                if series.get('kind') != 'series':
                    continue
                peers = {source['peer'] for source in series['sources']}
                episodes = sorted((e for e in found.values() if e.get('kind') == 'episode' and e['sources'][0]['peer'] in peers), key=lambda e: (e['season'], e['episode'], e['id']))
                if episodes:
                    series['sources'] = [dict(e['sources'][0], label=e['title']) for e in episodes]
                    series['episode_count'] = len(episodes)
                    for episode in episodes:
                        episode['series_id'] = series['id']
            self.movies = found
            save_json(self.cache, list(self.movies.values()))
            self.status['updated'] = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning('Channel sync failed: %s', type(exc).__name__)
            self.status['error'] = 'Channel refresh failed. Cached titles remain available. Try Refresh later.'
        finally:
            self.status['running'] = False

    async def close(self):
        if self.sync_task and not self.sync_task.done():
            self.sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.sync_task

    def movie(self, request):
        movie = self.movies.get(request.match_info['movie'])
        if not movie:
            raise web.HTTPNotFound(text='This title is no longer in the library. Refresh the library.')
        return movie

    async def poster(self, request):
        movie = self.movie(request)
        if movie.get('kind') == 'episode':
            # Do not require a separate poster post for directly uploaded episodes.
            title = html.escape(movie['series'])
            label = f"S{movie['season']:02d} E{movie['episode']:02d}"
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600"><rect width="400" height="600" fill="#171526"/><path d="M0 380L400 100V320L0 600Z" fill="#302347"/><text x="28" y="70" fill="#c3aeff" font-family="Arial" font-size="22">DAN SERIES</text><foreignObject x="28" y="190" width="344" height="210"><div xmlns="http://www.w3.org/1999/xhtml" style="color:white;font: bold 34px Arial;overflow-wrap:break-word">{title}</div></foreignObject><text x="28" y="525" fill="#eaee90" font-family="Arial" font-size="36">{label}</text></svg>'
            return web.Response(text=svg, content_type='image/svg+xml', headers={'Cache-Control': 'private, max-age=3600'})
        path = self.images / f"{movie['id']}.jpg"
        async with self.image_slots:
            if not path.exists():
                message = await self.client.get_messages(self.channel, ids=movie['id'])
                if not message or not message.photo:
                    raise web.HTTPNotFound(text='Poster unavailable')
                data = await self.client.download_media(message.photo, file=bytes)
                if not data:
                    raise web.HTTPNotFound()
                path.write_bytes(data)
        return web.FileResponse(path, headers={'Cache-Control': 'private, max-age=3600'})

    async def stream(self, request):
        movie = self.movie(request)
        try:
            source_index = int(request.query.get('source', '0'))
            if source_index < 0:
                raise ValueError()
            source = movie['sources'][source_index]
        except (ValueError, IndexError):
            raise web.HTTPBadRequest(text='Select an available version.')
        entity = await self.client.get_input_entity(source['peer'])
        message = await self.client.get_messages(entity, ids=source['post'])
        if not message or not message.document or not message.file or not message.file.size:
            raise web.HTTPNotFound(text='This link does not point to a video file, or the post was removed.')
        mime = message.file.mime_type or 'application/octet-stream'
        if not mime.startswith('video/') and not (message.file.name or '').lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.ts')):
            raise web.HTTPUnsupportedMediaType(text='The linked file is not a recognised video.')
        size = message.file.size
        try:
            start, end = byte_range(request.headers.get('Range'), size)
        except ValueError:
            return web.Response(status=416, headers={'Content-Range': f'bytes */{size}'})
        partial = 'Range' in request.headers
        headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(end - start + 1),
                   'Content-Type': mime, 'Cache-Control': 'no-store'}
        if partial:
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        response = web.StreamResponse(status=206 if partial else 200, headers=headers)
        if request.method == 'HEAD':
            await response.prepare(request)
            return response
        try:
            await asyncio.wait_for(self.stream_slots.acquire(), timeout=10)
        except asyncio.TimeoutError:
            raise web.HTTPServiceUnavailable(text='All playback slots are busy. Stop another player and retry.')
        iterator = None
        try:
            iterator = self.client.iter_download(message.media, offset=start, file_size=size)
            first = bytes(await iterator.__anext__())
            await response.prepare(request)
            remaining = end - start + 1
            chunk = first[:remaining]
            await response.write(chunk)
            remaining -= len(chunk)
            while remaining > 0:
                chunk = bytes(await iterator.__anext__())[:remaining]
                await response.write(chunk)
                remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            if response.prepared:
                if request.transport:
                    request.transport.close()
                LOG.warning('Playback interrupted; the player can retry.')
            else:
                raise
        finally:
            try:
                if iterator:
                    await iterator.close()
            finally:
                self.stream_slots.release()
        return response


def create_app(library, port=8765):
    auth_path = library.private / 'devices.json'
    if auth_path.exists():
        auth = json.loads(auth_path.read_text())
    else:
        auth = {'pin': str(secrets.randbelow(90000000) + 10000000), 'tokens': []}
        save_json(auth_path, auth)
    attempts = {}
    allowed_hosts = {'localhost', '127.0.0.1', *lan_addresses()}

    def local(request):
        return request.remote in ('127.0.0.1', '::1')

    def authorized(request):
        if local(request):
            return True
        token = request.cookies.get('movie_time', '')
        if request.headers.get('Authorization', '').startswith('Bearer '):
            token = request.headers['Authorization'][7:]
        return hashlib.sha256(token.encode()).hexdigest() in auth['tokens'] if token else False

    @web.middleware
    async def guard(request, handler):
        host = request.host.rsplit(':', 1)[0] if ':' in request.host else request.host
        if host not in allowed_hosts:
            raise web.HTTPForbidden(text='Use the laptop address shown in the launcher.')
        origin = request.headers.get('Origin')
        if origin and origin != f'http://{request.host}':
            raise web.HTTPForbidden(text='Cross-origin requests are not allowed.')
        public = request.path in ('/', '/app.js', '/style.css', '/api/status', '/api/pair')
        if not public and not authorized(request):
            raise web.HTTPUnauthorized(text='Pair this device using the code on your laptop.')
        try:
            response = await handler(request)
        except (ConnectionError, asyncio.TimeoutError):
            LOG.warning('Telegram connection unavailable; retry after reconnection.')
            response = web.json_response({'error': 'Telegram connection interrupted. Wait a moment and retry playback.'}, status=503, headers={'Retry-After': '30'})
        except (RPCError, ValueError) as exc:
            LOG.warning('Telegram request failed: %s', type(exc).__name__)
            response = web.json_response({'error': 'Telegram could not open this post. Check channel access and try again.'}, status=502)
        if not response.prepared:
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Cache-Control'] = response.headers.get('Cache-Control', 'no-store')
        return response

    async def index(request):
        return web.FileResponse(ROOT / 'index.html')

    async def asset(request):
        return web.FileResponse(ROOT / request.match_info['asset'])

    async def status(request):
        result = {'paired': authorized(request), 'local': local(request)}
        if result['paired']:
            result.update(library.status, count=len(library.movies))
        if local(request):
            result.update(pin=auth['pin'], addresses=[f'http://{a}:{port}' for a in lan_addresses()])
        return web.json_response(result)

    async def pair(request):
        now = time.monotonic()
        for peer in list(attempts):
            attempts[peer] = [t for t in attempts[peer] if now - t < 60]
            if not attempts[peer]:
                del attempts[peer]
        recent = attempts.setdefault(request.remote, [])
        if len(recent) >= 5 or sum(map(len, attempts.values())) >= 50:
            raise web.HTTPTooManyRequests(text='Wait a minute before trying another code.')
        recent.append(now)
        try:
            data = await request.json()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text='Enter the pairing code.')
        if not isinstance(data, dict) or not secrets.compare_digest(str(data.get('pin', '')), auth['pin']):
            raise web.HTTPUnauthorized(text='That pairing code is incorrect.')
        token = secrets.token_urlsafe(32)
        auth['tokens'] = (auth['tokens'] + [hashlib.sha256(token.encode()).hexdigest()])[-50:]
        save_json(auth_path, auth)
        response = web.json_response({'paired': True})
        response.set_cookie('movie_time', token, httponly=True, samesite='Strict', max_age=31536000)
        return response

    async def movies(request):
        items = []
        for movie in sorted(library.movies.values(), key=lambda m: (m.get('kind') != 'episode', str(m['id']).zfill(20)), reverse=True):
            item = {k: v for k, v in movie.items() if k != 'sources'}
            item['versions'] = [s['label'] for s in movie['sources']]
            items.append(item)
        return web.json_response({'movies': items})

    async def sync(request):
        library.start_sync()
        return web.json_response(library.status)

    async def apk(request):
        path = ROOT / 'dist' / 'Movie-Time-TV.apk'
        if not path.exists():
            raise web.HTTPNotFound(text='The APK has not been built yet.')
        return web.FileResponse(path, headers={'Content-Type': 'application/vnd.android.package-archive',
                                              'Content-Disposition': 'attachment; filename="Movie-Time-TV.apk"'})

    app = web.Application(middlewares=[guard], client_max_size=4096)
    app.add_routes([web.get('/', index), web.get('/{asset:app.js|style.css}', asset),
                    web.get('/api/status', status), web.post('/api/pair', pair),
                    web.get('/api/movies', movies), web.post('/api/sync', sync),
                    web.get('/poster/{movie}', library.poster), web.get('/stream/{movie}', library.stream),
                    web.get('/Movie-Time-TV.apk', apk)])
    app['library'] = library
    app['pairing_pin'] = auth['pin']
    return app
