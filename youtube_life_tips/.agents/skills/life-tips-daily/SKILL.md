---
name: life-tips-daily
description: Create an original Korean household-tips YouTube Short for a morning or evening release using seasonal-first research, a review handoff, one built-in ImageGen image, local rendering, and the configured life-tips channel.
---

# Daily life-tips Short

This workflow is restricted to the `youtube_life_tips` folder. Do not inspect, modify, or reuse assets or credentials from the parent Peace in Mind project.

## Schedule and control

- Windows Task Scheduler starts the mailbox watcher at logon and enqueues releases at 03:00 and 15:00 Korea Standard Time. Morning release keys are `YYYY-MM-DD`; evening keys are `YYYY-MM-DD-pm`.
- The watcher launches Codex CLI stages only when work exists. It uses short-lived, separate main, review, and developer sessions with file handoffs; it does not rely on Codex Scheduled or a permanently open Codex desktop window.
- The 06:30/18:30 KST cutoffs are strict for the 07:00/19:00 releases. If the PC is off/asleep at the corresponding start, that release is skipped without catch-up.
- Missing login, quota, Internet, ImageGen, channel OAuth, local TTS, FFmpeg, or any review/validation means skip; never try a different channel or credentials.

## Required sequence

1. Use the current Asia/Seoul date and the Korean season: spring March-May, summer June-August, autumn September-November, winter December-February. Review `work/sample/metadata.json` and previous `work/daily/*/content.json`. Avoid repeating the same practical tip, core claim, solution sequence, or distinctive hook. A broad household task category may recur when the actual advice remains useful and distinct.
2. Search for useful household tips relevant to the current season first. Verify key facts using at least two reliable sources, preferably primary sources. If no seasonal tip is both well-supported and genuinely useful, choose a season-neutral topic and state the reason in `fallback_reason`. Do not force a seasonal angle. Set `topic_strategy` to `seasonal` or `evergreen_fallback`.
3. Write a new, conversational Korean script as a continuous spoken_script, then split into concise scenes at natural meaning boundaries, under 55 seconds total. Record the ordinary approach, a sourced non-obvious decision that materially changes the viewer's action, and why the difference matters in `viewer_value`. Generic advice such as putting fruit in a refrigerator or folding clothes into a drawer does not pass; adding a fact that leaves the action unchanged does not rescue it. Read all scene narrations as one spoken script and remove abrupt transitions, repeated advice, and a filler ending. Do not copy source wording or any reference video's words, images, thumbnail, audio, or sequence. Keep source links in the YouTube description only; do not render source credits into the video.
4. A separate review session independently verifies sources and claims, safety, concrete viewer value, natural narration flow, content-level originality, scene structure, and whether the seasonal choice or fallback is justified. Repair editorial issues and re-review before ImageGen (up to two revisions). Stop only if issues remain unresolved or facts/safety are unverified.
5. The main session incorporates review findings and approves the final plan. It must retain at least two HTTPS source records and the seasonal decision fields.
6. Invoke the built-in `$imagegen` exactly once per candidate for a new high-resolution portrait storyboard using storyboard_grid (two columns and ceil(scene_count/2) rows), one distinct panel per scene, no text, captions, logos, or watermark. Save as `work/daily/RELEASE-KEY/storyboard.png`. Do not reuse `work/sample/`, previous daily images, or source images. If ImageGen fails or cannot save, stop; do not substitute downloaded assets, code-drawn scenes, or another image API.
7. Save `content.json` including `slot` (`am` or `pm`) and run `python render_daily.py --date YYYY-MM-DD --slot am|pm`. The renderer uses local Edge TTS and 720x1280/15fps output with one FFmpeg thread. Missing packages, TTS/render errors, unreadable captions, wrong dimensions, missing audio, or duration over 55 seconds mean stop.
8. Main performs an independent final audit of the storyboard, approved script, sources, seasonal choice/fallback, video metadata, duration, dimensions, and audio. Do not upload unless every check passes.
9. Run `python upload_daily.py --date YYYY-MM-DD --slot am|pm` before the slot's cutoff. It verifies the exact channel in `state/config.local.json` and schedules the selected release. Never upload to another channel or attempt a late/catch-up post.
10. Write the result to `work/mailbox/outbox/RELEASE-KEY.json`: `scheduled`, `skipped`, or `failed`, with URL or a specific reason. The mailbox runner owns email delivery.

## Resource limits

- Up to three candidates per release, exactly one ImageGen call per candidate, and at most one published video per release. After a candidate fails final review, attempt up to two safe wording/layout revisions with independent re-review. If it still fails or cannot be safely repaired, preserve its assets, exclude its topic, and start a new script and storyboard on a different topic. Cancel after the third rejected candidate. Infrastructure/auth/quota failures stop without consuming more image calls. Run stages serially.
- Use 720x1280, 15 fps, one FFmpeg/x264 thread. Keep assets and intermediate files under `work/daily/`.
- Do not install packages during a daily run. Use the existing `work/vendor` local Edge TTS package.
- Never commit credentials, OAuth tokens, generated videos, or daily output.

## Comprehension and layout repair

Write spoken_script before splitting scenes; the ordered scene narrations must reproduce it without losing transitions. Use the number of scenes the explanation needs, never force four. Every scene needs visual_action matching its object, state, and instruction. The reviewer must return viewer_recap, scene_count, and transition_checks for every adjacent pair (from_scene, to_scene, clear, evidence quoting actual wording). Do not infer missing steps from the description or sources. Check the complete final on-screen text, not merely legibility.

Before ImageGen, measure the text at the real rendering widths. Reflow and resize within readable limits, then revise long wording or split scenes if needed, up to two revisions with independent review. Never silently truncate words or omit conditions to fit. Generate the grid, narration clips, and audit contact sheet for the resulting scene count. New uploads set containsSyntheticMedia=true.
