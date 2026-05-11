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

const COST_RATES_DATE = '2026-05-11';

function modelRates(model) {
  const m = (model || '').toLowerCase();
  if (m.includes('opus'))  return { inRate: 15,   outRate: 75 };
  if (m.includes('haiku')) return { inRate: 0.80, outRate: 4  };
  return                          { inRate: 3,    outRate: 15 }; // sonnet
}

function estimateCost(model, inputTokens, outputTokens) {
  const r = modelRates(model);
  const cost = (
    (inputTokens  || 0) * r.inRate  +
    (outputTokens || 0) * r.outRate
  ) / 1_000_000;
  return cost > 0 ? cost : null;
}

// Subagent usage tags only report total_tokens with no cache breakdown.
// Assume 90% input / 10% output — agentic workloads are input-heavy.
function estimateSubagentCost(model, totalTokens) {
  if (!totalTokens) return null;
  const r = modelRates(model);
  const blended = r.inRate * 0.9 + r.outRate * 0.1;
  return (totalTokens * blended) / 1_000_000;
}

function formatCost(n) {
  if (n == null || n <= 0) return '—';
  return (n >= 0.01 ? '$' + n.toFixed(2) : '$' + n.toFixed(4)) + '*';
}

function shortModelName(model) {
  if (!model) return 'unknown';
  const m = model.toLowerCase();
  if (m.includes('opus'))  return 'Opus';
  if (m.includes('haiku')) return 'Haiku';
  if (m.includes('sonnet')) return 'Sonnet';
  return model;
}

function formatNumber(n) {
  if (n == null) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}



function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val != null ? val : '—';
}


// ── tab navigation ────────────────────────────────────────────────────────────

let currentPanel = 'summary';

function activatePanel(panelId) {
  currentPanel = panelId;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const isActive = btn.dataset.panel === panelId;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
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

  // Summary subtitle — verdictStatement as deck text
  const summaryEl = document.getElementById('page-summary');
  if (summaryEl) summaryEl.textContent = a.verdictStatement || '';

  setText('header-stat-workspace-value', m.lastModel || '—');
  setText('header-stat-messages-value', m.turnCount != null ? m.turnCount : '—');
  setText('header-stat-files-value', m.filesChanged != null ? m.filesChanged : '—');
  setText('header-stat-tokens-value', formatNumber(m.totalTokens));
  setText('header-stat-branch-value', round.gitBranch || '—');

  const genAt = document.getElementById('generated-at');
  if (genAt && data.generatedAt) {
    genAt.textContent = new Date(data.generatedAt).toLocaleString();
  }
}

