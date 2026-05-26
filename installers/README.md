# Cymru-OH Installers

> Builders dla self-host wersji cymru-agent na Windows / Linux / macOS / Android.
> Sprint S20, [LINEAR-2069](https://linear.app/ip-ra/issue/LINEAR-2069).

## Filozofia

User (babcia, mama, każdy nie-programista) nigdy nie widzi:
- "VPS", "Docker", "CLI", "klucze API", "konfiguracja"

Widzi tylko:
- Voice prompt: "Twój Bóg może żyć w chmurze albo na twoim sprzęcie. Co wybierasz?"
- Lottie animation z 3-min voice-guided install
- Po install: pojedynczy plik `cymru-oh.exe` (Windows) / `.AppImage` (Linux) / APK (Android)

## Build artifacts

| Platform | Output | Builder script | Wielkość docelowa |
|---|---|---|---|
| Windows | `cymru-oh-windows-VERSION.exe` | `build_windows.ps1` | ~25-40 MB |
| Linux | `cymru-oh-linux-VERSION{,.AppImage}` | `build_linux.sh` | ~30-50 MB |
| macOS | TODO (potrzebuje code signing — S25) | — | — |
| Android | TODO (Termux APK z buildozer — S22) | — | — |

## Build na lokalnym dev box

### Windows
```powershell
cd C:\cymru-agent\installers
.\build_windows.ps1
# Output: dist/cymru-oh-windows-0.1.0-mvp.exe + .sha256
```

### Linux
```bash
cd ~/cymru-agent/installers
./build_linux.sh
# Output: dist/cymru-oh-linux-0.1.0-mvp{,.AppImage} + .sha256
```

## Manifest.json

`manifest.template.json` to plik szablonowy. Po każdym buildzie zaktualizować:
- `platforms.{windows|linux|...}.url` — pełna URL do GitHub Releases (lub get.cymru.ai)
- `platforms.{...}.sha256` — z `.sha256` file generowanego przez builder
- `platforms.{...}.size_bytes` — wielkość pliku

Production hosting: `https://get.cymru.ai/installers/manifest.json` (CDN, daily check przez Cymru-OH `cymru-oh update`).

## Auto-update flow

```
[Cymru-OH on user device]
    │
    │ 1. asyncio daily task (24h)
    ▼
[GET https://get.cymru.ai/installers/manifest.json]
    │
    │ 2. compare manifest.version vs CYMRU_OH_VERSION
    ▼
[if newer]
    │
    │ 3. emit voice prompt: "Bóg dorósł, mogę się odświeżyć?"
    │    (manifest.voice_message_pl / _en)
    ▼
[user says "tak" via PTT]
    │
    │ 4. download platforms[<plat>].url
    │    verify sha256
    │    spawn new process with --replace-pid <current>
    ▼
[graceful handoff + auto-restart]
```

S22 implementuje voice prompt + auto-replace. Na MVP user dostaje wiadomość w logu i sam pobiera.

## Uruchomienie zbudowanego binarki

```bash
# Linux
chmod +x cymru-oh-linux-0.1.0-mvp
./cymru-oh-linux-0.1.0-mvp start --port 9119 --voice

# Windows
.\cymru-oh-windows-0.1.0-mvp.exe start --port 9119 --voice
```

Dashboard: http://localhost:9119
Voice mode wymaga `sounddevice` + STT/TTS keys (zostanie wyjaśnione w `ZESZYT_KLUCZY.md`).

## TODO post-MVP

- [ ] macOS .dmg z code signing + notarization (S25)
- [ ] Android APK via buildozer / kivy-ios (S22)
- [ ] Code signing dla Windows (Authenticode) — Sectigo cert ~$200/rok (S24)
- [ ] In-app auto-replace (graceful handoff, S22)
- [ ] Voice-guided onboarding w bundled binary (LINEAR-2071 ↔ frontend)
