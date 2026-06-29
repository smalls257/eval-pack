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

class SafeHtml { constructor(s) { this.s = String(s == null ? '' : s); } }

// Mark a string as already-escaped HTML — skips auto-escaping in html``
function safe(s) { return new SafeHtml(s == null ? '' : String(s)); }

// Tagged template: auto-escapes all interpolated values; wrap in safe() to opt out
function html(strings, ...values) {
  let result = strings[0];
  for (let i = 0; i < values.length; i++) {
    const val = values[i];
    result += val instanceof SafeHtml
      ? val.s
      : escapeHtml(val == null ? '' : val);
    result += strings[i + 1];
  }
  return result;
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

// Cache pricing (Anthropic, 5-minute ephemeral): cache WRITE = 1.25x base input,
// cache READ = 0.10x base input. Agentic sessions are cache-read dominated, so
// omitting these (as the old formula did) undercounts controller cost massively.
function estimateCost(model, inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens) {
  const r = modelRates(model);
  const cost = (
    (inputTokens      || 0) * r.inRate +
    (outputTokens     || 0) * r.outRate +
    (cacheWriteTokens || 0) * r.inRate * 1.25 +
    (cacheReadTokens  || 0) * r.inRate * 0.10
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

// Total cost = the sum of the per-model rows actually shown. Computing it as a
// single lastModel-on-aggregate estimate diverges from the displayed rows when
// models differ (e.g. a cheap lastModel makes Total < the sum above it).
function sumReportedCost(tokensByModel, subagentTokensByModel, fallbackCtrl, fallbackAgent) {
  let total = null;
  const add = (v) => { if (v != null) total = (total || 0) + v; };
  if (tokensByModel.length > 0) {
    for (const r of tokensByModel) {
      add(estimateCost(r.model, r.inputTokens, r.outputTokens, r.cacheReadTokens, r.cacheWriteTokens));
    }
  } else { add(fallbackCtrl); }
  if (subagentTokensByModel.length > 0) {
    for (const r of subagentTokensByModel) add(estimateSubagentCost(r.model, r.totalTokens));
  } else { add(fallbackAgent); }
  return total;
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

function renderPageHeader(data) {
  const m = data.metrics || {};
  const a = data.analysis || {};
  const latestRound = (data.rounds || []).slice(-1)[0] || {};
  const title = a.title || data.sessionId || 'Eval Pack';

  setText('page-title', title);
  setText('session-id', data.sessionId || '—');

  // Summary subtitle — verdictStatement as deck text
  const summaryEl = document.getElementById('page-summary');
  if (summaryEl) summaryEl.textContent = a.verdictStatement || '';

  setText('header-stat-workspace-value', m.lastModel || '—');
  setText('header-stat-messages-value', m.turnCount != null ? m.turnCount : '—');
  setText('header-stat-files-value', m.filesChanged != null ? m.filesChanged : '—');
  setText('header-stat-tokens-value', formatNumber((m.inputTokens || 0) + (m.outputTokens || 0) + (m.subagentTotalTokens || 0)));
  setText('header-stat-branch-value', latestRound.gitBranch || '—');

  const genAt = document.getElementById('generated-at');
  if (genAt && data.generatedAt) {
    genAt.textContent = new Date(data.generatedAt).toLocaleString();
  }
}

function renderHighlights(analysis) {
  const h = (analysis || {}).highlights || {};
  const cs = h.completionStatus || {};

  // Completion card
  const card = document.getElementById('completion-card');
  const val = document.getElementById('completion-value');
  const notes = document.getElementById('completion-notes');
  if (card && cs.label) {
    const color = /^(green|amber|red)$/.test(cs.color || '') ? cs.color : 'green';
    card.className = `highlight-card completion-card completion-${color}`;
    if (val) val.innerHTML = html`<span class="completion-dot"></span>${cs.label}`;
    if (notes) notes.textContent = cs.notes || '';
  }

  // Confidence card
  const confCard = document.getElementById('confidence-card');
  const confVal = document.getElementById('confidence-value');
  const confNotes = document.getElementById('confidence-notes');
  const pct = h.confidencePercent;
  if (confCard && pct != null) {
    const n = Math.max(0, Math.min(100, Number(pct) || 0));
    const tier = n >= 75 ? 'high' : n >= 40 ? 'mid' : 'low';
    confCard.className = `highlight-card confidence-card confidence-${tier}`;
    confCard.style.display = '';
    if (confVal) confVal.innerHTML =
      html`${n}%<div class="confidence-bar"><div class="confidence-bar-fill" style="width:${n}%"></div></div>`;
    if (confNotes) confNotes.textContent = h.confidenceNotes || '';
  } else if (confCard) {
    confCard.style.display = 'none';
  }

  // Business risk card
  const bizCard = document.getElementById('biz-risk-card');
  const bizVal = document.getElementById('biz-risk-value');
  const bizNotes = document.getElementById('biz-risk-notes');
  const biz = h.businessRisk || {};
  if (bizCard && biz.level) {
    const lvl = /^(low|medium|high)$/.test(biz.level) ? biz.level : 'medium';
    bizCard.className = `highlight-card biz-risk-card biz-risk-${lvl}`;
    bizCard.style.display = '';
    if (bizVal) bizVal.textContent = lvl.charAt(0).toUpperCase() + lvl.slice(1);
    if (bizNotes) bizNotes.textContent = biz.notes || '';
  } else if (bizCard) {
    bizCard.style.display = 'none';
  }

  // Risk mitigation card
  const mitCard = document.getElementById('mitigation-card');
  const mitVal = document.getElementById('mitigation-value');
  const steps = h.riskMitigation || [];
  if (mitCard && steps.length > 0) {
    mitCard.style.display = '';
    if (mitVal) mitVal.innerHTML = steps.map(s =>
      html`<div class="mitigation-step">${s}</div>`
    ).join('');
  } else if (mitCard) {
    mitCard.style.display = 'none';
  }

  // Main risk card
  const riskVal = document.getElementById('risk-value');
  const riskCard = document.getElementById('risk-card');
  if (riskVal) {
    const risk = h.mainRisk || '';
    if (risk) {
      riskVal.textContent = risk;
      if (riskCard) riskCard.style.display = '';
    } else {
      if (riskCard) riskCard.style.display = 'none';
    }
  }
}

function renderVerdict(data) {
  const p = data.patterns || {};
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
  } else if ((data.analysis || {}).disabled) {
    level = 'green';
    iconChar = 'ℹ';
    summaryText = 'Analysis disabled — heuristic flags only';
  } else {
    level = 'green';
    iconChar = '✓';
    summaryText = 'Session complete';
  }

  banner.className = 'verdict-banner verdict-' + level;
  if (icon) icon.textContent = iconChar;
  if (text) text.textContent = summaryText;

  const h = (data.analysis || {}).highlights || {};
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

function renderStats(data) {
  const m = data.metrics || {};
  const statsRow = document.getElementById('stats-row');
  if (!statsRow) return;
  const ctrlCost = estimateCost(m.lastModel, m.inputTokens, m.outputTokens, m.cacheReadTokens, m.cacheWriteTokens);
  const agentCost = estimateSubagentCost(m.lastModel, m.subagentTotalTokens);

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
        value: formatCost(estimateCost(r.model, r.inputTokens, r.outputTokens, r.cacheReadTokens, r.cacheWriteTokens))
      }))
    : [{ label: 'Controller', value: formatCost(ctrlCost) }];
  const subagentCostItems = subagentTokensByModel.length > 0
    ? subagentTokensByModel.map(r => ({
        label: shortModelName(r.model),
        value: '~' + formatCost(estimateSubagentCost(r.model, r.totalTokens))
      }))
    : [{ label: 'Subagents', value: '~' + formatCost(agentCost) }];
  const totalCost = sumReportedCost(tokensByModel, subagentTokensByModel, ctrlCost, agentCost);
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
    html`<div class="stat-group">
      <div class="stat-group-heading">${g.heading}</div>
      <div class="stat-group-items">${safe(g.items.map(s =>
        html`<div class="stat-item"><div class="stat-value">${String(s.value)}</div><div class="stat-label">${s.label}</div></div>`
      ).join(''))}</div>
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
    note.textContent = `* Claude API rates as of ${COST_RATES_DATE}. Controller cost includes input, output, and cache (write 1.25x, read 0.10x of base input). Subagent cost (~) assumes a 90/10 input/output split — only subagent_tokens is reported.`;
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
    html`<div class="tl-entry">
      <span class="tl-index">${i + 1}</span>
      <span class="tl-text">${event}</span>
    </div>`
  ).join('');
}

function screenshotBadge(source) {
  const src = source || 'unknown';
  if (src === 'agent') return { text: 'Agent-captured', cls: 'badge-agent' };
  if (src === 'test') return { text: 'Automated test', cls: 'badge-test' };
  return { text: 'Unknown source', cls: 'badge-unknown' };
}

function wrapIndex(i, n) {
  if (n <= 0) return 0;
  return ((i % n) + n) % n;
}

// One reusable enlarged-image viewer. Public surface: openLightbox(rounds, roundIdx, imgIdx).
const openLightbox = (() => {
  let overlay = null;
  let rounds = [];
  let roundIdx = 0;
  let imgIdx = 0;

  function shots() {
    return (rounds[roundIdx] && rounds[roundIdx].screenshots) || [];
  }

  function build() {
    overlay = document.createElement('div');
    overlay.className = 'modal-overlay lightbox';
    overlay.innerHTML = html`
      <div class="lightbox-panel" role="dialog" aria-modal="true">
        <div class="lightbox-bar">
          <select class="lightbox-round" aria-label="Round"></select>
          <button class="lightbox-close" type="button" aria-label="Close">✕</button>
        </div>
        <div class="lightbox-stage">
          <button class="lightbox-nav lightbox-prev" type="button" aria-label="Previous">‹</button>
          <img class="lightbox-img" alt="">
          <button class="lightbox-nav lightbox-next" type="button" aria-label="Next">›</button>
        </div>
        <div class="lightbox-details">
          <span class="screenshot-badge"></span>
          <div class="lightbox-label"></div>
          <div class="lightbox-counter"></div>
        </div>
      </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    overlay.querySelector('.lightbox-close').addEventListener('click', close);
    overlay.querySelector('.lightbox-prev').addEventListener('click', () => step(-1));
    overlay.querySelector('.lightbox-next').addEventListener('click', () => step(1));
    overlay.querySelector('.lightbox-round')
      .addEventListener('change', e => selectRound(parseInt(e.target.value, 10)));
    document.body.appendChild(overlay);
  }

  function onKey(e) {
    if (e.key === 'ArrowLeft') step(-1);
    else if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'Escape') close();
  }

  function buildRoundOptions() {
    const sel = overlay.querySelector('.lightbox-round');
    sel.innerHTML = rounds.map((r, i) => {
      const time = r.generatedAt
        ? new Date(r.generatedAt).toLocaleString([], {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          })
        : '';
      const label = `Round ${i + 1}` + (time ? ` — ${time}` : '');
      return html`<option value="${i}">${label}</option>`;
    }).join('');
  }

  function render() {
    const list = shots();
    const s = list[imgIdx] || {};
    const badge = screenshotBadge(s.source);
    const img = overlay.querySelector('.lightbox-img');
    img.src = s.path || '';
    img.alt = s.label || '';
    const badgeEl = overlay.querySelector('.lightbox-details .screenshot-badge');
    badgeEl.textContent = badge.text;
    badgeEl.className = 'screenshot-badge ' + badge.cls;
    overlay.querySelector('.lightbox-label').textContent = s.label || s.path || '';
    overlay.querySelector('.lightbox-counter').textContent =
      list.length ? `${imgIdx + 1} of ${list.length}` : '0 of 0';
    overlay.querySelector('.lightbox-round').value = String(roundIdx);
    const empty = list.length === 0;
    overlay.querySelector('.lightbox-prev').disabled = empty;
    overlay.querySelector('.lightbox-next').disabled = empty;
  }

  function step(delta) {
    imgIdx = wrapIndex(imgIdx + delta, shots().length);
    render();
  }

  function selectRound(idx) {
    roundIdx = idx;
    imgIdx = 0;
    render();
  }

  function close() {
    // Hide, don't destroy: the overlay is built once and reused across opens,
    // so listeners bound in build() are never re-attached (no duplicate keydowns).
    if (overlay) overlay.style.display = 'none';
    document.removeEventListener('keydown', onKey);
  }

  return function open(allRounds, rIdx, iIdx) {
    rounds = allRounds || [];
    roundIdx = rIdx ?? 0;
    imgIdx = iIdx ?? 0;
    if (!overlay) build();
    buildRoundOptions();
    overlay.style.display = 'flex';
    document.addEventListener('keydown', onKey);
    render();
  };
})();

