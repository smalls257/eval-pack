# user-improvements (Developer Ownership) — evaluation basis

Judges how well the DEVELOPER owned intent, decisions, and risk-proportional due diligence versus offloaded judgment to the AI (vibecoding). HIGH = dev drives, AI executes. Fixtures: a real MIT Claude Code session where the dev vets the AI's diagnosis and owns an auth fix (HIGH), a 943-turn ccexport Claude Code session where the dev drives intent/decisions/risk while the AI executes (HIGH, `marc-big`), a daaain/claude-code-log MIT session where the dev front-loads sharp evidence-backed asks but accepts some AI output unscrutinized (MEDIUM, `coderabbit-review`), a WildChat 'make my login better' auth rewrite with no security concern (LOW, risky), a single-turn 'search + summarize' offload (LOW), and a WildChat 'act as a python expert' vibecoding session that offloads judgment (LOW, `vibe-2`).

**Fairness:** rubber-ducking/discovery is engaged ownership, not an offload (see the rubber-ducking-is-fine claim + the HIGH fixture's exploratory turns). **Provenance caveat:** the single source is an internal design principle (vibecoding), not an external citation; the offline gate checks basis<->ledger title agreement.

```json
{
  "sources": [
    {
      "id": "vibecoding-decay",
      "citation": "eval-pack design principle",
      "title": "Vibecoding: offloading engineering judgment to the AI"
    }
  ],
  "claims": [
    {
      "id": "vetting-is-ownership",
      "statement": "A developer who challenges the AI's claims, demands verification/supporting evidence, and does not take output at face value owns the cognitive load; rubber-stamping offloads it.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "dev-owned-deploy-auth",
        "vibecoded-auth-rewrite",
        "marc-big",
        "coderabbit-review"
      ]
    },
    {
      "id": "rubber-ducking-is-fine",
      "statement": "Rubber-ducking and discovery WITH the AI (exploring options, thinking out loud, learning) while staying engaged and owning the conclusion is healthy collaboration, NOT weak ownership \u2014 it must not be flagged as an offload.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "dev-owned-deploy-auth",
        "marc-big"
      ]
    },
    {
      "id": "skipped-due-diligence-on-risk",
      "statement": "Shipping a change that touches a sensitive domain (auth/credentials) without raising the security/review consideration is an offloaded judgment \u2014 the deepest kind.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "vibecoded-auth-rewrite",
        "vibecoded-research-offload",
        "vibe-2"
      ]
    }
  ],
  "rules": [
    {
      "when": {
        "level": "high"
      },
      "require": {
        "findings.types": {
          "at_least_one_in": [
            "strength"
          ]
        }
      }
    }
  ]
}
```
