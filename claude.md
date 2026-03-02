You are a senior AI/ML + full-stack engineer. Build an “agentic” production system that automatically creates and posts ONE children-themed, faceless TikTok video daily.

GOALS
1) Research: find trending children-friendly topics daily (age-appropriate, safe, non-violent, no scary content).
2) Create: generate an engaging script, storyboard, voiceover, visuals, music, captions, and final vertical video.
3) Publish: post the video to TikTok daily (prefer official/approved methods; otherwise prepare an upload-ready package and optionally integrate a scheduler).
4) Compliance: enforce safety and platform policy constraints; avoid copyrighted media and disallowed content.

NON-NEGOTIABLE REQUIREMENTS
- Output is “faceless”: no human face footage. Use illustrations, animations, stock clips, shapes, toys, animal cartoons, simple motion graphics, text-on-screen, etc.
- Children-themed and age-appropriate. No content that targets kids with unsafe instructions or mature themes.
- Use only properly licensed assets OR generate them with AI. Never scrape copyrighted audio/video and reuse it.
- Implement a moderation gate that blocks unsafe topics, sexual content, violence/gore, or sensitive personal data.
- System runs daily on a schedule and produces logs + artifacts for auditing.

SYSTEM OVERVIEW
Build a modular, agentic pipeline with:
A) Trend Research Agent
B) Topic Selection + Safety Filter Agent
C) Scriptwriting Agent
D) Storyboard/Shotlist Agent
E) Asset Generation Agents (visuals, voiceover, background music)
F) Video Assembly Agent
G) Metadata Agent (caption, hashtags, thumbnail)
H) QA/Moderation Agent (policy checks + heuristics)
I) Publishing Agent (TikTok upload or export package)
J) Orchestrator + Storage + Observability

TECH STACK (suggested, but you can choose equivalents)
- Python backend (FastAPI) + Celery/Redis (or Temporal) for orchestration
- Postgres for metadata + S3-compatible storage for artifacts
- Dockerized services
- A small React admin dashboard for review/override (optional but recommended)
- Use OpenAI (or equivalent) models for text + optional image generation
- Use ffmpeg / moviepy for video assembly
- Use TTS (e.g., ElevenLabs/Azure/Google) or OpenAI audio models for voiceover (configurable)
- Use a royalty-free music provider API or generate music with a licensed model; or include “no-music” mode

DELIVERABLES
1) A repo with clear modules:
   /agents
   /pipelines
   /services (tts, image_gen, music_gen, tiktok_publish, trends, moderation)
   /storage
   /configs
   /tests
2) A CLI command: `python -m app.run_daily`
3) A scheduler config (cron or workflow) that triggers once per day.
4) A `.env.example` file with keys and toggles.
5) Documentation: architecture, setup, how to add new themes, how to change posting time.
6) Unit tests for topic filtering, script formatting, and video assembly.

FUNCTIONAL SPEC
1) Trend Research Agent
- Inputs: date, region (default: US, also configurable), target age band (e.g., 4–10)
- Sources (choose 2–4 with redundancy):
  - Google Trends (kids-friendly queries)
  - YouTube trending kids category (if accessible)
  - TikTok Creative Center / trends endpoints (if available)
  - General news/entertainment trend feeds that can be filtered
- Output: list of candidate topics with scores:
  - trend_score, kid_score, educational_score, novelty_score, risk_score
- Store all raw findings + citations/links.

2) Topic Selection + Safety Filter
- Apply hard filters:
  - No dangerous challenges, no medical claims, no personal data, no violence/scares, no mature content.
  - No brands that imply endorsement unless explicitly allowed.
- Pick one topic daily using weighted scoring + diversity (avoid repeating same topic category >2 times/week).
- Output: selected_topic + rationale + safety_report.

3) Scriptwriting Agent (children-themed)
- Generate:
  - Hook (first 1–2 seconds), simple narration, playful tone, short sentences
  - Call-and-response (“Can you guess…?”), fun facts, mini quiz, or story
  - Length target: 25–40 seconds
- Output format (STRICT JSON):
  {
    "title": "...",
    "age_band": "4-10",
    "topic": "...",
    "narration": [{"t":0.0,"text":"..."}, ...],
    "on_screen_text": [{"t":0.0,"text":"..."}],
    "sound_effects": [{"t":...,"type":"pop|ding|whoosh"}],
    "visual_style": "cartoon|paper-cut|3d-toy|whiteboard",
    "cta": "..."
  }