function makeScreenshotItem(s) {
  const path = s.path || '';
  const label = s.label || s.path || '';
  const badge = screenshotBadge(s.source);
  return html`<div class="screenshot-item">
    <span class="screenshot-badge ${badge.cls}">${badge.text}</span>
    <img src="${path}" alt="${label}" loading="lazy">
    <div class="screenshot-label">${label}</div>
  </div>`;
}

function attachScreenshotClicks(container, allRounds, roundIdx) {
  container.querySelectorAll('.screenshot-item').forEach((item, i) => {
    item.addEventListener('click', () => openLightbox(allRounds, roundIdx, i));
  });
}

function renderVisualEvidence(data) {
  const section = document.getElementById('screenshots-section');
  const grid = document.getElementById('screenshot-grid');
  const filterNav = document.getElementById('evidence-round-filter');
  if (!section || !grid) return;

  const rounds = data.rounds || [];
  const anyScreenshots = rounds.some(r => r.screenshots && r.screenshots.length > 0);
  if (!anyScreenshots) { section.style.display = 'none'; return; }

  section.style.display = 'block';

  let activeIdx = rounds.length - 1;

  function showRound(idx) {
    activeIdx = idx;
    const screenshots = (rounds[idx] && rounds[idx].screenshots) || [];
    if (screenshots.length === 0) {
      grid.innerHTML = '<p class="empty-state">No screenshots for this round.</p>';
    } else {
      grid.innerHTML = screenshots.map(makeScreenshotItem).join('');
      attachScreenshotClicks(grid, rounds, idx);
    }
    if (filterNav) {
      filterNav.querySelectorAll('.round-btn').forEach((b, i) => {
        b.classList.toggle('active', i === idx);
      });
    }
    // Also update proof-screenshots-area if present
    const proofArea = document.getElementById('proof-screenshots-area');
    if (proofArea && screenshots.length > 0) {
      proofArea.innerHTML = html`<h3 class="section-subheading">Screenshots</h3>
        <div class="screenshot-grid">${safe(screenshots.map(makeScreenshotItem).join(''))}</div>`;
      attachScreenshotClicks(proofArea, rounds, idx);
    }
  }

  if (filterNav) {
    if (rounds.length > 1) {
      filterNav.style.display = 'flex';
      filterNav.innerHTML = rounds.map((r, i) => {
        const time = r.generatedAt
          ? new Date(r.generatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : '';
        return html`<button class="round-btn${i === activeIdx ? ' active' : ''}" data-round="${i}">` +
          html`<span class="round-btn-num">Round ${i + 1}</span>` +
          (time ? html`<span class="round-btn-time">${time}</span>` : '') +
          `</button>`;
      }).join('');
      filterNav.querySelectorAll('.round-btn').forEach(btn => {
        btn.addEventListener('click', () => showRound(parseInt(btn.dataset.round, 10)));
      });
    } else {
      filterNav.style.display = 'none';
    }
  }

  showRound(activeIdx);
}

function renderFlags(data) {
  const flags = (data.patterns || {}).flags || [];
  const row = document.getElementById('flags-row');
  if (!row) return;
  if (flags.length === 0) {
    row.innerHTML = '<span class="flag-chip green">No issues detected</span>';
    return;
  }
  row.innerHTML = flags.map(f => {
    const count = f.count != null ? ` (${f.count})` : '';
    return html`<span class="flag-chip ${f.level}">${f.label}${count}</span>`;
  }).join('');
}

function renderSummary(analysis) {
  const s = analysis.summary || {};

  const whatChanged = document.getElementById('summary-what-changed');
  // index.html uses id="summary-what-proves" (not "summary-proves")
  const proves = document.getElementById('summary-what-proves');
  const notProven = document.getElementById('summary-not-proven');

  const makeList = arr => (arr && arr.length > 0)
    ? '<ul>' + arr.map(item => html`<li>${safe(renderMarkdown(item))}</li>`).join('') + '</ul>'
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
        html`<li class="artifact-item">
          <strong>${item.name || ''}</strong>${safe(
            item.path && isSafePath(item.path)
              ? html` — <a href="${item.path}">${item.path}</a>`
              : item.path ? html` — ${item.path}` : ''
          )}${safe(item.description ? `<div class="artifact-desc">${renderMarkdown(item.description)}</div>` : '')}
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
        html`<tr><td>${safe(renderMarkdown(r.point))}</td><td>${safe(renderMarkdown(r.where))}</td><td>${safe(renderMarkdown(r.whyItMatters))}</td></tr>`
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
        html`<li>${safe(renderMarkdown(ex))}</li>`
      ).join('');
    }
  }
}

function renderTestsExisting(analysis) {
  const t = analysis.testsExisting || {};
  const narr = document.getElementById('tests-existing-narrative');
  if (narr) narr.innerHTML = html`${safe(renderMarkdown(t.narrative || ''))}`;

  const tbody = document.getElementById('tests-existing-tbody');
  if (tbody) {
    const rows = t.validationTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No validation data.</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        html`<tr><td>${safe(renderMarkdown(r.validation))}</td><td>${safe(renderMarkdown(r.observedResult))}</td><td>${safe(renderMarkdown(r.interpretation))}</td></tr>`
      ).join('');
    }
  }

  const coveredWell = document.getElementById('tests-covered-well');
  const notCovered = document.getElementById('tests-not-covered');
  const makeList = arr => (arr && arr.length > 0)
    ? '<ul>' + arr.map(item => html`<li>${safe(renderMarkdown(item))}</li>`).join('') + '</ul>'
    : '<p class="empty-state">Nothing recorded.</p>';

  if (coveredWell) coveredWell.innerHTML = makeList(t.coveredWell);
  if (notCovered) notCovered.innerHTML = makeList(t.notCovered);
}

function renderTestsNew(analysis) {
  const t = analysis.testsNew || {};
  const narr = document.getElementById('tests-new-narrative');
  if (narr) narr.innerHTML = html`${safe(renderMarkdown(t.narrative || ''))}`;

  const list = document.getElementById('tests-new-list');
  if (list) {
    const items = t.newTests || [];
    if (items.length === 0) {
      list.innerHTML = '<li class="empty-state">No new tests recorded.</li>';
    } else {
      list.innerHTML = items.map(item => html`<li>${safe(renderMarkdown(item))}</li>`).join('');
    }
  }
}

function renderReviewFindings(analysis) {
  const tbody = document.getElementById('review-findings-tbody');
  if (!tbody) return;
  const rows = analysis.reviewFindings || [];
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No review findings recorded.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const sev = r.severity || 'suggestion';
    return html`<tr>
      <td>${safe(renderMarkdown(r.issue))}</td>
      <td><span class="review-severity review-severity-${sev}">${sev}</span></td>
      <td>${r.foundIn || '—'}</td>
      <td>${safe(renderMarkdown(r.resolution || '—'))}</td>
      <td>${safe(r.commit ? html`<code class="review-commit">${r.commit}</code>` : '—')}</td>
    </tr>`;
  }).join('');
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
    html`<tr>
      <td>${safe(renderMarkdown(r.friction))}</td>
      <td>${safe(renderMarkdown(r.evidence))}</td>
      <td><span class="friction-type friction-${r.type || ''}">${r.type || '—'}</span></td>
      <td>${safe(renderMarkdown(r.resolution))}</td>
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
    let badgeHtml = badges.map(b => {
      const present = st[b.key];
      return html`<span class="diff-badge ${present ? 'present' : 'absent'}">${b.label}: ${present ? 'Yes' : 'No'}</span>`;
    }).join('');
    if (st.note) badgeHtml += html`<p class="diff-note">${safe(renderMarkdown(st.note))}</p>`;
    statusEl.innerHTML = badgeHtml;
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
        return html`<li><code>${path}</code>${safe(desc ? ` — ${renderMarkdown(desc)}` : '')}</li>`;
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
        html`<tr><td>${safe(renderMarkdown(r.area))}</td><td>${safe(renderMarkdown(r.evidenceInTranscript))}</td><td>${safe(renderMarkdown(r.observedEffect))}</td></tr>`
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
          if (typeof item === 'string') return html`<li>${safe(renderMarkdown(item))}</li>`;
          return html`<li><strong>${item.title || ''}</strong>${safe(item.detail ? `<br><span class="improvement-detail">${renderMarkdown(item.detail)}</span>` : '')}</li>`;
        }).join('')
      : '<li class="empty-state">No improvements recorded.</li>';
  }

  const userEl = document.getElementById('user-improvements-list');
  if (userEl) {
    const items = analysis.userImprovements || [];
    userEl.innerHTML = items.length > 0
      ? items.map(item => {
          if (typeof item === 'string') return html`<li>${safe(renderMarkdown(item))}</li>`;
          return html`<li><strong>${item.title || ''}</strong>${safe(item.detail ? `<br><span class="improvement-detail">${renderMarkdown(item.detail)}</span>` : '')}</li>`;
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
      return html`<li><a href="${item.path}" target="_blank">${item.name || item.label || item.path}</a></li>`;
    }
    return html`<li>${item.name || item.label || item.path || String(item)}</li>`;
  }).join('');
}