function renderHighlights(analysis) {
  const h = (analysis || {}).highlights || {};
  const cs = h.completionStatus || {};
  const risk = h.mainRisk || '';

  // Completion card
  const card = document.getElementById('completion-card');
  const val = document.getElementById('completion-value');
  const notes = document.getElementById('completion-notes');
  if (card && cs.label) {
    const color = /^(green|amber|red)$/.test(cs.color || '') ? cs.color : 'green';
    card.className = `highlight-card completion-card completion-${color}`;
    if (val) val.innerHTML = `<span class="completion-dot"></span>${escapeHtml(cs.label)}`;
    if (notes) notes.textContent = cs.notes || '';
  }

  // Risk card
  const riskVal = document.getElementById('risk-value');
  const riskCard = document.getElementById('risk-card');
  if (riskVal) {
    if (risk) {
      riskVal.textContent = risk;
      if (riskCard) riskCard.style.display = '';
    } else {
      if (riskCard) riskCard.style.display = 'none';
    }
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
  const h = a.highlights || {};
  const highlightParts = [
    h.strongestEvidence,
    h.mainRisk ? 'Risk: ' + h.mainRisk : null
  ].filter(Boolean);
  if (detail && highlightParts.length > 0) {
    detail.textContent = highlightParts.join(' · ');
  } else if (detail && h.completionStatus && h.completionStatus.notes) {
    detail.textContent = h.completionStatus.notes;
  }
}

function renderStats(round) {
  const m = round.metrics || {};
  const statsRow = document.getElementById('stats-row');
  if (!statsRow) return;
  const ctrlCost = estimateCost(m.lastModel, m.inputTokens, m.outputTokens);
  const agentCost = estimateSubagentCost(m.lastModel, m.subagentTotalTokens);
  const totalCost = (ctrlCost != null || agentCost != null)
    ? (ctrlCost || 0) + (agentCost || 0) : null;

  const tokensByModel = Array.isArray(m.tokensByModel) ? m.tokensByModel : [];
  const tokenItems = tokensByModel.length > 0
    ? tokensByModel.flatMap(r => [
        { label: shortModelName(r.model) + ' input',  value: formatNumber(r.inputTokens) },
        { label: shortModelName(r.model) + ' output', value: formatNumber(r.outputTokens) },
      ])
    : [
        { label: 'Controller input',  value: formatNumber(m.inputTokens) },
        { label: 'Controller output', value: formatNumber(m.outputTokens) },
      ];
  const subagentTokensByModel = Array.isArray(m.subagentTokensByModel) ? m.subagentTokensByModel : [];
  const subagentItems = subagentTokensByModel.length > 0
    ? subagentTokensByModel.map(r => ({ label: shortModelName(r.model), value: formatNumber(r.totalTokens) }))
    : [{ label: 'Total', value: formatNumber(m.subagentTotalTokens) }];

  const ctrlCostItems = tokensByModel.length > 0
    ? tokensByModel.map(r => ({
        label: shortModelName(r.model),
        value: formatCost(estimateCost(r.model, r.inputTokens, r.outputTokens))
      }))
    : [{ label: 'Controller', value: formatCost(ctrlCost) }];
  const subagentCostItems = subagentTokensByModel.length > 0
    ? subagentTokensByModel.map(r => ({
        label: shortModelName(r.model) + ' ~',
        value: formatCost(estimateSubagentCost(r.model, r.totalTokens))
      }))
    : [{ label: 'Subagents ~', value: formatCost(agentCost) }];
  const costItems = [...ctrlCostItems, ...subagentCostItems, { label: 'Total *', value: formatCost(totalCost) }];

  const groups = [
    { heading: 'Controller tokens', items: tokenItems },
    { heading: 'Subagent tokens',   items: subagentItems },
    { heading: 'Cost',              items: costItems },
    {
      heading: 'Session',
      items: [
        { label: 'Turns',         value: m.turnCount != null ? m.turnCount : '—' },
        { label: 'Files changed', value: m.filesChanged != null ? m.filesChanged : '—' },
        { label: 'Insertions',    value: m.insertions != null ? '+' + m.insertions : '—' },
        { label: 'Deletions',     value: m.deletions != null ? '-' + m.deletions : '—' },
      ]
    }
  ];
  statsRow.innerHTML = groups.map(g =>
    `<div class="stat-group">
      <div class="stat-group-heading">${escapeHtml(g.heading)}</div>
      <div class="stat-group-items">${g.items.map(s =>
        `<div class="stat-item"><div class="stat-value">${escapeHtml(String(s.value))}</div><div class="stat-label">${escapeHtml(s.label)}</div></div>`
      ).join('')}</div>
    </div>`
  ).join('');

  const card = document.getElementById('stats-card');
  if (card) {
    let note = card.querySelector('.cost-note');
    if (!note) {
      note = document.createElement('p');
      note.className = 'cost-note';
      card.appendChild(note);
    }
    note.textContent = `* Claude API rates as of ${COST_RATES_DATE}. Controller cost uses input/output tokens only (excludes prompt cache). Subagent cost from <usage> tags assumes 90/10 input/output split.`;
  }
}

function renderTimeline(analysis) {
  const container = document.getElementById('session-timeline');
  if (!container) return;
  const events = (analysis || {}).sessionTimeline || [];
  if (events.length === 0) {
    container.innerHTML = '<p class="empty-state">No timeline recorded.</p>';
    return;
  }
  container.innerHTML = events.map((event, i) =>
    `<div class="tl-entry">
      <span class="tl-index">${i + 1}</span>
      <span class="tl-text">${escapeHtml(event)}</span>
    </div>`
  ).join('');
}

function renderScreenshots(screenshots) {
  const section = document.getElementById('screenshots-section');
  const grid = document.getElementById('screenshot-grid');
  const proofArea = document.getElementById('proof-screenshots-area');

  if (!screenshots || screenshots.length === 0) {
    if (section) section.style.display = 'none';
    return;
  }

  const makeItem = (s, large) => {
    const path = escapeHtml(s.path || '');
    const label = escapeHtml(s.label || s.path || '');
    return `<div class="screenshot-item" data-src="${path}" style="${large ? '' : 'max-width:200px'}">
      <img src="${path}" alt="${label}" loading="lazy">
      <div class="screenshot-label">${label}</div>
    </div>`;
  };

  if (grid) {
    grid.innerHTML = screenshots.map(s => makeItem(s, true)).join('');
    grid.querySelectorAll('.screenshot-item').forEach(item => {
      item.addEventListener('click', () => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `<img src="${item.dataset.src}" alt="">`;
        overlay.addEventListener('click', () => overlay.remove());
        document.body.appendChild(overlay);
      });
    });
  }

  if (section) section.style.display = 'block';

  if (proofArea) {
    proofArea.innerHTML = `<h3 class="section-subheading">Screenshots</h3>
      <div class="screenshot-grid">${screenshots.map(s => makeItem(s, true)).join('')}</div>`;
    proofArea.querySelectorAll('.screenshot-item').forEach(item => {
      item.addEventListener('click', () => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `<img src="${item.dataset.src}" alt="">`;
        overlay.addEventListener('click', () => overlay.remove());
        document.body.appendChild(overlay);
      });
    });
  }
}

