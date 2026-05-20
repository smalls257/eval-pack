#!/usr/bin/env python3

# Scope drift: monorepo PRs typically touch <10 files; beyond this suggests task bleed
SCOPE_DRIFT_FILE_THRESHOLD = 10

# Retry amber flag: >3 retries indicates repeated misunderstanding, not normal course-correction
RETRY_AMBER_THRESHOLD = 3

# Skill args truncation: keeps tools.json readable without losing functional context
SKILL_ARGS_MAX_LEN = 200
