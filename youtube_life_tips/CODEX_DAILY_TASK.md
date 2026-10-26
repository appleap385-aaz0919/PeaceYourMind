# Daily life-tips Short workflow

This workflow is launched by the project's Windows Task Scheduler mailbox. It is not a Codex Scheduled task. The watcher invokes separate, short-lived Codex CLI sessions for the main writer, reviewer, visual developer, and final auditor; they exchange JSON and image files under `work/mailbox/` and `work/daily/`.

Enqueue the morning request at 03:00 Asia/Seoul for 07:00 release, and a separate evening request at 15:00 for 19:00 release. The upload cutoffs are 06:30 and 18:30. Each release has at most three attempts with 1-minute then 3-minute waits; successful stages and validated renders are reused. Missed starts and validation failures skip only that release without catch-up. An uncertain ImageGen attempt must never be repeated for the same release. Morning keys keep the legacy `YYYY-MM-DD` name; evening keys are `YYYY-MM-DD-pm`. Use the release key for daily folders, runs, requests, and reports.

Work only inside `youtube_life_tips`. Do not read or use the parent Peace in Mind project, its credentials, assets, or channel. Do not use Gemini, paid APIs, downloaded media, or prior/sample visuals. Use the built-in `$imagegen` exactly once per release for one new storyboard with a panel per scene. If ImageGen is unavailable, fails, reaches a limit, or cannot save into the release folder, skip that release.

## Research selection rule

Use the current Korean season for topic selection: spring is March-May, summer June-August, autumn September-November, and winter December-February. Search seasonal household needs first and verify the practical claim against at least two reliable sources, preferably primary sources. If no seasonal tip is both well-supported and genuinely useful, use a season-neutral household tip and explain the fallback in `fallback_reason`. Never force a seasonal angle or invent seasonal evidence. Record `topic_strategy` as `seasonal` or `evergreen_fallback`; the independent reviewer must verify the season fit or fallback reason.

## Content-level repetition check

Before drafting, compare the idea with `work/sample/metadata.json`, `work/previews/*/content.json`, and previous `work/daily/*/content.json` records, including the other release on the same date. Exclude only the current release's own content from comparison. Avoid repeating the same actionable recommendation, central factual claim, solution steps, or distinctive hook. Repeating a broad subject, appliance, room, or category is acceptable when the practical advice and editorial angle are meaningfully different.

## Viewer value and narration flow

Record `viewer_value.common_approach`, `better_decision`, and `why_it_matters`. The better decision must be a sourced, non-obvious condition, threshold, exception, or technique that materially changes what the viewer does. Reject scripts whose takeaway is merely “put fruit in the refrigerator” or “fold clothes into a drawer,” even if those statements are correct. A fact that can be removed without changing the obvious advice is decorative, not viewer value. Repeating a broad household category is allowed when the actual advice is useful and distinct. Read all scene narrations aloud as one script: each scene must advance the explanation, transitions must make sense, and the ending must add a payoff rather than repeat the advice. The reviewer must explain and pass both `usefulness_pass` and `flow_pass` before image generation. The final audit checks both again.

## Daily handoff

1. Main researches the seasonal-first topic and writes `draft.json` with a continuous spoken_script split into as many original Korean narration/caption scenes as needed, viewer value, and at least two HTTPS sources.
2. Reviewer independently verifies the cited claims, safety, usefulness, narration flow, content-level originality, and season selection. Editorial issues receive up to two revisions with independent re-review before ImageGen; unresolved factual or safety issues mean skip.
3. Main incorporates review findings and writes `approved.json`. The plan must record the date, season, `topic_strategy`, fallback reason when relevant, title, description, scenes, and sources.
4. Developer makes exactly one new ImageGen storyboard and saves `work/daily/RELEASE-KEY/storyboard.png`. Reused or duplicate art is rejected.
5. The local renderer creates and checks a 720x1280, 15fps video with Korean Edge TTS and one FFmpeg thread.
6. Main audits the generated storyboard, final content, metadata, duration, dimensions, audio, sources, and season decision. Only a complete approval permits upload.
7. `upload_daily.py --date YYYY-MM-DD --slot am|pm` verifies the channel and schedules the private upload for 07:00 or 19:00. The renderer accepts the same slot argument.

Write the final status to `work/mailbox/outbox/RELEASE-KEY.json` and logs to `work/mailbox/runs/RELEASE-KEY/`. The local runner sends the release result email when secure email notifications are configured. Never commit credentials, tokens, videos, or daily work products.

## Comprehension and layout repair

Write spoken_script before splitting scenes; the ordered scene narrations must reproduce it without losing transitions. Use the number of scenes the explanation needs, never force four. Every scene needs visual_action matching its object, state, and instruction. The reviewer must return viewer_recap, scene_count, and transition_checks for every adjacent pair (from_scene, to_scene, clear, evidence quoting actual wording). Do not infer missing steps from the description or sources. Check the complete final on-screen text, not merely legibility.

Before ImageGen, measure the text at the real rendering widths. Reflow and resize within readable limits, then revise long wording or split scenes if needed, up to two revisions with independent review. Never silently truncate words or omit conditions to fit. Generate the grid, narration clips, and audit contact sheet for the resulting scene count. New uploads set containsSyntheticMedia=true.
