"""Sign in locally, then run the Movie Time library on your home network."""
import argparse
import asyncio
import getpass
import json
from pathlib import Path
from aiohttp import web
from telethon import TelegramClient
from library_server import Library, create_app, lan_addresses

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / 'private'


async def main(port=8765, unattended=False):
    PRIVATE.mkdir(exist_ok=True)
    config_file = PRIVATE / 'config.json'
    if config_file.exists():
        config = json.loads(config_file.read_text())
    else:
        if unattended:
            raise RuntimeError('Telegram setup is missing. Run Start Movie Time.cmd and sign in first.')
        print('Create your Telegram API credentials at https://my.telegram.org > API development tools.')
        config = {'api_id': int(input('API ID: ').strip()),
                  'api_hash': getpass.getpass('API hash (hidden): ').strip()}
        config_file.write_text(json.dumps(config))
    if not config.get('channel'):
        if unattended:
            raise RuntimeError('Set the channel in private/config.json first.')
        channel = input('Poster channel username (without @) or numeric channel ID: ').strip().lstrip('@')
        if not channel:
            raise ValueError('A poster channel is required.')
        config['channel'] = int(channel) if channel.lstrip('-').isdigit() else channel
        config_file.write_text(json.dumps(config))
    client = TelegramClient(str(PRIVATE / 'telegram'), config['api_id'], config['api_hash'])
    runner, library = None, None
    try:
        if unattended:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError('Telegram login expired. Sign in again using the local launcher.')
        else:
            await client.start(phone=lambda: input('Your Telegram phone number with country code: '),
                               code_callback=lambda: getpass.getpass('Telegram login code (hidden): '),
                               password=lambda: getpass.getpass('Telegram two-step password (hidden): '))
        await client.get_dialogs()
        library = Library(client, PRIVATE, channel=config['channel'])
        app = create_app(library, port)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', port).start()
        print(f'\nMOVIE TIME is ready: http://127.0.0.1:{port}')
        for address in lan_addresses():
            print(f'TV / phone address: http://{address}:{port}')
        if not unattended:
            print(f"Pairing code: {app['pairing_pin']}")
        print('Importing the channel in the background. Keep this window open and laptop awake. Ctrl+C stops it.')
        library.start_sync()
        # Telethon retries transient outages itself. If it gives up, terminate
        # this stale server so the boot supervisor starts a fresh connection.
        await client.disconnected
        raise ConnectionError('Telegram disconnected; restarting the server connection.')
    finally:
        if library:
            await library.close()
        if runner:
            await runner.cleanup()
        await client.disconnect()


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--port', type=int, default=8765)
    args.add_argument('--unattended', action='store_true')
    options = args.parse_args()
    try:
        asyncio.run(main(options.port, options.unattended))
    except KeyboardInterrupt:
        print('\nStopped.')