function renderFlags(round) {
  const flags = (round.patterns || {}).flags || [];
  const row = document.getElementById('flags-row');
  if (!row) return;
  if (flags.length === 0) {
    row.innerHTML = '<span class="flag-chip green">No issues detected</span>';
    return;
  }
  row.innerHTML = flags.map(f => {
    const count = f.count != null ? ` (${f.count})` : '';
    return `<span class="flag-chip ${escapeHtml(f.level)}">${escapeHtml(f.label)}${count}</span>`;
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
  if (notProven) notProven.innerHTML = makeList(s.whatStillNotProven);
}

function renderProof(analysis) {
  const proof = analysis.proof || {};

  // Artifact inventory — index.html has <ul id="artifact-inventory">
  const invEl = document.getElementById('artifact-inventory');
  if (invEl) {
    const items = proof.artifactInventory || [];
    if (items.length === 0) {
      invEl.innerHTML = '<li class="empty-state">No artifacts recorded.</li>';
    } else {
      invEl.innerHTML = items.map(item =>
        `<li class="artifact-item">
          <strong>${escapeHtml(item.name || '')}</strong>
          ${item.path && isSafePath(item.path) ? ` — <a href="${escapeHtml(item.path)}">${escapeHtml(item.path)}</a>` : (item.path ? ` — ${escapeHtml(item.path)}` : '')}
          ${item.description ? `<div class="artifact-desc">${renderMarkdown(item.description)}</div>` : ''}
        </li>`
      ).join('');
    }
  }

  // Evidence table
  const tbody = document.getElementById('proof-evidence-tbody');
  if (tbody) {
    const rows = proof.evidenceTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No evidence recorded.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        `<tr><td>${renderMarkdown(r.point)}</td><td>${renderMarkdown(r.where)}</td><td>${renderMarkdown(r.whyItMatters)}</td></tr>`
      ).join('');
    }
  }

  // High-signal excerpts — index.html has <ul id="proof-excerpts">
  const excerpts = document.getElementById('proof-excerpts');
  if (excerpts) {
    const items = proof.transcriptExcerpts || [];
    if (items.length === 0) {
      excerpts.innerHTML = '<li class="empty-state">No excerpts recorded.</li>';
    } else {
      excerpts.innerHTML = items.map(ex =>
        `<li>${renderMarkdown(ex)}</li>`
      ).join('');
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
    const items = t.newTests || [];
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
      { label: 'Diff stat', key: 'hasDiffStat' },
      { label: 'Diff patch', key: 'hasDiffPatch' }
    ];
    let html = badges.map(b => {
      const present = st[b.key];
      return `<span class="diff-badge ${present ? 'present' : 'absent'}">${escapeHtml(b.label)}: ${present ? 'Yes' : 'No'}</span>`;
    }).join('');
    if (st.note) html += `<p class="diff-note">${renderMarkdown(st.note)}</p>`;
    statusEl.innerHTML = html;
  }

  // Files changed list
  const filesEl = document.getElementById('diff-files-changed');
  if (filesEl) {
    const files = diff.filesChanged || [];
    if (files.length === 0) {
      filesEl.innerHTML = '<li class="empty-state">No files recorded.</li>';
    } else {
      filesEl.innerHTML = files.map(f => {
        const path = typeof f === 'string' ? f : (f.file || '');
        const desc = typeof f === 'object' ? (f.description || '') : '';
        return `<li><code>${escapeHtml(path)}</code>${desc ? ` — ${renderMarkdown(desc)}` : ''}</li>`;
      }).join('');
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
        `<tr><td>${renderMarkdown(r.area)}</td><td>${renderMarkdown(r.evidenceInTranscript)}</td><td>${renderMarkdown(r.observedEffect)}</td></tr>`
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
      ? items.map(item => {
          if (typeof item === 'string') return `<li>${renderMarkdown(item)}</li>`;
          return `<li><strong>${escapeHtml(item.title || '')}</strong>${item.detail ? `<br><span class="improvement-detail">${renderMarkdown(item.detail)}</span>` : ''}</li>`;
        }).join('')
      : '<li class="empty-state">No improvements recorded.</li>';
  }

  const userEl = document.getElementById('user-improvements-list');
  if (userEl) {
    const items = analysis.userImprovements || [];
    userEl.innerHTML = items.length > 0
      ? items.map(item => {
          if (typeof item === 'string') return `<li>${renderMarkdown(item)}</li>`;
          return `<li><strong>${escapeHtml(item.title || '')}</strong>${item.detail ? `<br><span class="improvement-detail">${renderMarkdown(item.detail)}</span>` : ''}</li>`;
        }).join('')
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

function isSafePath(path) {
  if (/^\/\//.test(path)) return false;
  return /^https?:\/\//i.test(path) || /^\.{0,2}\//.test(path) || /^[^:]+$/.test(path);
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
    if (item.path && isSafePath(item.path)) {
      return `<li><a href="${escapeHtml(item.path)}" target="_blank">${escapeHtml(item.name || item.label || item.path)}</a></li>`;
    }
    return `<li>${escapeHtml(item.name || item.label || item.path || String(item))}</li>`;
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
      ? `<span class="transcript-ts">${escapeHtml(new Date(entry.timestamp).toLocaleTimeString())}</span>`
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
    const time = r.generatedAt
      ? new Date(r.generatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';
    const isActive = i === data.rounds.length - 1;
    return `<button class="round-btn${isActive ? ' active' : ''}" data-round="${i}">` +
      `<span class="round-btn-num">Round ${i + 1}</span>` +
      (time ? `<span class="round-btn-time">${escapeHtml(time)}</span>` : '') +
      `</button>`;
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

function renderTools(tools) {
  if (!tools) return;

  const callList = document.getElementById('tools-call-list');
  if (callList) {
    const calls = tools.toolCalls || [];
    if (calls.length === 0) {
      callList.innerHTML = '<p class="empty-state">No tool calls recorded.</p>';
    } else {
      const max = calls[0].count;
      callList.innerHTML = calls.map(t => {
        const pct = max > 0 ? Math.round((t.count / max) * 100) : 0;
        return `<div class="tool-bar-row">
          <span class="tool-bar-name">${escapeHtml(t.name)}</span>
          <div class="tool-bar-track"><div class="tool-bar-fill" style="width:${pct}%"></div></div>
          <span class="tool-bar-count">${escapeHtml(String(t.count))}</span>
        </div>`;
      }).join('');
    }
  }

  const subagentsEl = document.getElementById('tools-subagents');
  if (subagentsEl) {
    const subagents = tools.subagents || [];
    if (subagents.length === 0) {
      subagentsEl.innerHTML = '<p class="empty-state">No subagents dispatched.</p>';
    } else {
      subagentsEl.innerHTML = subagents.map(s =>
        `<div class="subagent-card">
          <div class="subagent-desc">${escapeHtml(s.description)}</div>
          <div class="subagent-meta">
            ${s.model ? `<span class="subagent-badge">${escapeHtml(s.model)}</span>` : ''}
            ${s.subagentType && s.subagentType !== 'general-purpose' ? `<span class="subagent-badge">${escapeHtml(s.subagentType)}</span>` : ''}
          </div>
        </div>`
      ).join('');
    }
  }

  const skillsEl = document.getElementById('tools-skills-list');
  if (skillsEl) {
    const skills = tools.skills || [];
    if (skills.length === 0) {
      skillsEl.innerHTML = '<li class="empty-state">No skills invoked.</li>';
    } else {
      skillsEl.innerHTML = skills.map(s => {
        const truncated = s.args && s.args.length > 80
          ? s.args.slice(0, 80) + '\u2026'
          : (s.args || '');
        return `<li><code class="skill-name">${escapeHtml(s.name)}</code>${truncated ? `<span class="skill-args">${escapeHtml(truncated)}</span>` : ''}</li>`;
      }).join('');
    }
  }
}

// ── main render ───────────────────────────────────────────────────────────────

function renderRound(data, round) {
  const analysis = round.analysis || {};

  renderPageHeader(data, round);
  renderHighlights(analysis);
  renderVerdict(round);
  renderStats(round);
  renderFlags(round);
  renderSummary(analysis);
  renderProof(analysis);
  renderTestsExisting(analysis);
  renderTestsNew(analysis);
  renderFriction(analysis);
  renderDiff(analysis);
  renderTools(round.tools);
  renderScreenshots(round.screenshots);
  renderImprovements(analysis);
  renderPromptPattern(analysis);
  renderSessionArtifacts(analysis);
  renderVerdictStatement(analysis);
  renderTimeline(analysis);
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
