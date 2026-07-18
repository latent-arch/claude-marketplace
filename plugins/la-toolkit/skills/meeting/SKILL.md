---
name: meeting
description: Meeting minutes in the repo's meetings/ folder. Mode plan — agenda draft before the meeting; mode protocol — local transcription of an audio/video recording (faster-whisper, incl. Telemost .webm) and assembly of the minutes. Documents are written in the user's working language (any language). Trigger on "meeting minutes", "meeting notes", "agenda", "transcribe the recording", and equivalents in other languages («протокол встречи», «повестка», «транскрибируй запись»).
---

# Meeting minutes

Two modes; **the first token of `$ARGUMENTS` is the mode**: `plan` (before the meeting)
or `protocol` (after). Empty or anything else — don't guess: show both forms
(`plan <details>`, `protocol <recording> [minutes-file.md]`) and ask.

Conventions (the `meetings/` folder, file naming, the `meeting-note` template) and the
script reference are in [reference.md](reference.md). Tooling is a single script that
sets up its own environment:

```bash
${CLAUDE_SKILL_DIR}/scripts/meeting.py transcribe <recording>   # recording → transcript
${CLAUDE_SKILL_DIR}/scripts/meeting.py lint <minutes.md>        # frontmatter check
```

**Working language.** All generated documents — agenda, minutes, `meetings/README.md`,
the index — are written in the repo's working language for meetings, which can be any
language (e.g. Russian). Resolve it in this order: language of the existing
`meetings/README.md` → explicit user request → the language the user communicates in.
Regardless of the language: frontmatter stays exactly as in the template (English field
names and enum values — it is machine-checked by `lint`), file names and slugs are Latin
kebab-case.

**Before either mode:** if the repo has no `meetings/README.md` — first deploy the
convention per the "First-time initialization" section in reference.md (README with the
template and index + .gitignore), rendered in the working language. After that, the
template in `meetings/README.md` is the canonical one for this repo — use it, not the
English sample from reference.md.

Never commit anything in either mode — only on a separate explicit user request.

## `plan` mode — draft before the meeting

Conversational planning, run it yourself (not a subagent). The result is a file with
`status: planned`: agenda and goals filled in, content sections empty (the `protocol`
mode will fill them later).

1. **Collect details** from the arguments + ask for what's missing: topic/goal;
   `meeting_type` (`tech`|`product`); `date` (today by default); participants; agenda
   items; questions to discuss; `related` (suggest from the repo contents yourself,
   otherwise `[]`). If details are scarce — propose an agenda yourself from the topic
   and context, let the user correct it.
2. **Slug and file name**: `meetings/YYYY-MM-DD-<meeting_type>-<slug>.md`. If the file
   already exists — ask whether to extend the existing one.
3. **Create the draft** from the repo's template with `status: planned`. Frontmatter —
   complete. In the body: Agenda and Goals filled in; Discussion and Decisions — a
   placeholder like _(to be filled from the transcript after the meeting)_ in the
   working language; Action items — empty table; Open questions — from step 1.
4. **Lint and index**: run `lint` until green; add a row to the meetings index in
   `meetings/README.md` with status `planned`.
5. **Hand over for review**: show the draft and its path; remind that after the meeting
   `protocol <recording> <this-file.md>` will fill it in and flip it to `final`.

## `protocol` mode — minutes from a recording

Pipeline: recording → transcript (script) → minutes (you). No diarization: the
transcript has no speaker labels; attribute utterances via the participant roster and
context.

1. **Parse the arguments** (recording names contain spaces — don't split naively): the
   argument ending in `.md` is the minutes file (optional), everything else is the
   recording.
   - Recording: normally lives in `meetings/.audio/`; an explicit path is fine. If the
     file is missing — ask to put it there and stop.
   - Minutes file: use the path as given, else `meetings/<name>`, else search by
     basename under `meetings/`; ambiguous/not found — ask, don't create silently.
2. **Transcribe**: `${CLAUDE_SKILL_DIR}/scripts/meeting.py transcribe <recording-path>`.
   The language is auto-detected; pass `--language xx` if it's known upfront (skips
   detection and avoids misdetection on noisy audio). The first run is long (venv +
   ~3 GB model); on CPU an hour-long meeting takes tens of minutes, so run it **in the
   background** and wait for completion. The transcript appears in
   `meetings/.transcripts/<recording-name>.md`.
3. **Read the transcript, build the roster**: participants — from the minutes file
   (`participants`) or ask. Attribute utterances/tasks by context; where unclear —
   don't invent an author, record it as an open question.
4. **Fill in the minutes** (in the working language):
   - *File given* — extend it in place: keep Agenda/Goals, fill Discussion, Decisions,
     Action items (who/what/due), update Open questions; compare the agenda against
     what actually happened (what was covered, what to carry over);
     `status: planned` → `final`.
   - *No file given* — create a new one: ask for `meeting_type`, `date` (default from
     the recording name `DD.MM.YYYY`, else today), `slug`, `related`; complete
     frontmatter with `status: final`.
   Write substance, don't retell verbatim.
5. **Lint and index**: `lint` until green; update/add the row in the meetings index
   with status `final`.
6. **Hand over for review**: show the minutes and the path. The recording and the raw
   transcript stay in gitignored folders — only the minutes go into git.
