# Skill Registry — mid

Generated: 2026-05-28
Source: sdd-init
Scope: user-level skills (no project-level skills found)

## Registry Contract

- This file is an **index** only. Each skill's `SKILL.md` is the source of truth.
- Subagents receive exact paths and read the full skill.
- Skip `sdd-*`, `_shared`, and `skill-registry` skills (SDD skills are invoked by the orchestrator, not directly).
- Deduplication: first source in scan order wins. Scan order follows the init-details reference.

## Indexed Skills

| Skill | Trigger / Description | Path | Scope |
|---|---|---|---|
| find-skills | Helps users discover and install agent skills | `C:\Users\ezepr\.agents\skills\find-skills\SKILL.md` | user |
| branch-pr | Create Gentle AI pull requests with issue-first checks. Trigger: creating, opening, or preparing PRs for review. | `C:\Users\ezepr\.config\opencode\skills\branch-pr\SKILL.md` | user |
| chained-pr | Trigger: PRs over 400 lines, stacked PRs, review slices. Split oversized changes into chained PRs that protect review focus. | `C:\Users\ezepr\.config\opencode\skills\chained-pr\SKILL.md` | user |
| cognitive-doc-design | Design docs that reduce cognitive load. Trigger: writing guides, READMEs, RFCs, onboarding, architecture, or review-facing docs. | `C:\Users\ezepr\.config\opencode\skills\cognitive-doc-design\SKILL.md` | user |
| comment-writer | Write warm, direct collaboration comments. Trigger: PR feedback, issue replies, reviews, Slack messages, or GitHub comments. | `C:\Users\ezepr\.config\opencode\skills\comment-writer\SKILL.md` | user |
| go-testing | Trigger: Go tests, go test coverage, Bubbletea teatest, golden files. Apply focused Go testing patterns. | `C:\Users\ezepr\.config\opencode\skills\go-testing\SKILL.md` | user |
| issue-creation | Create Gentle AI issues with issue-first checks. Trigger: creating GitHub issues, bug reports, or feature requests. | `C:\Users\ezepr\.config\opencode\skills\issue-creation\SKILL.md` | user |
| judgment-day | Trigger: judgment day, dual review, adversarial review, juzgar. Run blind dual review, fix confirmed issues, then re-judge. | `C:\Users\ezepr\.config\opencode\skills\judgment-day\SKILL.md` | user |
| skill-creator | Trigger: new skills, agent instructions, documenting AI usage patterns. Create LLM-first skills with valid frontmatter. | `C:\Users\ezepr\.config\opencode\skills\skill-creator\SKILL.md` | user |
| skill-improver | Trigger: improve skills, audit skills, refactor skills, skill quality. Audit and upgrade existing LLM-first skills. | `C:\Users\ezepr\.config\opencode\skills\skill-improver\SKILL.md` | user |
| work-unit-commits | Plan commits as reviewable work units. Trigger: implementation, commit splitting, chained PRs, or keeping tests and docs with code. | `C:\Users\ezepr\.config\opencode\skills\work-unit-commits\SKILL.md` | user |

## Convention Files

No convention files (AGENTS.md, CLAUDE.md, .cursorrules, etc.) found at project root.

## Notes

- 11 non-excluded skills indexed (22 total installed, 11 excluded: 7 SDD, _shared, skill-registry, and 3 duplicates from other agent dirs).
- No project-level skills found — all indexed skills are user-global.
- Cache: freshly generated (first init).