function renderVerdictStatement(analysis) {
  const card = document.getElementById('verdict-statement-card');
  const el = document.getElementById('verdict-statement');
  if (!card || !el) return;
  if (analysis.verdictStatement) {
    card.style.display = 'block';
    el.innerHTML = html`${safe(renderMarkdown(analysis.verdictStatement))}`;
  } else {
    card.style.display = 'none';
  }
}

function renderTranscript(transcript) {
  const container = document.getElementById('transcript-container');
  if (!container) return;
  if (!transcript || transcript.length === 0) {
    container.innerHTML = '<p class="empty-state"><a href="transcript.html" target="_blank">Open transcript →</a></p>';
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
      ? html`<span class="transcript-ts">${new Date(entry.timestamp).toLocaleTimeString()}</span>`
      : '';

    return html`<div class="transcript-entry transcript-${role}">
      <div class="transcript-header">
        <span class="transcript-role">${role}</span>
        ${safe(ts)}
        ${safe(usageLine)}
      </div>
      <div class="transcript-body">${safe(renderMarkdown(content))}</div>
    </div>`;
  }).join('');
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
        return html`<div class="tool-bar-row">
          <span class="tool-bar-name">${t.name}</span>
          <div class="tool-bar-track"><div class="tool-bar-fill" style="width:${pct}%"></div></div>
          <span class="tool-bar-count">${String(t.count)}</span>
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
        html`<div class="subagent-card">
          <div class="subagent-desc">${s.description}</div>
          <div class="subagent-meta">
            ${safe(s.model ? html`<span class="subagent-badge">${s.model}</span>` : '')}
            ${safe(s.subagentType && s.subagentType !== 'general-purpose' ? html`<span class="subagent-badge">${s.subagentType}</span>` : '')}
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
        return html`<li><code class="skill-name">${s.name}</code>${safe(truncated ? html`<span class="skill-args">${truncated}</span>` : '')}</li>`;
      }).join('');
    }
  }
}

