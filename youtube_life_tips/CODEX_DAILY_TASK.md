# Daily life-tips Short workflow

This workflow is launched by the project's Windows Task Scheduler mailbox. It is not a Codex Scheduled task. The watcher invokes separate, short-lived Codex CLI sessions for the main writer, reviewer, visual developer, and final auditor; they exchange JSON and image files under `work/mailbox/` and `work/daily/`.

At 03:00 Asia/Seoul, enqueue today's request. Permanent preflight errors stop the date; temporary connection/service errors may be queued for bounded retries. The watcher runs the stages serially, at most three attempts with 1-minute then 3-minute waits, and may start uploading only before 06:30. Successful stage files and validated renders are reused. Starting at 03:00 leaves 3.5 hours before the upload cutoff. The YouTube uploader schedules the video privately for 07:00 Asia/Seoul. If the PC is off/asleep at the scheduled start, or validation still fails after permitted retries, skip the date. Never catch up or upload on a later date. An uncertain ImageGen attempt must never be repeated that day.

Work only inside `youtube_life_tips`. Do not read or use the parent Peace in Mind project, its credentials, assets, or channel. Do not use Gemini, paid APIs, downloaded media, or prior/sample visuals. Use the built-in `$imagegen` exactly once for one new four-panel storyboard. If ImageGen is unavailable, fails, reaches a limit, or cannot save into today's folder, skip the date.

## Research selection rule

Use the current Korean season for topic selection: spring is March-May, summer June-August, autumn September-November, and winter December-February. Search seasonal household needs first and verify the practical claim against at least two reliable sources, preferably primary sources. If no suitable seasonal topic can be supported by two reliable sources, use a season-neutral household tip and explain the fallback in `fallback_reason`. Never force a seasonal angle or invent seasonal evidence. Record `topic_strategy` as `seasonal` or `evergreen_fallback`; the independent reviewer must verify the season fit or fallback reason.

## Content-level repetition check

Before drafting, compare the idea with `work/sample/metadata.json` and previous `work/daily/*/content.json` records. Avoid reusing the same actionable recommendation, central factual claim, solution steps, or distinctive hook. Repeating a broad subject, appliance, room, or category is acceptable when the practical advice and editorial angle are meaningfully different. The reviewer must reject material content repetition, but must not reject a tip just because it shares a broad topic.

## Daily handoff

1. Main researches the seasonal-first topic and writes `draft.json` with four short original Korean narration/caption scenes and at least two HTTPS sources.
2. Reviewer independently verifies the cited claims, safety, content-level originality, and season selection. Any unresolved issue means skip.
3. Main incorporates review findings and writes `approved.json`. The plan must record the date, season, `topic_strategy`, fallback reason when relevant, title, description, scenes, and sources.
4. Developer makes exactly one new ImageGen storyboard and saves `work/daily/YYYY-MM-DD/storyboard.png`. Reused or duplicate art is rejected.
5. The local renderer creates and checks a 720x1280, 15fps video with Korean Edge TTS and one FFmpeg thread.
6. Main audits the generated storyboard, final content, metadata, duration, dimensions, audio, sources, and season decision. Only a complete approval permits upload.
7. `upload_daily.py` verifies the configured life-tips channel and schedules the private upload for 07:00. The 06:30 cutoff prevents late publishing.

Write the final status to `work/mailbox/outbox/YYYY-MM-DD.json` and logs to `work/mailbox/runs/YYYY-MM-DD/`. The local runner sends one result email for each final status when secure email notifications are configured. Never commit credentials, tokens, videos, or daily work products.
