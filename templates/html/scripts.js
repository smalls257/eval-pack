// ── helpers ──────────────────────────────────────────────────────────────────

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderMarkdown(text) {
  if (!text) return '';
  const escaped = escapeHtml(text);
  return escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function formatNumber(n) {
  if (n == null) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

function formatDuration(first, last) {
  if (!first || !last) return '—';
  const ms = new Date(last) - new Date(first);
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return mins + 'm';
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return hrs + 'h ' + rem + 'm';
}

function getPhaseColor(label) {
  const map = {
    'user': '#4a90e2',
    'human': '#4a90e2',
    'assistant': '#7c5cbf',
    'tool': '#2ecc71',
    'system': '#95a5a6'
  };
  return map[label] || '#bdc3c7';
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val != null ? val : '—';
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

// ── tab navigation ────────────────────────────────────────────────────────────

let currentPanel = 'summary';

function activatePanel(panelId) {
  currentPanel = panelId;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.panel === panelId);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.style.display = panel.id === 'panel-' + panelId ? '' : 'none';
  });
}

function showAll() {
  document.querySelectorAll('.tab-panel').forEach(p => p.style.display = '');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
}

function focusCurrent() {
  activatePanel(currentPanel);
}

// ── renderers ─────────────────────────────────────────────────────────────────

function renderPageHeader(data, round) {
  const m = round.metrics || {};
  const a = round.analysis || {};
  const title = a.title || data.sessionId || 'Eval Pack';

  setText('page-title', title);
  setText('session-id', data.sessionId || '—');

  // index.html header stat IDs: workspace, messages, files, artifacts
  // Map available round metrics to these slots meaningfully
  setText('header-stat-workspace-value', m.lastModel || '—');
  setText('header-stat-messages-value', m.turnCount != null ? m.turnCount : '—');
  setText('header-stat-files-value', m.filesChanged != null ? m.filesChanged : '—');
  setText('header-stat-artifacts-value', formatNumber(m.totalTokens));

  // Footer timestamp
  const genAt = document.getElementById('generated-at');
  if (genAt && data.generatedAt) {
    genAt.textContent = new Date(data.generatedAt).toLocaleString();
  }
}

function renderVerdict(round) {
  const p = round.patterns || {};
  const flags = p.flags || [];
  const banner = document.getElementById('verdict-banner');
  const icon = document.getElementById('verdict-icon');
  const text = document.getElementById('verdict-text');
  const detail = document.getElementById('verdict-detail');
  if (!banner) return;

  const redFlags = flags.filter(f => f.level === 'red');
  const amberFlags = flags.filter(f => f.level === 'amber');
  const greenFlags = flags.filter(f => f.level === 'green');

  let level, iconChar, summaryText;
  if (redFlags.length > 0) {
    level = 'red';
    iconChar = '✗';
    summaryText = redFlags.map(f => f.label).join(', ');
  } else if (amberFlags.length > 0) {
    level = 'amber';
    iconChar = '△';
    summaryText = amberFlags.map(f => f.label).join(', ');
  } else if (greenFlags.length > 0) {
    level = 'green';
    iconChar = '✓';
    summaryText = greenFlags[0].label;
  } else {
    level = 'green';
    iconChar = '✓';
    summaryText = 'Session complete';
  }

  banner.className = 'verdict-banner verdict-' + level;
  if (icon) icon.textContent = iconChar;
  if (text) text.textContent = summaryText;

  const a = round.analysis || {};
  const highlights = a.highlights || [];
  if (detail && highlights.length > 0) {
    detail.textContent = highlights.join(' · ');
  }
}

function renderStats(round) {
  const m = round.metrics || {};
  const statsRow = document.getElementById('stats-row');
  if (!statsRow) return;
  const stats = [
    { label: 'Model', value: m.lastModel || '—' },
    { label: 'Input tokens', value: formatNumber(m.inputTokens) },
    { label: 'Output tokens', value: formatNumber(m.outputTokens) },
    { label: 'Turns', value: m.turnCount != null ? m.turnCount : '—' },
    { label: 'Files changed', value: m.filesChanged != null ? m.filesChanged : '—' },
    { label: 'Insertions', value: m.insertions != null ? '+' + m.insertions : '—' },
    { label: 'Deletions', value: m.deletions != null ? '-' + m.deletions : '—' }
  ];
  statsRow.innerHTML = stats.map(s =>
    `<div class="stat-card"><div class="stat-value">${escapeHtml(String(s.value))}</div><div class="stat-label">${escapeHtml(s.label)}</div></div>`
  ).join('');
}