- Add a “pronunciation hints” field for tricky words.

4) Storyboard/Shotlist Agent
- Convert script JSON into shot plan:
  - Each shot includes duration, camera motion (pan/zoom), background, characters/objects, text overlays, transitions
- Ensure visuals are faceless and safe (cartoons, animals, objects).
- Output (STRICT JSON) with a list of shots.

5) Asset Generation
A) Visual generation:
- Option 1: AI images per shot (consistent style) then animate via simple motion (Ken Burns)
- Option 2: Template-based motion graphics using SVG/Lottie assets
- Must include a style lock: same palette + character design across video
- Cache reusable assets (mascot character, backgrounds, frames)

B) Voiceover generation (TTS):
- Child-friendly narrator voice (not impersonating a real person)
- Pace aligned to shot durations

C) Music and SFX:
- Royalty-free or generated music; keep volume low under voice
- Add simple SFX for engagement (ding/pop/whoosh), generated or licensed

6) Video Assembly Agent
- Compose 9:16 video 1080x1920, 30fps
- Burn-in captions (large, readable, high contrast), with word highlighting optional
- Add intro/outro bumper (1s each) with channel mascot
- Output MP4 H.264 + AAC audio
- Generate a thumbnail (cover image) with big text

7) QA/Moderation Agent
- Validate:
  - No disallowed content (run content moderation on text)
  - No copyrighted music fingerprints (if using external audio, ensure licensing)
  - Captions not too small; audio levels normalized
  - Duration 15–60s, ideal 25–40s
- If fails: automatically revise topic/script once; otherwise escalate to “needs review”.

8) Metadata Agent
- Generate caption:
  - Short, fun, emoji-light
  - 3–6 relevant hashtags (kid-safe, broad + niche)
- Avoid “#fyp” spam unless you choose; keep it authentic.
- Output: caption, hashtags, keywords, alt text.

9) Publishing Agent
- Implement “Publishing Modes”:
  MODE_A (Official): If TikTok API posting is available & configured, upload and publish.
  MODE_B (Scheduler): push to approved scheduler (if user provides).
  MODE_C (Manual): export a folder with:
     final.mp4, thumbnail.jpg, caption.txt, hashtags.txt, metadata.json
     and mark in DB “READY_TO_POST”.
- Always store the final artifact and publishing status.

10) Orchestrator + State
- Maintain DB tables:
  runs, topics, scripts, storyboards, assets, videos, publish_jobs, errors
- Each daily run is idempotent: re-running does not duplicate posts.
- Add retries with backoff and a dead-letter queue.

CONFIGURATION
Provide env toggles:
- REGION, POST_TIME, AGE_BAND
- VISUAL_STYLE (cartoon/paper-cut/3d-toy)
- VOICE_PROVIDER, VOICE_ID
- MUSIC_MODE (none/royalty_free/generated)
- PUBLISH_MODE (A/B/C)
- SAFETY_STRICTNESS (low/med/high)
- COST_LIMIT_PER_DAY (hard cap)

OBSERVABILITY
- Structured logs with run_id
- Save intermediate artifacts for debugging
- Metrics: time per stage, cost estimates, success rate
- Notifications (email/Slack webhook) on failure

SECURITY
- Keep API keys in secret manager or env vars
- Do not log secrets
- Rate limit external calls
- Validate all downloaded/trending source content

IMPLEMENTATION PLAN
- Step 1: Define data models + storage + orchestrator skeleton
- Step 2: Implement trend research + topic selection
- Step 3: Script + storyboard generation with strict JSON schemas + validation
- Step 4: Asset generation (start with template visuals + TTS)
- Step 5: Video assembly with ffmpeg/moviepy
- Step 6: QA/moderation gate
- Step 7: Publishing in MODE_C first (manual export), then add MODE_A if feasible
- Step 8: Add dashboard and tests

OUTPUT EXPECTATIONS
- Provide the full folder structure and key files with code.
- Provide runnable Docker Compose.
- Provide at least one working example run that generates a sample children-themed faceless video locally (MODE_C).
- Include clear instructions for adding new series formats:
  (e.g., “Guess the Animal Sound”, “Space Fun Facts”, “Math Magic Trick”, “Alphabet Adventure”).

CONSTRAINTS
- Avoid any solution that relies on scraping TikTok in ways that violate ToS.
- Do not include code that automates a consumer web browser login unless user explicitly requests it and it’s compliant.
- Keep everything modular so each agent can be swapped/replaced.