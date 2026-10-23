# Peace in Mind — YouTube Shorts

This folder is a standalone Shorts pipeline. It reads verified verses from `../verses.yaml`, creates a narrated Korean vertical video, adds the app and website call to action, and uploads through the YouTube Data API. It does not change the PWA, Android app, or existing video collection batch.

The daily picker uses only verified, non-crisis entries whose reference identifies one verse. Consecutive dates go through the pool before a verse can repeat. The current pool has 266 single-verse entries. KRV text and the attribution `성경전서 개역한글판, 대한성서공회` are preserved.

## Viewer journey and links

Each Short opens on the app emotion-entry screen, reveals the daily verse on the result page with the continuation-reading tab selected, then switches to the praise recommendations and YouTube player handoff. The daily verse is overlaid on the real app screenshots so it always matches the narration. Three low male Korean neural TTS segments cover the emotion prompt, verse, and praise recommendation; short crossfades align the app-screen changes with each segment. The YouTube handoff uses the actual recommended thumbnail with a player-state animation. The ending asks viewers to use the channel profile link to open the website or download the Android app.

Shorts descriptions and comments do not make URLs clickable. Add these as channel profile links:

- Website: https://appleap385-aaz0919.github.io/PeaceYourMind/
- Android app: https://play.google.com/store/apps/details?id=io.github.appleap385.peaceinmind

The same URLs are included in descriptions for reference, with a clear "프로필 링크" instruction.

## Render a local draft

Python 3.12+, FFmpeg/FFprobe, a Korean font, and Google Cloud Text-to-Speech Application Default Credentials are required. Google Cloud currently offers Korean Neural2 voices; the default is the low male `ko-KR-Neural2-C` voice at a slower reading rate and lower pitch, with no background music.

From the repository root:

```powershell
python -m pip install -r youtube_shorts/requirements.txt
gcloud auth application-default login
python youtube_shorts/scripts/choose_verse.py --date 2026-10-22 --output-dir youtube_shorts/work/2026-10-22
python youtube_shorts/scripts/render_short.py youtube_shorts/work/2026-10-22/2026-10-22.json
python youtube_shorts/scripts/build_metadata.py youtube_shorts/work/2026-10-22/2026-10-22.json
```

This writes the narrated MP4, app walkthrough frames, and metadata beneath the ignored `youtube_shorts/work/` directory. Before automation, listen to the MP4 and confirm that the AI voice reads the older KRV spelling clearly.

## Upload authorization

Uploading requires the channel owner's OAuth consent. A regular YouTube API key cannot upload on a creator's behalf. Use a Google Cloud project with YouTube Data API v3 enabled and desktop OAuth credentials. Run `authorize_youtube.py` once on the channel owner's PC; it writes `youtube_shorts/token.local.json`. This file is ignored by Git and must stay private.

With that credential, a generated video can be uploaded privately by default. To schedule public release, pass a future KST timestamp at least 15 minutes ahead:

```powershell
python youtube_shorts/scripts/upload_short.py `
  youtube_shorts/work/2026-10-22/short-draft.mp4 `
  youtube_shorts/work/2026-10-22/metadata.json `
  --publish-at-kst 2026-10-22T07:00
```

The upload history is stored in `youtube_shorts/state/uploads.json` to prevent a repeat upload for the same KST date. Tokens and OAuth client secrets are excluded by `.gitignore`.

## Daily automation

The daily runner is `.github/workflows/youtube-shorts.yml`, separate from the app and video-data workflows. It has primary and retry starts at 01:30 and 02:15 KST, then uploads a private Short and asks YouTube to publish it at 07:00 KST. GitHub Actions uses UTC for cron, so these starts are `30 16 * * *` and `15 17 * * *`. Before rendering, each scheduled run checks the date-to-video-ID ledger and skips the day if a Short is already recorded. Scheduled runs require the repository Actions secrets `PYM_TTS_SERVICE_ACCOUNT_JSON`, `PYM_YOUTUBE_TOKEN_JSON`, and `PYM_SMTP_APP_PASSWORD`; the workflow stops before rendering if any are missing. `PYM_YOUTUBE_TOKEN_JSON` must contain the channel owner's OAuth token JSON with the `youtube.upload` scope. A YouTube API key alone cannot upload videos.

Daily status is sent from `appleap385@gmail.com` to `aaz0919@naver.com` through Gmail SMTP at no per-message charge. Create a Google App Password for the sender account (2-Step Verification must be enabled) and store it only as the GitHub Actions secret `PYM_SMTP_APP_PASSWORD`; never commit or paste the password into project files. The email contains the scheduled Short link on success, or the GitHub Actions run link if generation or upload fails.

For Google OAuth, set the consent screen publishing status to Production before relying on the scheduled refresh token. In Testing mode, YouTube-scope authorizations for external users expire after seven days.

Google Cloud requires billing to be enabled for Text-to-Speech. The Neural2 tier currently includes one million input characters per month, then costs US$16 per million characters. A single short verse each day is far below that monthly allowance. See [official pricing](https://cloud.google.com/text-to-speech/pricing?hl=ko) and the [Korean voice list](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types?hl=ko).
