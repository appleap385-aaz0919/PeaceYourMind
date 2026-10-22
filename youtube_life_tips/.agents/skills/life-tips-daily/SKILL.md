---
name: life-tips-daily
description: Create one original Korean household-tips YouTube Short each day using seasonal-first research, a review handoff, one built-in ImageGen image, local rendering, and the explicitly configured life-tips channel.
---

# Daily life-tips Short

This workflow is restricted to the `youtube_life_tips` folder. Do not inspect, modify, or reuse assets or credentials from the parent Peace in Mind project.

## Schedule and control

- Windows Task Scheduler starts the mailbox watcher at the user's logon and enqueues the daily request at 05:00 Korea Standard Time.
- The watcher launches Codex CLI stages only when work exists. It uses short-lived, separate main, review, and developer sessions with file handoffs; it does not rely on Codex Scheduled or a permanently open Codex desktop window.
- The 06:30 KST cutoff is strict. Uploading is allowed only after every stage passes and the video can be scheduled for 07:00 KST. If the PC is off/asleep at 05:00, the date is skipped without catch-up.
- Missing login, quota, Internet, ImageGen, channel OAuth, local TTS, FFmpeg, or any review/validation means skip; never try a different channel or credentials.

## Required sequence

1. Use the current Asia/Seoul date and the Korean season: spring March-May, summer June-August, autumn September-November, winter December-February. Review `work/sample/metadata.json` and previous `work/daily/*/content.json` at the content level. Avoid repeating the same practical tip, core claim, solution sequence, or distinctive hook. Broad subjects, appliances, and categories may recur when the actual advice and angle differ materially; do not reject a useful idea solely because its broad topic appeared before.
2. Search for useful household tips relevant to the current season first. Verify key facts using at least two reliable sources, preferably primary sources. If a suitable seasonal topic cannot be supported by two reliable sources, choose a season-neutral topic and state the reason in `fallback_reason`. Do not force a seasonal angle. Set `topic_strategy` to `seasonal` or `evergreen_fallback`.
3. Write a new, conversational Korean script with exactly four concise scenes, under 55 seconds total. Do not copy source wording or any reference video's words, images, thumbnail, audio, or sequence. Keep source links in the YouTube description only; do not render source credits into the video.
4. A separate review session independently verifies sources and claims, safety, content-level originality, scene structure, and whether the seasonal choice or fallback is justified. It rejects materially repeated advice, not broad-topic overlap by itself. If it finds an unresolved issue, stop.
5. The main session incorporates review findings and approves the final plan. It must retain at least two HTTPS source records and the seasonal decision fields.
6. Invoke the built-in `$imagegen` exactly once for a new high-resolution portrait 2x2 storyboard with four distinct scenes, no text, captions, logos, or watermark. Save as `work/daily/YYYY-MM-DD/storyboard.png`. Do not reuse `work/sample/`, previous daily images, or source images. If ImageGen fails or cannot save, stop; do not substitute downloaded assets, code-drawn scenes, or another image API.
7. Save `content.json` and run `python render_daily.py --date YYYY-MM-DD`. The renderer uses local Edge TTS and 720x1280/15fps output with one FFmpeg thread. Missing packages, TTS/render errors, unreadable captions, wrong dimensions, missing audio, or duration over 55 seconds mean stop.
8. Main performs an independent final audit of the storyboard, approved script, sources, seasonal choice/fallback, video metadata, duration, dimensions, and audio. Do not upload unless every check passes.
9. Run `python upload_daily.py --date YYYY-MM-DD` only before 06:30 KST. It verifies the exact channel in `state/config.local.json` and schedules a private upload for 07:00 KST. Never upload to another channel or attempt a late/catch-up post.
10. Write the result to `work/mailbox/outbox/YYYY-MM-DD.json`: `scheduled`, `skipped`, or `failed`, with URL or a specific reason. Do not send email or Kakao messages.

## Resource limits

- One ImageGen call and one video per Korea date; run stages serially.
- Use 720x1280, 15 fps, one FFmpeg/x264 thread. Keep assets and intermediate files under `work/daily/`.
- Do not install packages during a daily run. Use the existing `work/vendor` local Edge TTS package.
- Never commit credentials, OAuth tokens, generated videos, or daily output.
