# user-improvements (Developer Ownership) — evaluation basis

Judges how well the DEVELOPER owned intent, decisions, and risk-proportional due diligence versus offloaded judgment to the AI (vibecoding). HIGH = dev drives, AI executes. Fixtures: a real MIT Claude Code session where the dev vets the AI's diagnosis and owns an auth fix (HIGH), a 943-turn ccexport Claude Code session where the dev drives intent/decisions/risk while the AI executes (HIGH, `marc-big`), a daaain/claude-code-log MIT session where the dev front-loads sharp evidence-backed asks but accepts some AI output unscrutinized (MEDIUM, `coderabbit-review`), a WildChat 'make my login better' auth rewrite with no security concern (LOW, risky), a single-turn 'search + summarize' offload (LOW), and a WildChat 'act as a python expert' vibecoding session that offloads judgment (LOW, `vibe-2`). Plus two SYNTHETIC marker fixtures (purpose-built, not real sessions; see each `meta.json`): `arbiter-offload-verbatim` (LOW — every decision, incl. an auth/ownership boundary, accepted verbatim: "ok, do it", "sure, go ahead", "whatever you think", "ship it") and `comprehension-gap` (MEDIUM — the dev owns intent but ships a log-format change while asking whether it affects unrelated webhook/invoice subsystems, taking the AI's answer on trust). A third, `review-delegation-knowledge-gap` (MEDIUM), pins the two most-missed signals: the developer offloads the whether-a-code-review-is-needed decision AND has the authoring AI review its own change, while asking basic questions about the auth code being changed — intent is owned (one strength) but the whole due-diligence chain is offloaded. These pin the arbiter-test, comprehension, and review-necessity signals so the gate regression-locks them.

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
    },
    {
      "id": "arbiter-offload-is-offload",
      "statement": "Asking the AI to make or recommend a decision (whether a check is needed, which option, is it done, is it safe) and accepting its answer verbatim with no independent rationale — 'ok', 'sure', 'go ahead', 'whatever you think' — is an arbiter offload; ownership means engaging the answer: own reasoning, modifying it, choosing against it, or justifying the pick.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "arbiter-offload-verbatim"
      ]
    },
    {
      "id": "comprehension-is-ownership",
      "statement": "The developer must understand the change they ship; a question that reveals a basic misunderstanding of the part of the system being changed, taken on the AI's word and shipped, is an offload of comprehension — distinct from learning an unfamiliar area in order to own the change.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "comprehension-gap"
      ]
    },
    {
      "id": "review-necessity-is-ownership",
      "statement": "Deciding whether a change warrants review/QA is the developer's judgment; asking the AI whether a review is needed and acting on its answer offloads it — even if a review then happens — and a review performed by the author (the AI that wrote the code) is not an independent second set of eyes. Basic questions clustering around the code being changed are a possible comprehension/ownership gap that must be surfaced, not left silent.",
      "sources": [
        "vibecoding-decay"
      ],
      "covers": [
        "review-delegation-knowledge-gap"
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
