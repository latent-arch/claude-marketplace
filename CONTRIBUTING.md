# Contributing

## Repository layout

```
.claude-plugin/marketplace.json          — marketplace catalog (list of plugins)
plugins/
└── la-toolkit/                          — plugin (general-purpose toolkit)
    ├── .claude-plugin/plugin.json       — plugin manifest
    └── skills/
        └── <skill-name>/SKILL.md        — the skill (+ reference.md, scripts/, etc.)
```

## Adding a new skill

1. Create `plugins/la-toolkit/skills/<name>/SKILL.md` — frontmatter with `name` and `description` (the description drives auto-invocation), the body holds the instructions for Claude. Move details into sibling files (`reference.md`, `scripts/`).
2. Check: `claude plugin validate .`
3. Commit and push.
