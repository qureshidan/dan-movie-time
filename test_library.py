import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch, PropertyMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from catalogue import parse_post, telegram_target, parse_episode, parse_split_series
from library_server import Library, create_app


def post(id=3135):
    return NS(id=id, raw_text='Movie Name: Test movie\nRelease Year: 2026\nLanguage: Hindi\nGenre: Action, Comedy\nMovie-SYNOPSIS/PLOT:\nA test story.', photo=True,
              buttons=[[NS(text='Hindi', url='https://t.me/c/1234567890/4042'),
                        NS(text='English', url='https://t.me/examplechannel/123')]])


class ParserTests(unittest.TestCase):
    def test_direct_episode_and_unique_channels(self):
        m=NS(id=24,raw_text='Bigg Boss S20 E20',document=True,file=NS(name=None,mime_type='video/mp4',size=1000))
        episode=parse_episode(m,-100111,'Bigg Boss')
        self.assertEqual((episode['season'],episode['episode']),(20,20))
        self.assertNotEqual(episode['id'],parse_episode(m,-100222,'Other')['id'])
        self.assertEqual(episode['sources'][0]['post'],24)
        m.document=None
        self.assertIsNone(parse_episode(m,-100111,'Bigg Boss'))

    def test_split_series_requires_adjacent_episode_buttons(self):
        poster=NS(id=100,photo=True,raw_text='')
        button_post=NS(id=101,buttons=[[NS(text='EP2',url='https://t.me/c/12345/22'),NS(text='EP1',url='https://t.me/c/12345/21')]])
        episode=NS(raw_text='Example Show Unknown Year S01 E01',document=True)
        result=parse_split_series(poster,button_post,episode)
        self.assertEqual(result['title'],'Example Show')
        self.assertEqual(result['episode_count'],2)
        self.assertEqual([x['post'] for x in result['sources']],[21,22])
        button_post.id=102
        self.assertIsNone(parse_split_series(poster,button_post,episode))
        button_post.id=101;button_post.buttons[0][0].text='Visit channel'
        self.assertIsNone(parse_split_series(poster,button_post,episode))

    def test_captioned_split_series_preserves_metadata(self):
        poster=NS(id=100,photo=True,raw_text='Series Name: Example Show\nRelease Year: 2026\nLanguage: Hindi\nSeries-SYNOPSIS/PLOT:\nStory here.')
        buttons=NS(id=101,buttons=[[NS(text='EP2',url='https://t.me/c/12345/22'),NS(text='EP1',url='https://t.me/c/12345/21')]])
        result=parse_split_series(poster,buttons)
        self.assertEqual(result['title'],'Example Show')
        self.assertEqual(result['language'],'Hindi')
        self.assertEqual(result['synopsis'],'Story here.')
        self.assertEqual(result['episode_count'],2)
        poster.raw_text='Movie Name: Unrelated movie'
        self.assertIsNone(parse_split_series(poster,buttons))

    def test_series_poster(self):
        m=post()
        m.raw_text='Series Name: Crime Patrol 2026\nRelease Year: 2026\nSeries-SYNOPSIS/PLOT:\nA series description.'
        parsed=parse_post(m)
        self.assertEqual(parsed['kind'],'series')
        self.assertEqual(parsed['title'],'Crime Patrol 2026')
        self.assertEqual(parsed['synopsis'],'A series description.')

    def test_private_and_public_links(self):
        self.assertEqual(telegram_target('https://t.me/c/1234567890/4042'), {'peer': -1001234567890, 'post': 4042})
        self.assertEqual(telegram_target('https://t.me/examplechannel/3135?single'), {'peer': 'examplechannel', 'post': 3135})

    def test_reject_non_message_links(self):
        for link in ['https://evil.test/examplechannel/1','https://t.me/+invite','https://t.me/bot?start=1',
                     'https://t.me@evil.test/name/1','https://t.me/c/22/0','file:///etc/passwd', None]:
            with self.subTest(link=link):
                self.assertIsNone(telegram_target(link))

    def test_metadata_and_multiple_versions(self):
        movie=parse_post(post())
        self.assertEqual(movie['title'],'Test movie')
        self.assertEqual(movie['synopsis'],'A test story.')
        self.assertEqual(len(movie['sources']),2)

    def test_ignore_non_movie_and_duplicate_buttons(self):
        p=post();p.buttons[0].append(p.buttons[0][0])
        self.assertEqual(len(parse_post(p)['sources']),2)
        p.raw_text='Pinned notice'
        self.assertIsNone(parse_post(p))


class Download:
    def __init__(self, data): self.data=data;self.closed=False
    def __aiter__(self):return self
    async def __anext__(self):
        if not self.data:raise StopAsyncIteration
        result,self.data=self.data[:7],self.data[7:]
        return result
    async def close(self):self.closed=True


