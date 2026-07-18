# Latent Arch marketplace for Claude Code

Plugins for [Claude Code](https://claude.com/claude-code) by [Latent Arch](https://latent-arch.com/): practical skills we use daily, packaged so you can install them in two commands.

## Quick start

In any Claude Code session:

```
/plugin marketplace add latent-arch/claude-marketplace
/plugin install la-toolkit@latent-arch
```

That's it. The skills are now available as `/la-toolkit:<skill-name>` slash commands, and Claude also picks them up automatically when your request matches what a skill does.

## What's inside

### `la-toolkit` — general-purpose toolkit

| Skill | What it does |
|-------|--------------|
| `meeting` | Meeting minutes, end to end. `plan` drafts an agenda file before the meeting; `protocol` transcribes a recording **locally** (faster-whisper — audio never leaves your machine) and turns it into structured minutes: decisions, action items, open questions. Works in your language. |

Try it:

```
/la-toolkit:meeting plan sync with the team about Q3 roadmap, tomorrow
/la-toolkit:meeting protocol standup 18.07.2026.webm
```

Or just say "make minutes from this recording" — the skill triggers on its own.

> **Note on transcription:** the first `protocol` run sets up a local Python environment and downloads a ~3 GB Whisper model, so it takes a while. Subsequent runs are much faster.

## Using a skill on claude.ai (web / desktop)

Skills also work outside Claude Code: zip a skill folder (the folder itself at the archive root, e.g. `meeting/`) and upload it via **Settings → Capabilities → Skills → Upload**.

## Feedback

Found a bug or have an idea for a skill? [Open an issue](https://github.com/latent-arch/claude-marketplace/issues) — happy to hear from you.

---

Curious how these skills are born and used in real work? We write about agentic engineering, Claude Code workflows and building things solo-with-agents on the [Latent Arch blog](https://latent-arch.com/) — come say hi. 👋
