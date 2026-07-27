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

// Pure lookup: the business-risk lens is a contributor named "business-risk" in
// data.lenses.contributors. Kept separate from the DOM-touching renderer so it is
// unit-testable without a document shim (Airplane Test: an absent lens must yield null,
// not throw — the three highlight cards it feeds then degrade to hidden).
function businessRiskFrom(lenses) {
  const contributors = (lenses && lenses.contributors) || [];
  return contributors.find(c => c.skill === 'business-risk') || null;
}

function renderHighlights(analysis, lenses) {
  const h = (analysis || {}).highlights || {};
  const cs = h.completionStatus || {};
  const biz = businessRiskFrom(lenses) || {};

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
  const eff = effectiveConfidence(analysis, lenses);
  const pct = eff.value;
  if (confCard && pct != null) {
    const n = Math.max(0, Math.min(100, Number(pct) || 0));
    const tier = n >= 75 ? 'high' : n >= 40 ? 'mid' : 'low';
    confCard.className = `highlight-card confidence-card confidence-${tier}`;
    confCard.style.display = '';
    if (confVal) confVal.innerHTML =
      html`${n}%<div class="confidence-bar"><div class="confidence-bar-fill" style="width:${n}%"></div></div>`;
    if (confNotes) confNotes.textContent = h.confidenceNotes || '';
    if (confNotes && eff.note) confNotes.textContent =
      (h.confidenceNotes ? h.confidenceNotes + ' — ' : '') + eff.note;
  } else if (confCard) {
    confCard.style.display = 'none';
  }

  // Business risk card
  const bizCard = document.getElementById('biz-risk-card');
  const bizVal = document.getElementById('biz-risk-value');
  const bizNotes = document.getElementById('biz-risk-notes');
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
  const steps = biz.mitigation || [];
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
    const risk = biz.mainRisk || '';
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
  const biz = businessRiskFrom(data.lenses);
  const highlightParts = [
    h.confidenceNotes,
    biz && biz.mainRisk ? 'Risk: ' + biz.mainRisk : null
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

  const groups = [
    { heading: 'Controller tokens', items: tokenItems },
    { heading: 'Subagent tokens',   items: subagentItems },
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

// Pure fit math. The zoom=1 display factor that fits a NATURAL-size image into the
// stage box (letterboxing, aspect preserved) — baked into the transform alongside the
// user's zoom `scale` so the img can be laid out at its native raster size (crisp at
// any zoom) while still presenting a consistent fit-to-stage baseline across
// differently-shaped screenshots. Falls back to 1 (no scaling) when either dimension
// is not yet known (0/NaN) — e.g. before the image has finished loading.
function computeBaseFit(naturalW, naturalH, stageW, stageH) {
  if (!(naturalW > 0) || !(naturalH > 0) || !(stageW > 0) || !(stageH > 0)) return 1;
  return Math.min(stageW / naturalW, stageH / naturalH);
}

// Pure zoom math. Given current scale + pan and a cursor offset from the image's
// (untransformed) centre, return the new scale (clamped to [1, maxScale]) and the
// pan that keeps the point under the cursor fixed. cursor (0,0) zooms about the
// centre (used by the +/- buttons). At scale 1 the pan is reset to 0.
function zoomAt(scale, panX, panY, cursorX, cursorY, factor, maxScale) {
  let next = scale * factor;
  if (next < 1) next = 1;
  if (next > maxScale) next = maxScale;
  if (next === 1) return { scale: 1, panX: 0, panY: 0 };
  const k = next / scale;
  return {
    scale: next,
    panX: cursorX - k * (cursorX - panX),
    panY: cursorY - k * (cursorY - panY),
  };
}

// One reusable enlarged-image viewer. Public surface: openLightbox(rounds, roundIdx, imgIdx).
const openLightbox = (() => {
  const MAX_SCALE = 5;
  let overlay = null;
  let rounds = [];
  let roundIdx = 0;
  let imgIdx = 0;
  let scale = 1, panX = 0, panY = 0;
  let dragging = false, dragMoved = false;
  let dragX = 0, dragY = 0, panStartX = 0, panStartY = 0;
  // baseFit: the zoom=1 "fit natural image to stage" factor (see computeBaseFit).
  // Baked into the transform alongside the user's `scale` so the img can stay laid
  // out at its native raster size (crisp) while presenting a consistent fit-to-stage
  // baseline. Recomputed on image load, image change, and window resize.
  let baseFit = 1;

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
          <div class="lightbox-zoom">
            <button class="lightbox-zoombtn lightbox-zoomout" type="button" aria-label="Zoom out">−</button>
            <span class="lightbox-zoomlevel">100%</span>
            <button class="lightbox-zoombtn lightbox-zoomin" type="button" aria-label="Zoom in">+</button>
            <button class="lightbox-zoombtn lightbox-zoomreset" type="button" aria-label="Reset zoom">reset</button>
          </div>
          <button class="lightbox-close" type="button" aria-label="Close">✕</button>
        </div>
        <div class="lightbox-stage">
          <button class="lightbox-nav lightbox-prev" type="button" aria-label="Previous">‹</button>
          <img class="lightbox-img" alt="" draggable="false">
          <button class="lightbox-nav lightbox-next" type="button" aria-label="Next">›</button>
        </div>
        <div class="lightbox-details">
          <span class="screenshot-badge"></span>
          <div class="lightbox-label"></div>
          <div class="lightbox-counter"></div>
        </div>
      </div>`;
    overlay.addEventListener('click', e => {
      if (dragMoved) { dragMoved = false; return; }  // a pan-drag is not a backdrop click
      if (e.target === overlay) close();
    });
    overlay.querySelector('.lightbox-close').addEventListener('click', close);
    overlay.querySelector('.lightbox-prev').addEventListener('click', () => step(-1));
    overlay.querySelector('.lightbox-next').addEventListener('click', () => step(1));
    overlay.querySelector('.lightbox-round')
      .addEventListener('change', e => selectRound(parseInt(e.target.value, 10)));
    overlay.querySelector('.lightbox-zoomin').addEventListener('click', () => zoomBy(1.25));
    overlay.querySelector('.lightbox-zoomout').addEventListener('click', () => zoomBy(1 / 1.25));
    overlay.querySelector('.lightbox-zoomreset').addEventListener('click', resetZoom);
    const img = overlay.querySelector('.lightbox-img');
    img.addEventListener('dblclick', resetZoom);
    img.addEventListener('wheel', onWheel, { passive: false });
    img.addEventListener('mousedown', onDragStart);
    img.addEventListener('load', () => { recomputeBaseFit(); applyZoom(); });
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
    // The overlay is hidden (not destroyed) on close, and this window listener lives for
    // the page's lifetime — early-return when closed so we don't recompute against a
    // display:none stage (whose clientWidth is 0). Symmetric intent with keydown's removal.
    window.addEventListener('resize', () => {
      if (!overlay || overlay.style.display === 'none') return;
      recomputeBaseFit(); applyZoom();
    });
    document.body.appendChild(overlay);
  }

  // Recompute baseFit from the img's natural size (available once loaded) and the
  // stage's current client box. Safe to call before the image has loaded — falls
  // back to 1 (computeBaseFit's Airplane-Test guard against 0/NaN).
  // Note: scale/pan intentionally persist across a resize; a rare resize while zoomed+panned
  // can off-center the image, but overflow:hidden clips it and reset/dblclick recenters.
  function recomputeBaseFit() {
    const img = overlay.querySelector('.lightbox-img');
    const stage = overlay.querySelector('.lightbox-stage');
    baseFit = computeBaseFit(img.naturalWidth, img.naturalHeight, stage.clientWidth, stage.clientHeight);
  }

  function applyZoom() {
    const img = overlay.querySelector('.lightbox-img');
    // -50%,-50% recenters the natural-size box (CSS position:absolute;top/left:50%)
    // before panning/scaling — see .modal-overlay .lightbox-img in styles.css.
    img.style.transform =
      `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${baseFit * scale})`;
    img.style.cursor = scale > 1 ? (dragging ? 'grabbing' : 'grab') : '';
    overlay.querySelector('.lightbox-zoomlevel').textContent = Math.round(scale * 100) + '%';
    overlay.querySelector('.lightbox-zoomout').disabled = scale <= 1;
    overlay.querySelector('.lightbox-zoomreset').disabled = scale <= 1;
  }

  function resetZoom() {
    scale = 1; panX = 0; panY = 0;
    if (overlay) applyZoom();
  }

  function zoomBy(factor) {
    ({ scale, panX, panY } = zoomAt(scale, panX, panY, 0, 0, factor, MAX_SCALE));
    applyZoom();
  }

  function onWheel(e) {
    e.preventDefault();
    const rect = overlay.querySelector('.lightbox-img').getBoundingClientRect();
    const cx = rect.left + rect.width / 2 - panX;   // untransformed centre
    const cy = rect.top + rect.height / 2 - panY;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    ({ scale, panX, panY } = zoomAt(scale, panX, panY, e.clientX - cx, e.clientY - cy, factor, MAX_SCALE));
    applyZoom();
  }

  function onDragStart(e) {
    if (scale <= 1) return;
    e.preventDefault();
    dragging = true; dragMoved = false;
    dragX = e.clientX; dragY = e.clientY; panStartX = panX; panStartY = panY;
    applyZoom();
  }

  function onDragMove(e) {
    if (!dragging) return;
    panX = panStartX + (e.clientX - dragX);
    panY = panStartY + (e.clientY - dragY);
    if (Math.abs(e.clientX - dragX) > 2 || Math.abs(e.clientY - dragY) > 2) dragMoved = true;
    applyZoom();
  }

  function onDragEnd() {
    if (dragging) { dragging = false; applyZoom(); }
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
    scale = 1; panX = 0; panY = 0;  // each image opens at fit; nav/round-change start un-zoomed
    const list = shots();
    const s = list[imgIdx] || {};
    const badge = screenshotBadge(s.source);
    const img = overlay.querySelector('.lightbox-img');
    img.src = s.path || '';
    img.alt = s.label || '';
    // The previous image's naturalWidth/Height is stale for this src until `load`
    // fires (browsers fire `load` even for cache hits, which then recomputes and
    // repaints via the `load` listener). Recompute+paint now too against whatever the
    // img element currently reports (0 if not yet decoded, which computeBaseFit
    // treats as "unknown" and falls back to 1) so there's no flash of the previous
    // image's fit factor.
    recomputeBaseFit();
    applyZoom();
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
    resetZoom();
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

// Pure lookups: the Summary tab's 3-column narrative is sourced from the two SCORER lenses
// that already judge these dimensions (requirement-drift, verification-rigor), not from
// analysis.summary — the evaluator no longer emits that field. Scorers live in
// data.lenses.scorers (not contributors). Kept separate from the DOM-touching renderer so
// each is unit-testable without a document shim (Airplane Test: an absent lens must yield an
// empty list, not throw — the Summary column then degrades to its empty-state).
function deliveredFrom(lenses) {
  const scorers = (lenses && lenses.scorers) || [];
  const drift = scorers.find(s => s.skill === 'requirement-drift');
  return (drift && drift.delivered) || [];
}

function unmetFrom(lenses) {
  const scorers = (lenses && lenses.scorers) || [];
  const drift = scorers.find(s => s.skill === 'requirement-drift');
  return (drift && drift.unmet) || [];
}

function provenFrom(lenses) {
  const scorers = (lenses && lenses.scorers) || [];
  const rigor = scorers.find(s => s.skill === 'verification-rigor');
  return (rigor && rigor.proven) || [];
}

function unprovenFrom(lenses) {
  const scorers = (lenses && lenses.scorers) || [];
  const rigor = scorers.find(s => s.skill === 'verification-rigor');
  return (rigor && rigor.unproven) || [];
}

function renderSummary(data) {
  const lenses = data && data.lenses;

  const whatChanged = document.getElementById('summary-what-changed');
  // index.html uses id="summary-what-proves" (not "summary-proves")
  const proves = document.getElementById('summary-what-proves');
  const notProven = document.getElementById('summary-not-proven');

  const makeList = arr => (arr && arr.length > 0)
    ? '<ul>' + arr.map(item => html`<li>${safe(renderMarkdown(item))}</li>`).join('') + '</ul>'
    : '<p class="empty-state">Nothing recorded.</p>';

  if (whatChanged) whatChanged.innerHTML = makeList(deliveredFrom(lenses));
  if (proves) proves.innerHTML = makeList(provenFrom(lenses));
  if (notProven) notProven.innerHTML = makeList([...unprovenFrom(lenses), ...unmetFrom(lenses)]);
}

function renderProof(data) {
  // Artifact inventory — deterministic (built by render_html.py from the pack's actual
  // files, not the evaluator), so index.html reads it off data.artifactInventory. The
  // detailed evidence assessment (evidence table / excerpts / proven vs unproven) now
  // lives in the verification-rigor lens — see the Summary tab.
  const invEl = document.getElementById('artifact-inventory');
  if (invEl) {
    const items = data.artifactInventory || [];
    if (items.length === 0) {
      invEl.innerHTML = '<li class="empty-state">No artifacts recorded.</li>';
    } else {
      invEl.innerHTML = items.map(item =>
        html`<li class="artifact-item">
          <strong>${item.name || ''}</strong>${safe(
            item.path && artifactLinkable(item.path)
              ? html` — <a href="${artifactHref(item.path)}">${artifactHref(item.path)}</a>`
              : item.path ? html` — ${item.path}` : ''
          )}${safe(item.description ? `<div class="artifact-desc">${renderMarkdown(item.description)}</div>` : '')}
        </li>`
      ).join('');
    }
  }
}

// Pure lookup: the deterministic test verdict + commands recorded in test-results.json
// (data.testResults) — not LLM-authored. Returns null when the file is absent/empty so
// the caller can render an empty-state instead of throwing (Airplane Test).
function testResultsSummary(testResults) {
  const t = testResults || {};
  if (!t.verdict && !t.summary && !(t.testsRun || []).length) return null;
  return {
    verdict: t.verdict || 'none',
    summary: t.summary || '',
    testsRun: t.testsRun || [],
  };
}

function renderTests(data) {
  const container = document.getElementById('tests-body');
  if (!container) return;
  const t = testResultsSummary(data.testResults);
  if (!t) {
    container.innerHTML = '<p class="empty-state">No test results recorded.</p>';
    return;
  }
  const verdictCls = t.verdict === 'pass' ? 'green' : t.verdict === 'fail' ? 'red' : 'amber';
  const rows = t.testsRun.map(r =>
    html`<tr><td>${safe(renderMarkdown(r.name || ''))}</td><td>${r.passed ? '✓ pass' : '✗ fail'}</td><td>${safe(renderMarkdown(r.output || ''))}</td></tr>`
  ).join('');
  container.innerHTML = html`
    <p class="tests-verdict tests-verdict-${verdictCls}">Verdict: <strong>${t.verdict}</strong>${safe(t.summary ? ' — ' + renderMarkdown(t.summary) : '')}</p>
    ${safe(t.testsRun.length > 0
      ? html`<table class="data-table" id="tests-run-table">
          <thead><tr><th>Test</th><th>Result</th><th>Output</th></tr></thead>
          <tbody>${safe(rows)}</tbody>
        </table>`
      : '<p class="empty-state">No individual test records.</p>')}`;
}

// Pure lookup: the review lens is a contributor named "review" in data.lenses.contributors.
// Kept separate from the DOM-touching renderer so it is unit-testable without a document shim
// (Airplane Test for the render path: an absent/empty lens must yield an empty list, not throw).
function reviewFindingsFrom(lenses) {
  const contributors = (lenses && lenses.contributors) || [];
  const review = contributors.find(c => c.skill === 'review');
  return (review && review.findings) || [];
}

function renderReviewFindings(data) {
  const tbody = document.getElementById('review-findings-tbody');
  if (!tbody) return;
  const rows = reviewFindingsFrom(data && data.lenses);
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No review findings recorded.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const sev = r.severity || 'minor';
    return html`<tr>
      <td>${safe(renderMarkdown(r.issue))}</td>
      <td><span class="review-severity review-severity-${sev}">${sev}</span></td>
      <td>${r.foundIn || '—'}</td>
      <td>${safe(renderMarkdown(r.resolution || '—'))}</td>
    </tr>`;
  }).join('');
}

// Pure lookup: the friction lens is a contributor named "friction" in
// data.lenses.contributors. Kept separate from the DOM-touching renderer so it is
// unit-testable without a document shim (Airplane Test: an absent lens must yield an
// empty list, not throw — the friction table then degrades to its empty-state).
function frictionEntriesFrom(lenses) {
  const contributors = (lenses && lenses.contributors) || [];
  const friction = contributors.find(c => c.skill === 'friction');
  return (friction && friction.entries) || [];
}

function renderFriction(data) {
  const tbody = document.getElementById('friction-tbody');
  if (!tbody) return;
  const rows = frictionEntriesFrom(data && data.lenses);
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No friction recorded.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r =>
    html`<tr>
      <td>${safe(renderMarkdown(r.friction))}</td>
      <td>${safe(renderMarkdown(r.impact))}</td>
      <td><span class="friction-type friction-${r.type || ''}">${r.type || '—'}</span></td>
    </tr>`
  ).join('');
}

// Pure lookup: the deterministic repo diff surface lives in data.repoDiffs (loaded from
// repo-diffs.json by render_html). Kept separate from the DOM renderer so it is unit-testable
// without a document shim (Airplane Test: an absent artifact must yield empty buckets, not
// throw — the Diff tab then degrades to its empty-state instead of blanking the report).
function diffReposFrom(data) {
  const rd = (data && data.repoDiffs) || {};
  return { repos: rd.repos || [], skipped: rd.skipped || [], errors: rd.errors || [] };
}

function renderDiff(data) {
  const body = document.getElementById('diff-body');
  if (!body) return;

  const { repos, skipped, errors } = diffReposFrom(data);
  if (repos.length === 0 && skipped.length === 0 && errors.length === 0) {
    body.innerHTML = '<p class="empty-state">No repo diffs recorded.</p>';
    return;
  }

  let out = '';

  for (const repo of repos) {
    const files = repo.files || [];
    const filesHtml = files.length === 0
      ? html`<li class="empty-state">No files recorded.</li>`
      : files.map(f => html`<li>${safe(pathLink(f))}</li>`).join('');
    const statHtml = repo.stat
      ? html`<pre class="code-block">${repo.stat}</pre>`
      : '';
    out += html`<div class="diff-repo">
      <h3 class="section-subheading">${repo.repoRoot} @ ${repo.branch}</h3>
      <p class="diff-repo-meta">base ${repo.base} → ${repo.baseResolved ? repo.baseResolved.slice(0, 9) : '?'} · +${repo.insertions} −${repo.deletions} · ${repo.filesChanged} file(s)</p>
      <ul class="files-changed-list">${safe(filesHtml)}</ul>
      ${safe(statHtml)}
    </div>`;
  }

  for (const s of skipped) {
    out += html`<p class="empty-state">Skipped: ${s.repoRoot} — ${s.reason}</p>`;
  }

  // Never swallow a diff failure — surface it visibly (Sensor).
  for (const e of errors) {
    out += html`<div class="lens-fail">diff failed · ${e.repoRoot} — ${e.error}</div>`;
  }

  body.innerHTML = out;
}

// Pure lookup: the repo-improvements lens is a contributor named "repo-improvements" in
// data.lenses.contributors. Kept separate from the DOM-touching renderer so it is
// unit-testable without a document shim (Airplane Test: an absent lens must yield an
// empty list, not throw — the Repo Improvements tab then degrades to its empty-state).
function repoImprovementsFrom(lenses) {
  const contributors = (lenses && lenses.contributors) || [];
  const repo = contributors.find(c => c.skill === 'repo-improvements');
  return (repo && repo.items) || [];
}

// Pure lookup: the user-improvements lens is a contributor named "user-improvements" in
// data.lenses.contributors. Returns the whole contributor record (or null) rather than
// just `.items`, because `promptPattern` lives on the SAME record and both the User
// Improvements list and the prompt-pattern block read from this one lookup (Airplane
// Test: an absent lens must yield null, not throw).
function userImprovementsFrom(lenses) {
  const contributors = (lenses && lenses.contributors) || [];
  return contributors.find(c => c.skill === 'user-improvements') || null;
}

// One improvement item — a plain string or a {title, detail} record. Shared by both the
// repo and user improvement lists so the string-vs-record handling lives in one place.
function improvementItem(item) {
  if (typeof item === 'string') return html`<li>${safe(renderMarkdown(item))}</li>`;
  return html`<li><strong>${item.title || ''}</strong>${safe(item.detail ? `<br><span class="improvement-detail">${renderMarkdown(item.detail)}</span>` : '')}</li>`;
}

function improvementList(items) {
  return items.length > 0
    ? items.map(improvementItem).join('')
    : '<li class="empty-state">No improvements recorded.</li>';
}

function renderImprovements(data) {
  const repoEl = document.getElementById('repo-improvements-list');
  if (repoEl) {
    repoEl.innerHTML = improvementList(repoImprovementsFrom(data && data.lenses));
  }
  const userEl = document.getElementById('user-improvements-list');
  if (userEl) {
    const userLens = userImprovementsFrom(data && data.lenses);
    userEl.innerHTML = improvementList((userLens && userLens.items) || []);
  }
}

function renderPromptPattern(data) {
  const area = document.getElementById('prompt-pattern-area');
  const pre = document.getElementById('prompt-pattern');
  const userLens = userImprovementsFrom(data && data.lenses);
  const pattern = userLens && userLens.promptPattern;
  if (area && pattern) {
    area.style.display = 'block';
    if (pre) pre.textContent = pattern;
  } else if (area) {
    area.style.display = 'none';
  }
}

function isSafePath(path) {
  if (/^\/\//.test(path)) return false;
  return /^https?:\/\//i.test(path) || /^\.{0,2}\//.test(path) || /^[^:]+$/.test(path);
}

// Raw .jsonl files are excluded from the pack/zip; the transcript ships as the
// rendered transcript.html. Map the link target so the artifact is not a dead link.
function artifactHref(p) {
  return p === 'transcript.jsonl' ? 'transcript.html' : p;
}
// Linkable only if safe AND bundled — a .jsonl other than the transcript is not shipped.
function artifactLinkable(p) {
  return isSafePath(p) && (!p.endsWith('.jsonl') || p === 'transcript.jsonl');
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
    if (item.path && artifactLinkable(item.path)) {
      return html`<li><a href="${artifactHref(item.path)}" target="_blank">${item.name || item.label || item.path}</a></li>`;
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

// Resolved eval-pack config (branding, subjectNoun, link templates). Set in renderSession.
let EVAL_CONFIG = {};

// Reject dangerous URL schemes from config-supplied link templates; allow http(s)/relative.
function safeUrl(u) {
  if (typeof u !== 'string' || !u) return '';
  if (/^\s*(javascript|data|vbscript):/i.test(u)) return '';
  return u;
}

// Linkify a repo-relative file path against repoBaseUrl, or render it as plain code.
function pathLink(path) {
  const base = EVAL_CONFIG.repoBaseUrl;
  const url = base ? safeUrl(base.replace(/\/$/, '') + '/' + path) : '';
  if (url) return html`<a href="${url}"><code>${path}</code></a>`;
  return html`<code>${path}</code>`;
}

// Honor configured section toggle/order: hide unlisted tabs, reorder to match, activate first.
function applySections(data) {
  const order = (data.evalConfig || {}).sections || [];
  if (!order.length) return;  // empty = default set/order
  const nav = document.getElementById('tab-nav');
  if (!nav) return;
  const btns = Array.from(nav.querySelectorAll('.tab-btn'));
  const actions = nav.querySelector('.tab-nav-actions');
  // The legacy 'lenses' token now stands for the whole group of dynamically-injected
  // per-lens tabs (data-panel="lens-*"); it's "known" iff any such button exists.
  const lensBtns = btns.filter(b => (b.dataset.panel || '').startsWith('lens-'));
  const isLensGroup = panel => panel === 'lenses';
  const matchesOrder = b => order.includes(b.dataset.panel) ||
    (order.includes('lenses') && lensBtns.includes(b));
  const known = order.filter(panel =>
    isLensGroup(panel) ? lensBtns.length : btns.some(b => b.dataset.panel === panel));
  // All-unknown list: leave the default nav intact rather than hiding every tab.
  if (!known.length) return;
  btns.forEach(b => {
    if (!matchesOrder(b)) b.style.display = 'none';
  });
  known.forEach(panel => {
    if (isLensGroup(panel)) {
      // Move the lens buttons as a contiguous group to the 'lenses' token's position.
      lensBtns.forEach(btn => nav.insertBefore(btn, actions || null));
      return;
    }
    const btn = btns.find(b => b.dataset.panel === panel);
    if (btn) nav.insertBefore(btn, actions || null);
  });
  activatePanel(isLensGroup(known[0]) ? (lensBtns[0].dataset.panel) : known[0]);
}

function renderBranding(data) {
  const cfg = data.evalConfig || {};
  EVAL_CONFIG = cfg;

  if (cfg.brandName) {
    const logo = document.querySelector('.logo');
    if (logo) logo.textContent = cfg.brandName;
  }

  const a = data.analysis || {};
  document.title = cfg.reportTitle || a.title || cfg.brandName || 'Eval Pack';

  const noun = cfg.subjectNoun;
  if (noun && noun !== 'extension') {
    document.querySelectorAll('.three-col-heading').forEach(h => {
      h.textContent = h.textContent.replace(/\bextension\b/, noun);
    });
  }

  // footerText overrides the brand span only — NOT the whole footer — so the version
  // stamp and generated-at timestamp always survive.
  if (cfg.footerText) {
    const brand = document.getElementById('footer-brand');
    if (brand) brand.textContent = cfg.footerText;
  }

  // Stamp the eval-pack version that produced this report.
  const ver = document.getElementById('eval-pack-version');
  if (ver && data.evalPackVersion) ver.textContent = `eval-pack v${data.evalPackVersion}`;
}

// messages: override any labeled UI string by element id, e.g. {"page-title":"…"} (i18n hook).
// Applied LAST, after every renderer, so a specific string (e.g. page-title) isn't clobbered.
function applyMessages(data) {
  const messages = (data.evalConfig || {}).messages || {};
  Object.keys(messages).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = messages[id];
  });
}

// Display a lens score defensively: a finite number clamped to [0,100], else an em dash.
function lensScore(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : '—';
}

// Verdict-facing confidence: when scorer lenses ran under a non-core rule, the aggregated
// finalScore IS the confidence a user should lead with (finding: cosmetic finalScore).
function effectiveConfidence(analysis, lenses) {
  const core = ((analysis || {}).highlights || {}).confidencePercent;
  const l = lenses || {};
  const scorers = l.scorers || [];
  if (l.rule && l.rule !== 'core' && scorers.length && l.finalScore != null) {
    return { value: l.finalScore,
             note: `${l.rule} of core ${l.coreScore} and ${scorers.length} scorer lens(es)` };
  }
  return { value: core != null ? core : null, note: null };
}

// A lens finding may be a plain string or a shaped object — render every known shape
// readably, and degrade unknown objects to "key: value" lines, never raw JSON.
function lensFindingText(f) {
  if (typeof f === 'string') return f;
  if (f && typeof f === 'object') {
    // verification-rigor shape: {claim, backed, evidence}
    if (f.claim != null) {
      const mark = f.backed === true ? '✓' : f.backed === false ? '✗' : '•';
      const ev = f.evidence && f.evidence !== 'none' ? ` — ${f.evidence}` : '';
      return `${mark} ${f.claim}${ev}`;
    }
    // requirement-drift shape: {type, detail}
    const detail = f.detail != null ? String(f.detail) : '';
    if (f.type || detail) return f.type ? `${f.type}: ${detail}` : detail;
    // unknown object: readable key-value join, not JSON
    return Object.entries(f).map(([k, v]) => `${k}: ${String(v)}`).join(' · ');
  }
  return String(f);
}

// Resolve a dot-path into a lens record.
function lensPath(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function lensValueText(v) {
  if (v == null) return '';
  return typeof v === 'object' ? lensFindingText(v) : String(v);
}

// Render a repo-authored lens template (mustache-lite). The MARKUP is trusted — it came
// from a repo file, resolve-time confined — but every interpolated VALUE is untrusted LLM
// output and is ALWAYS escaped. Supported: {{field}} / {{dot.path}} (escaped value),
// {{#arrayField}}...{{/arrayField}} (repeat per item, one level), {{.}} (the item, via
// lensFindingText, escaped). Unknown fields render as empty strings.
function renderLensTemplate(tpl, data) {
  let out = tpl.replace(/\{\{#([\w.]+)\}\}([\s\S]*?)\{\{\/\1\}\}/g, (m, key, body) => {
    const arr = lensPath(data, key);
    if (!Array.isArray(arr)) return '';
    return arr.map(item => body
      .replace(/\{\{\.\}\}/g, escapeHtml(lensFindingText(item)))
      .replace(/\{\{([\w.]+)\}\}/g, (mm, k) => escapeHtml(lensValueText(lensPath(item, k))))
    ).join('');
  });
  return out.replace(/\{\{([\w.]+)\}\}/g, (m, k) => escapeHtml(lensValueText(lensPath(data, k))));
}

// Contributors that render in their own dedicated tab/table — excluded from the generic
// Lenses list to avoid double-rendering. Grows as dimensions are extracted into lenses.
const DEDICATED_CONTRIBUTORS = new Set(['review', 'business-risk', 'friction', 'repo-improvements', 'user-improvements']);

// Slugify a skill name into a stable, id-safe token (fallback 'lens' when empty).
function lensSlug(skill) {
  const s = String(skill == null ? '' : skill).toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return s || 'lens';
}

// Title-case a skill name for a tab label (fallback 'Lens' when empty).
function lensTabLabel(skill) {
  const words = String(skill == null ? '' : skill).split(/[-_\s]+/).filter(Boolean)
    .map(w => w[0].toUpperCase() + w.slice(1));
  return words.length ? words.join(' ') : 'Lens';
}

// PURE lookup (separate from the DOM renderer, matching this file's lens idiom): which
// lenses should each get their own nav tab, and in what order. Scorers first, then
// non-dedicated contributors (dedicated ones own their hardcoded tabs), then failures.
// Airplane Test: absent/empty lenses → [], never throws on missing arrays.
function lensTabsFrom(lenses) {
  const l = lenses || {};
  const records = [];
  (l.scorers || []).forEach(r => records.push({ kind: 'scorer', record: r }));
  (l.contributors || []).forEach(r => {
    if (DEDICATED_CONTRIBUTORS.has(r.skill)) return;
    records.push({ kind: 'contributor', record: r });
  });
  (l.failures || []).forEach(r => records.push({ kind: 'failure', record: r }));

  const seen = new Map();  // panelId → count, to de-dupe colliding slugs
  return records.map(({ kind, record }) => {
    const id = lensSlug(record.skill);
    let panelId = 'lens-' + id;
    const n = (seen.get(panelId) || 0) + 1;
    seen.set(panelId, n);
    if (n > 1) panelId = `${panelId}-${n}`;
    const label = (typeof record.title === 'string' && record.title)
      ? record.title : lensTabLabel(record.skill);
    return { id, panelId, label, kind, record };
  });
}

// A record with a repo-authored templateHtml renders via the mustache-lite interpolator
// (markup trusted, values escaped); on interpolation failure fall back to a VISIBLE
// failure card rather than a blank/broken one.
function lensCustomCard(rec, headExtra) {
  try {
    return html`<div class="lens-card lens-custom"><div class="lens-head"><span class="lens-meta">${rec.role} · ${rec.skill}</span>${safe(headExtra || '')}</div>${safe(renderLensTemplate(rec.templateHtml, rec))}</div>`;
  } catch (e) {
    return html`<div class="lens-card lens-fail"><div class="lens-meta">template failed · ${rec.skill}</div><p>${String(e)}</p></div>`;
  }
}

// The lens card markup for one tab's panel body — dispatched by kind. Uses the html`` tag
// (not safe() in plain literals — that stringifies to "[object Object]"). html`` escapes
// each interpolation, which is what we want for untrusted lens output (skill names,
// rationales, findings, error text).
function lensCardMarkup(tab) {
  const rec = tab.record;
  if (tab.kind === 'scorer') {
    if (rec.templateHtml) return lensCustomCard(rec, html`<span class="lens-score">${lensScore(rec.score)}</span>`);
    const findings = (rec.findings || []).map(f => html`<li>${lensFindingText(f)}</li>`).join('');
    return html`<div class="lens-card"><div class="lens-head"><span class="lens-meta">scorer · ${rec.skill}</span><span class="lens-score">${lensScore(rec.score)}</span></div><p class="lens-rationale">${rec.rationale}</p>${safe(findings ? html`<ul class="lens-findings">${safe(findings)}</ul>` : '')}</div>`;
  }
  if (tab.kind === 'contributor') {
    if (rec.templateHtml) return lensCustomCard(rec);
    const findings = (rec.findings || []).map(f => html`<li>${lensFindingText(f)}</li>`).join('');
    return html`<div class="lens-card"><div class="lens-head"><span class="lens-meta">contributor · ${rec.skill}</span></div><h4>${rec.title}</h4><ul class="lens-findings">${safe(findings)}</ul></div>`;
  }
  // failure
  return html`<div class="lens-card lens-fail"><div class="lens-meta">failed · ${rec.skill}</div><p>${rec.error}</p></div>`;
}

function renderLenses(data) {
  const tabs = lensTabsFrom(data.lenses);
  const nav = document.getElementById('tab-nav');
  const actions = nav.querySelector('.tab-nav-actions');
  const sessionArtifacts = document.getElementById('session-artifacts');
  const panelsParent = sessionArtifacts.parentNode;
  // No surfaced lenses → no lens tabs at all (the old code hid an empty shared tab).
  if (!tabs.length) return;

  tabs.forEach((t, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.dataset.panel = t.panelId;
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', 'false');
    btn.textContent = t.label;
    nav.insertBefore(btn, actions || null);

    const section = document.createElement('section');
    section.className = 'tab-panel card';
    section.id = 'panel-' + t.panelId;
    section.setAttribute('role', 'tabpanel');
    section.style.display = 'none';
    let inner = lensCardMarkup(t);
    // Aggregation transparency — the core X → final Y math must stay visible exactly once;
    // prepend it to the first generated panel (verbatim markup preserved).
    if (i === 0 && data.lenses.finalScore != null) {
      inner = html`<p class="lens-agg">Verdict aggregation — core <strong>${lensScore(data.lenses.coreScore)}</strong> <code>${data.lenses.rule}</code> lenses → final <strong>${lensScore(data.lenses.finalScore)}</strong></p>` + inner;
    }
    section.innerHTML = inner;
    panelsParent.insertBefore(section, sessionArtifacts);
  });
  // Click handlers are NOT attached here: init() wires every .tab-btn after renderSession
  // (which calls renderLenses) runs, so these injected buttons are present in time.
}

function renderSession(data) {
  const analysis = data.analysis || {};
  renderDisabledBanner(analysis);

  renderBranding(data);
  renderPageHeader(data);
  renderHighlights(analysis, data.lenses);
  renderVerdict(data);
  renderStats(data);
  renderFlags(data);
  renderSummary(data);
  renderProof(data);
  renderTests(data);
  renderReviewFindings(data);
  renderFriction(data);
  renderDiff(data);
  renderTools(data.tools);
  renderImprovements(data);
  renderPromptPattern(data);
  renderSessionArtifacts(analysis);
  renderVerdictStatement(analysis);
  renderTimeline(analysis);
  renderLenses(data);
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
  const cfgTheme = (data.evalConfig || {}).defaultTheme;
  if (savedTheme) {
    document.documentElement.dataset.theme = savedTheme;
  } else if (cfgTheme === 'system') {
    const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    document.documentElement.dataset.theme = prefersLight ? 'light' : 'dark';
  } else if (cfgTheme === 'light' || cfgTheme === 'dark') {
    document.documentElement.dataset.theme = cfgTheme;
  }

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

  // Apply configured section toggle/order (overrides the default activation above)
  applySections(data);

  // Apply message overrides LAST so they win over every renderer's default text.
  applyMessages(data);
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
  module.exports = { screenshotBadge, wrapIndex, zoomAt, computeBaseFit, artifactHref, artifactLinkable, effectiveConfidence, lensFindingText, renderLensTemplate, lensPath, lensValueText, reviewFindingsFrom, businessRiskFrom, frictionEntriesFrom, diffReposFrom, repoImprovementsFrom, userImprovementsFrom, deliveredFrom, unmetFrom, provenFrom, unprovenFrom, testResultsSummary, renderImprovements, renderPromptPattern, lensTabsFrom };
}
