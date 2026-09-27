# DAN Movie Time

A personal Telegram media library for Windows, Android TV and Android-based Fire TV. Early beta, tested on a Mi TV and an Android-based Fire Stick.

Your laptop reads a poster channel and streams linked Telegram video files to paired devices on the same home network. Telegram credentials stay on the laptop. No full-library download is required.

## Features

- Searchable posters, language and genre filters, movie details and multiple versions.
- Series posters with ordered episode selection and a Next episode button.
- Direct episode channels and adjacent poster/episode-button posts.
- Compact TV layout, remote navigation, seeking, buffering indicator and per-device resume.
- Eight-digit device pairing and a private local catalogue cache.

## Requirements

- Windows laptop, Python 3.11 or newer (3.12 tested), internet and home Wi-Fi.
- Your own Telegram account with access to the channels containing your media.
- Telegram API ID and API hash from https://my.telegram.org under API development tools.
- Browser for laptop/phone playback. Building the TV app also requires a JDK and Android SDK.

## First setup

1. Download the source and extract it to a folder.
2. Open PowerShell in that folder and run `powershell -ExecutionPolicy Bypass -File .\setup.ps1`.
3. Double-click **Start Movie Time.cmd**.
4. Enter your Telegram API credentials and login details locally when prompted. Then enter your poster channel username or numeric ID.
5. Open http://127.0.0.1:8765 and wait for the initial import.
6. Select **Connect a TV** for the LAN address and pairing code. Keep the server window open and laptop awake.

Allow the Python server through Windows Firewall on your trusted home network if prompted. Do not forward port 8765 on your router. This beta uses local HTTP and is not designed for public internet exposure.

## Telegram post formats

A normal poster has a photo, a `Movie Name:` or `Series Name:` caption field and Telegram message URL buttons linking to video files. Optional caption fields include Release Year, Language, Genre, Quality and Size.

For a split series post, the poster must be immediately followed by a message with EP1, EP2, etc. URL buttons. Captioned posters must have `Series Name:`. For a captionless poster, the first linked video's caption must contain a title followed by S01 E01-style numbering. Unrelated or unsupported posts are skipped.

For directly uploaded episode channels, create `private/sources.json` using this structure and replace the example with your own channel ID:

```json
{"episode_channels": [{"peer": -1001234567890, "title": "Example Show"}]}
```

Restart the server after changing this configuration. **Refresh channel** updates all configured sources. A series poster pointing into a configured episode channel opens an ordered episode picker.

## Build and install the TV app

Set JAVA_HOME to your JDK, install Android SDK build-tools 36.1.0 and platform android-36.1, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-tv.ps1
```

The script generates a personal signing key under private/ and writes dist/Movie-Time-TV.apk. Keep that key to install future updates over the same app. The original developer's signing key and APK are not included.

Transfer your built APK to the TV and install it, or use `install-fire-tv.ps1 -TvAddress YOUR_TV_IP` with ADB debugging enabled. Approve the laptop on the TV. Enter the server address and pairing code once; the app remembers them. Devices running non-Android Fire TV software cannot use this APK.

## Privacy and limitations

Never upload private/, Telegram sessions, API credentials, device tokens, cached posters/catalogues or signing keys. The included .gitignore excludes these files. Only use channels and media you have permission to access and share.

Playback depends on Telegram throughput, Wi-Fi and the TV's codecs. There is no transcoding, embedded audio-track selection, external subtitle loading or cross-device progress sync. The laptop must remain awake and online. Progress is stored by episode/version position, so changing the source order can affect resume history. This release runs manually; machine-specific Windows SYSTEM startup scripts are deliberately excluded.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Automated tests use fake Telegram clients and cover parsing, episode grouping, ranges, pairing, host/origin checks and connection errors. They do not require Telegram credentials. Real TV behavior still needs device testing.

## Project status

Personal early beta, released under the MIT licence. See [LICENSE](LICENSE). Bug reports and suggestions are welcome through GitHub Issues; see [CONTRIBUTING.md](CONTRIBUTING.md).

This repository contains source code. No prebuilt APK release is currently supplied; use the build instructions above. You must provide your own Telegram account and media sources.
