# RuralVoice Assistant

## Zimbabwe ANPR Dashboard

The ANPR detector is in `main.py`. The browser dashboard is in `dashboard.py` and reads the same `plates.db` database that the detector writes to.

Run the detector:

```powershell
py main.py --video 0524.mp4
```

Run the dashboard in another terminal:

```powershell
py dashboard.py
```

Open:

```text
http://127.0.0.1:8080
```

The dashboard auto-refreshes every 3 seconds and shows detected plate, status, time, vehicle type, confidence, and snapshot.
It also shows a demo registration section with generated owner details for each detected plate. These owner records are dummy data for presentation only.

## Phone Capture Mode

Use this when your phone should take the picture while the laptop runs the trained YOLO and OCR models.

1. Connect the phone and laptop to the same Wi-Fi.
2. Start the phone capture server:

```powershell
py mobile_server.py
```

3. The terminal will print an address like:

```text
http://192.168.1.25:8090
```

4. Open that address on your phone browser.
5. Tap the file/camera input, take a photo, then tap `Detect Plate`.

Do not open `127.0.0.1` from the phone. On a phone, `127.0.0.1` means the phone itself, not the laptop.

If Windows Firewall asks for permission, allow Python on private networks.

## Hosted Server Mode

To stop depending on your laptop, deploy the phone capture server to a cloud GPU server. Follow:

[DEPLOY_SERVER.md](DEPLOY_SERVER.md)

After deployment, your phone will open the public server URL instead of the laptop Wi-Fi address.

Offline-first phone assistant concept for rural Zimbabwean users and blind users.

This repository currently contains:

- A system blueprint in [docs/SYSTEM_BLUEPRINT.md](docs/SYSTEM_BLUEPRINT.md).
- A starter command grammar in [docs/COMMAND_GRAMMAR.md](docs/COMMAND_GRAMMAR.md).
- An Android MVP skeleton in [android-assistant](android-assistant).

## What Works In The Skeleton

- Basic Android project structure.
- Voice command data model.
- English/Shona/Ndebele starter command parser.
- Spoken feedback through Android TextToSpeech.
- Intent-based opening of contacts, dialer/calls, and installed apps.
- AccessibilityService scaffold for future `home`, `back`, and screen-reading commands.

## What Must Be Added Next

- Real offline speech recognition engine.
- Contact lookup by name before calling.
- Confirmation flow for calls and dangerous commands.
- Media search against local audio/video files.
- AccessibilityService binding from the command executor.
- Low-end phone testing and phrase tuning with Zimbabwean voices.

## Android Build

Open `android-assistant` in Android Studio.

Recommended first test device:

- Android 8 or newer.
- Has Google/Android TextToSpeech installed, or another TTS engine.
- Microphone permission available.
- Accessibility permission can be enabled manually.

After installing:

1. Open Android Settings.
2. Go to Accessibility.
3. Enable RuralVoice.
4. Open the RuralVoice app.
5. Test the current demo button.

## Feature Phone Build

Do not try to install this Android APK on KaiOS or Java button phones. They need separate apps.

For KaiOS, build a web app with a manifest and test capabilities on target devices.

For Java/J2ME, build only a limited keypad app if the specific phone supports MIDlets.

For closed button phones, use an IVR/USSD/SMS assistant instead of an offline installed assistant.