function renderTimeline(transcript) {
  const bar = document.getElementById('timeline-bar');
  const legend = document.getElementById('timeline-legend');
  if (!bar || !transcript || transcript.length === 0) return;

  const counts = {};
  transcript.forEach(entry => {
    const role = entry.type || 'unknown';
    counts[role] = (counts[role] || 0) + 1;
  });

  const total = transcript.length;
  const roles = Object.keys(counts);

  bar.innerHTML = roles.map(role => {
    const pct = ((counts[role] / total) * 100).toFixed(1);
    const color = getPhaseColor(role);
    return `<div class="timeline-segment" style="width:${pct}%;background:${color}" title="${escapeHtml(role)}: ${counts[role]}"></div>`;
  }).join('');

  legend.innerHTML = roles.map(role => {
    const color = getPhaseColor(role);
    return `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${escapeHtml(role)} (${counts[role]})</span>`;
  }).join('');
}

function renderFlags(round) {
  const flags = (round.patterns || {}).flags || [];
  const row = document.getElementById('flags-row');
  if (!row) return;
  if (flags.length === 0) {
    row.innerHTML = '<span class="flag flag-green">No issues detected</span>';
    return;
  }
  row.innerHTML = flags.map(f => {
    const count = f.count != null ? ` (${f.count})` : '';
    return `<span class="flag flag-${escapeHtml(f.level)}">${escapeHtml(f.label)}${count}</span>`;
  }).join('');
}

function renderSummary(analysis) {
  const s = analysis.summary || {};

  const whatChanged = document.getElementById('summary-what-changed');
  // index.html uses id="summary-what-proves" (not "summary-proves")
  const proves = document.getElementById('summary-what-proves');
  const notProven = document.getElementById('summary-not-proven');

  const makeList = arr => (arr && arr.length > 0)
    ? '<ul>' + arr.map(item => `<li>${renderMarkdown(item)}</li>`).join('') + '</ul>'
    : '<p class="empty-state">Nothing recorded.</p>';

  if (whatChanged) whatChanged.innerHTML = makeList(s.whatChanged);
  if (proves) proves.innerHTML = makeList(s.whatTranscriptProves);
  if (notProven) notProven.innerHTML = makeList(s.whatNotProven);
}

function renderProof(analysis) {
  const proof = analysis.proof || {};

  // Artifact inventory — index.html has <ul id="artifact-inventory">
  const inv = proof.artifactInventory || {};
  const invEl = document.getElementById('artifact-inventory');
  if (invEl) {
    const items = [
      { label: 'Screenshots', value: inv.screenshots > 0 ? inv.screenshots : null, icon: '📸' },
      { label: 'Video', value: inv.video ? 'Yes' : null, icon: '🎥' },
      { label: 'Transcript', value: inv.transcript ? 'Yes' : null, icon: '📄' },
      { label: 'Terminal output', value: inv.terminalOutput ? 'Yes' : null, icon: '💻' }
    ];
    invEl.innerHTML = items.map(item => {
      const present = item.value != null;
      return `<li class="artifact-item ${present ? 'artifact-present' : 'artifact-absent'}">
        <span class="artifact-icon">${item.icon}</span>
        <span class="artifact-label">${escapeHtml(item.label)}</span>
        <span class="artifact-value">${present ? escapeHtml(String(item.value)) : 'None'}</span>
      </li>`;
    }).join('');
  }

  // Evidence table
  const tbody = document.getElementById('proof-evidence-tbody');
  if (tbody) {
    const rows = proof.evidenceTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No evidence recorded.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        `<tr><td>${renderMarkdown(r.evidencePoint)}</td><td>${renderMarkdown(r.whereItAppeared)}</td><td>${renderMarkdown(r.whyItMatters)}</td></tr>`
      ).join('');
    }
  }

  // High-signal excerpts — index.html has <ul id="proof-excerpts">
  const excerpts = document.getElementById('proof-excerpts');
  if (excerpts) {
    const items = proof.highSignalExcerpts || [];
    if (items.length === 0) {
      excerpts.innerHTML = '<li class="empty-state">No excerpts recorded.</li>';
    } else {
      excerpts.innerHTML = items.map(ex => {
        const role = ex.role || 'unknown';
        return `<li class="excerpt-item excerpt-${escapeHtml(role)}">
          <div class="excerpt-meta">Turn ${escapeHtml(String(ex.turn || ''))} · ${escapeHtml(role)}</div>
          <div class="excerpt-text">${renderMarkdown(ex.text)}</div>
        </li>`;
      }).join('');
    }
  }
}