class FakeTelegram:
    def __init__(self):self.data=bytes(range(100));self.last=None;self.fail=False
    async def get_input_entity(self, peer):return peer
    async def get_messages(self, peer, ids):
        return NS(document=True, media='video',file=NS(size=len(self.data),mime_type='video/mp4',name='test.mp4'))
    def iter_download(self, media, offset, file_size):
        self.last=Download(self.data[offset:]);return self.last
    async def iter_messages(self, channel):
        yield post(3136)
        if self.fail:raise RuntimeError('test failure')


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.tg=FakeTelegram()
        self.lib=Library(self.tg,Path(self.temp.name))
        self.lib.movies={'3135':parse_post(post())}
        self.app=create_app(self.lib)
        self.client=TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.lib.close();await self.client.close();self.temp.cleanup()

    async def test_stream_full_range_suffix_and_head(self):
        for header,expected,status in [(None,self.tg.data,200),('bytes=13-27',self.tg.data[13:28],206),('bytes=-9',self.tg.data[-9:],206)]:
            r=await self.client.get('/stream/3135',headers={'Range':header} if header else {})
            self.assertEqual(r.status,status);self.assertEqual(await r.read(),expected)
            self.assertTrue(self.tg.last.closed)
        r=await self.client.head('/stream/3135',headers={'Range':'bytes=13-27'})
        self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Length'],'15');self.assertEqual(await r.read(),b'')

    async def test_disconnected_telegram_reports_retryable_error(self):
        async def disconnected(*args, **kwargs): raise ConnectionError('offline')
        self.tg.get_messages=disconnected
        r=await self.client.get('/stream/3135')
        self.assertEqual(r.status,503)
        self.assertEqual(r.headers['Retry-After'],'30')

    async def test_episode_sync_and_playback(self):
        self.lib.episode_channels=[{'peer':-100111,'title':'Show'}]
        async def messages(channel):
            if channel=='examplechannel': yield post()
            else: yield NS(id=9,raw_text='Show S02 E03',document=True,file=NS(name=None,mime_type='video/mp4',size=100))
        self.tg.iter_messages=messages
        await self.lib.sync()
        r=await self.client.get('/api/movies')
        self.assertEqual(len((await r.json())['movies']),2)
        r=await self.client.get('/stream/episode_100111_9',headers={'Range':'bytes=13-27'})
        self.assertEqual(r.status,206)
        self.assertEqual(await r.read(),self.tg.data[13:28])
        r=await self.client.get('/poster/episode_100111_9')
        self.assertEqual(r.status,200)
        self.assertIn('S02 E03',await r.text())

    async def test_series_poster_expands_episode_list(self):
        self.lib.episode_channels=[{'peer':-1001234567890,'title':'Show'}]
        async def messages(channel):
            if channel=='examplechannel':
                m=post();m.raw_text='Series Name: Show';yield m
            else:
                for n in [3,1,2]:
                    yield NS(id=n,raw_text=f'Show S01 E{n:02d}',document=True,file=NS(name=None,mime_type='video/mp4',size=100))
        self.tg.iter_messages=messages
        await self.lib.sync()
        series=self.lib.movies['3135']
        self.assertEqual(series['episode_count'],3)
        self.assertEqual([s['post'] for s in series['sources']],[1,2,3])
        self.assertEqual(self.lib.movies['episode_1001234567890_1']['series_id'],3135)
        r=await self.client.get('/stream/3135?source=2',headers={'Range':'bytes=0-9'})
        self.assertEqual(r.status,206)
        self.assertEqual(await r.read(),self.tg.data[:10])

    async def test_invalid_range_and_source(self):
        r=await self.client.get('/stream/3135',headers={'Range':'bytes=100-'})
        self.assertEqual(r.status,416);self.assertEqual(r.headers['Content-Range'],'bytes */100')
        for suffix,status in [('?source=-1',400),('?source=abc',400),('?source=99',400)]:
            r=await self.client.get('/stream/3135'+suffix);self.assertEqual(r.status,status)
        r=await self.client.get('/stream/4042');self.assertEqual(r.status,404)

    async def test_catalogue_does_not_expose_source_ids(self):
        r=await self.client.get('/api/movies');movie=(await r.json())['movies'][0]
        self.assertNotIn('sources',movie);self.assertEqual(movie['versions'],['Hindi','English'])

    async def test_lan_requires_pairing_and_remembers_cookie(self):
        with patch.object(web.Request,'remote',new_callable=PropertyMock,return_value='192.168.1.55'):
            for path in ['/api/movies','/poster/3135','/stream/3135','/Movie-Time-TV.apk']:
                r=await self.client.get(path);self.assertEqual(r.status,401)
            status=await (await self.client.get('/api/status')).json()
            self.assertFalse(status['paired']);self.assertNotIn('pin',status)
            r=await self.client.post('/api/pair',json={'pin':'wrong'});self.assertEqual(r.status,401)
            r=await self.client.post('/api/pair',json={'pin':self.app['pairing_pin']});self.assertEqual(r.status,200)
            cookie=r.cookies['movie_time'].value
            r=await self.client.get('/api/movies',headers={'Cookie':'movie_time='+cookie});self.assertEqual(r.status,200)
            stored=json.loads((Path(self.temp.name)/'devices.json').read_text())
            self.assertNotIn(cookie,stored['tokens'])

    async def test_host_origin_and_pair_rate_limit(self):
        r=await self.client.get('/api/status',headers={'Host':'evil.test:8765'});self.assertEqual(r.status,403)
        r=await self.client.post('/api/sync',headers={'Origin':'http://evil.test'},json={});self.assertEqual(r.status,403)
        for _ in range(5):
            r=await self.client.post('/api/pair',json={'pin':'wrong'});self.assertEqual(r.status,401)
        r=await self.client.post('/api/pair',json={'pin':'wrong'});self.assertEqual(r.status,429)

    async def test_complete_sync_removes_deleted_posts_and_persists(self):
        await self.lib.sync()
        self.assertEqual(set(self.lib.movies),{'3136'})
        restored=Library(self.tg,Path(self.temp.name));self.assertEqual(set(restored.movies),{'3136'})

    async def test_failed_sync_preserves_previous_titles(self):
        self.tg.fail=True
        await self.lib.sync()
        self.assertIn('3135',self.lib.movies);self.assertIsNotNone(self.lib.status['error'])


if __name__=='__main__':unittest.main()