function renderDisabledBanner(analysis) {
  const el = document.getElementById('disabled-banner');
  if (!el) return;
  el.style.display = analysis && analysis.disabled ? 'block' : 'none';
}

// ── main render ───────────────────────────────────────────────────────────────

function renderSession(data) {
  const analysis = data.analysis || {};
  renderDisabledBanner(analysis);

  renderPageHeader(data);
  renderHighlights(analysis);
  renderVerdict(data);
  renderStats(data);
  renderFlags(data);
  renderSummary(analysis);
  renderProof(analysis);
  renderTestsExisting(analysis);
  renderTestsNew(analysis);
  renderReviewFindings(analysis);
  renderFriction(analysis);
  renderDiff(analysis);
  renderTools(data.tools);
  renderImprovements(analysis);
  renderPromptPattern(analysis);
  renderSessionArtifacts(analysis);
  renderVerdictStatement(analysis);
  renderTimeline(analysis);
}

function init(data) {
  renderSession(data);
  renderVisualEvidence(data);
  renderTranscript(data.transcript);

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

if (typeof window !== 'undefined' && !window.__EVAL_PACK_TEST__) {
  if (window.__EVAL_PACK_DATA__) {
    init(window.__EVAL_PACK_DATA__);
  } else {
    fetch('data.json')
      .then(r => r.json())
      .then(init)
      .catch(err => {
        document.body.innerHTML = html`<div style="padding:2rem;font-family:monospace;color:#e74c3c">
          <h2>Failed to load eval pack data</h2>
          <p>${String(err)}</p>
        </div>`;
      });
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { screenshotBadge, wrapIndex, estimateCost, modelRates, estimateSubagentCost, sumReportedCost };
}
