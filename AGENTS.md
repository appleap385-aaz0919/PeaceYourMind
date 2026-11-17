# Korean video narration

Before selecting household-tip topics for `youtube_life_tips`, read its [editorial brief](youtube_life_tips/EDITORIAL_BRIEF.md). It records the user's accepted content patterns, rejected subjects, and the required discovery process.

When drafting or revising Korean video narration in this repository, read and apply the project-local [humanize-korean skill](.agents/skills/humanize-korean/SKILL.md) from im-not-ai. Its installation and updates belong in this repository's `.agents/skills/` directory.

Establish one clear takeaway and a logical explanation in a source-checked continuous draft first. Apply the skill's single-call style pass to that draft before splitting it into scenes, then recheck meaning, factual conditions, sentence connections, and spoken Korean. Structural rewriting and factual corrections belong before the style pass; the skill preserves the draft's facts and claims.

Keep the skill's diagnostics and summary outside narration and captions. Preserve the JSON schema in automated stages. When the user asks to see a script, show the complete narration inline.

# Project-local video skills

For new `youtube_life_tips` videos, use the accepted AI-photorealistic hands-and-work demonstration style described in its editorial brief for both manual and scheduled production. Keep PIM production, assets, credentials, and settings unchanged. Preview servers are opt-in; after production, stop only the exact server session started for this project, verifying its identity and exit without touching another project's server.

When using Remotion or HyperFrames to author, preview, render, or update video compositions, first read [the project video-skill policy](youtube_life_tips/VIDEO_SKILLS.md). It defines the local skill entry points, renderer scope, and overrides to upstream service and export defaults. Install and update these skills only under this repository's `.agents/skills/`; keep all user-level skill and plugin directories unchanged.