function renderTestsExisting(analysis) {
  const t = analysis.testsExisting || {};
  const narr = document.getElementById('tests-existing-narrative');
  if (narr) narr.innerHTML = renderMarkdown(t.narrative || '');

  const tbody = document.getElementById('tests-existing-tbody');
  if (tbody) {
    const rows = t.validationTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No validation data.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        `<tr><td>${renderMarkdown(r.validation)}</td><td>${renderMarkdown(r.observedResult)}</td><td>${renderMarkdown(r.interpretation)}</td></tr>`
      ).join('');
    }
  }

  const coveredWell = document.getElementById('tests-covered-well');
  const notCovered = document.getElementById('tests-not-covered');
  const makeList = arr => (arr && arr.length > 0)
    ? '<ul>' + arr.map(item => `<li>${renderMarkdown(item)}</li>`).join('') + '</ul>'
    : '<p class="empty-state">Nothing recorded.</p>';

  if (coveredWell) coveredWell.innerHTML = makeList(t.coveredWell);
  if (notCovered) notCovered.innerHTML = makeList(t.notCovered);
}

function renderTestsNew(analysis) {
  const t = analysis.testsNew || {};
  const narr = document.getElementById('tests-new-narrative');
  if (narr) narr.innerHTML = renderMarkdown(t.narrative || '');

  const list = document.getElementById('tests-new-list');
  if (list) {
    const items = t.list || [];
    if (items.length === 0) {
      list.innerHTML = '<li class="empty-state">No new tests recorded.</li>';
    } else {
      list.innerHTML = items.map(item => `<li>${renderMarkdown(item)}</li>`).join('');
    }
  }
}

function renderFriction(analysis) {
  const tbody = document.getElementById('friction-tbody');
  if (!tbody) return;
  const rows = analysis.frictionLog || [];
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No friction recorded.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r =>
    `<tr>
      <td>${renderMarkdown(r.friction)}</td>
      <td>${renderMarkdown(r.evidence)}</td>
      <td><span class="friction-type friction-${escapeHtml(r.type || '')}">${escapeHtml(r.type || '—')}</span></td>
      <td>${renderMarkdown(r.resolution)}</td>
    </tr>`
  ).join('');
}

function renderDiff(analysis) {
  const diff = analysis.diff || {};

  // Artifact status badges
  const statusEl = document.getElementById('diff-artifact-status');
  if (statusEl) {
    const st = diff.artifactStatus || {};
    const badges = [
      { label: 'Screenshot', key: 'screenshot' },
      { label: 'Video', key: 'video' },
      { label: 'Terminal log', key: 'terminalLog' }
    ];
    statusEl.innerHTML = badges.map(b => {
      const present = st[b.key];
      return `<span class="diff-badge diff-badge-${present ? 'present' : 'absent'}">${escapeHtml(b.label)}: ${present ? 'Yes' : 'No'}</span>`;
    }).join('');
  }

  // Files changed list
  const filesEl = document.getElementById('diff-files-changed');
  if (filesEl) {
    const files = diff.filesChanged || [];
    if (files.length === 0) {
      filesEl.innerHTML = '<li class="empty-state">No files recorded.</li>';
    } else {
      filesEl.innerHTML = files.map(f => `<li><code>${escapeHtml(f)}</code></li>`).join('');
    }
  }

  // Change table
  const tbody = document.getElementById('diff-change-tbody');
  if (tbody) {
    const rows = diff.changeTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No changes recorded.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        `<tr><td>${renderMarkdown(r.area)}</td><td>${renderMarkdown(r.evidence)}</td><td>${renderMarkdown(r.observedEffect)}</td></tr>`
      ).join('');
    }
  }

  // Representative commands
  const cmds = document.getElementById('diff-commands');
  if (cmds) {
    const commands = diff.representativeCommands || [];
    if (commands.length === 0) {
      cmds.textContent = '# No commands recorded';
    } else {
      cmds.textContent = commands.join('\n');
    }
  }
}

function renderImprovements(analysis) {
  const repoEl = document.getElementById('repo-improvements-list');
  if (repoEl) {
    const items = analysis.repoImprovements || [];
    repoEl.innerHTML = items.length > 0
      ? items.map(item => `<li>${renderMarkdown(item)}</li>`).join('')
      : '<li class="empty-state">No improvements recorded.</li>';
  }

  const userEl = document.getElementById('user-improvements-list');
  if (userEl) {
    const items = analysis.userImprovements || [];
    userEl.innerHTML = items.length > 0
      ? items.map(item => `<li>${renderMarkdown(item)}</li>`).join('')
      : '<li class="empty-state">No improvements recorded.</li>';
  }
}

function renderPromptPattern(analysis) {
  const area = document.getElementById('prompt-pattern-area');
  const pre = document.getElementById('prompt-pattern');
  if (area && analysis.promptPattern) {
    area.style.display = 'block';
    if (pre) pre.textContent = analysis.promptPattern;
  } else if (area) {
    area.style.display = 'none';
  }
}

function renderSessionArtifacts(analysis) {
  const list = document.getElementById('session-artifacts-list');
  if (!list) return;
  const items = analysis.sessionArtifacts || [];
  if (items.length === 0) {
    list.innerHTML = '<li class="empty-state">No artifacts recorded.</li>';
    return;
  }
  list.innerHTML = items.map(item => {
    if (item.path) {
      return `<li><a href="${escapeHtml(item.path)}" target="_blank">${escapeHtml(item.label || item.path)}</a></li>`;
    }
    return `<li>${escapeHtml(item.label || String(item))}</li>`;
  }).join('');
}

function renderVerdictStatement(analysis) {
  const card = document.getElementById('verdict-statement-card');
  const el = document.getElementById('verdict-statement');
  if (!card || !el) return;
  if (analysis.verdictStatement) {
    card.style.display = 'block';
    el.innerHTML = renderMarkdown(analysis.verdictStatement);
  } else {
    card.style.display = 'none';
  }
}

function renderTranscript(transcript) {
  const container = document.getElementById('transcript-container');
  if (!container) return;
  if (!transcript || transcript.length === 0) {
    container.innerHTML = '<p class="empty-state">No transcript available.</p>';
    return;
  }

  container.innerHTML = transcript.map(entry => {
    const role = entry.type || 'unknown';
    const msg = entry.message || {};
    let content = '';

    if (typeof msg.content === 'string') {
      content = msg.content;
    } else if (Array.isArray(msg.content)) {
      content = msg.content
        .filter(block => block.type === 'text')
        .map(block => block.text || '')
        .join('\n');
    } else if (typeof entry.content === 'string') {
      content = entry.content;
    }

    const usage = msg.usage || entry.usage || {};
    const usageLine = (usage.input_tokens || usage.output_tokens)
      ? `<div class="transcript-usage">${usage.input_tokens || 0} in / ${usage.output_tokens || 0} out</div>`
      : '';

    const ts = entry.timestamp
      ? `<span class="transcript-ts">${new Date(entry.timestamp).toLocaleTimeString()}</span>`
      : '';

    return `<div class="transcript-entry transcript-${escapeHtml(role)}">
      <div class="transcript-header">
        <span class="transcript-role">${escapeHtml(role)}</span>
        ${ts}
        ${usageLine}
      </div>
      <div class="transcript-body">${renderMarkdown(content)}</div>
    </div>`;
  }).join('');
}

function renderRounds(data) {
  const section = document.getElementById('rounds-section');
  const nav = document.getElementById('rounds-nav');
  if (!section || !nav || !data.rounds || data.rounds.length <= 1) {
    if (section) section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  nav.innerHTML = data.rounds.map((r, i) => {
    const label = r.generatedAt ? new Date(r.generatedAt).toLocaleString() : 'Round ' + (i + 1);
    return `<button class="round-btn${i === data.rounds.length - 1 ? ' active' : ''}" data-round="${i}">${escapeHtml(label)}</button>`;
  }).join('');

  nav.querySelectorAll('.round-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.round, 10);
      nav.querySelectorAll('.round-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderRound(data, data.rounds[idx]);
    });
  });
}

// ── main render ───────────────────────────────────────────────────────────────

function renderRound(data, round) {
  const analysis = round.analysis || {};

  renderPageHeader(data, round);
  renderVerdict(round);
  renderStats(round);
  renderFlags(round);
  renderSummary(analysis);
  renderProof(analysis);
  renderTestsExisting(analysis);
  renderTestsNew(analysis);
  renderFriction(analysis);
  renderDiff(analysis);
  renderImprovements(analysis);
  renderPromptPattern(analysis);
  renderSessionArtifacts(analysis);
  renderVerdictStatement(analysis);
  renderTimeline(data.transcript);
}

function init(data) {
  const rounds = data.rounds || [];
  const latestRound = rounds.length > 0 ? rounds[rounds.length - 1] : {};

  renderRound(data, latestRound);
  renderTranscript(data.transcript);
  renderRounds(data);

  // Tab navigation
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => activatePanel(btn.dataset.panel));
  });

  const showAllBtn = document.getElementById('btn-show-all');
  if (showAllBtn) showAllBtn.addEventListener('click', showAll);

  const focusBtn = document.getElementById('btn-focus-current');
  if (focusBtn) focusBtn.addEventListener('click', focusCurrent);

  // Theme toggle — persist selection in localStorage
  const themeToggle = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('eval-pack-theme');
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const html = document.documentElement;
      const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
      html.dataset.theme = next;
      localStorage.setItem('eval-pack-theme', next);
    });
  }

  // Activate default panel
  activatePanel('summary');
}

// ── bootstrap ─────────────────────────────────────────────────────────────────

fetch('data.json')
  .then(r => r.json())
  .then(init)
  .catch(err => {
    document.body.innerHTML = `<div style="padding:2rem;font-family:monospace;color:#e74c3c">
      <h2>Failed to load eval pack data</h2>
      <p>${escapeHtml(String(err))}</p>
      <p>Serve this directory over HTTP: <code>python3 -m http.server 8080</code></p>
    </div>`;
  });
