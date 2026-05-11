(async function () {
  const resp = await fetch('data.json');
  const data = await resp.json();

  const currentRound = data.rounds ? data.rounds.length - 1 : 0;
  let activeRound = currentRound;

  function getRound(idx) {
    if (data.rounds) return data.rounds[idx];
    return data;
  }

  // Theme toggle
  const toggle = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('eval-pack-theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

  toggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('eval-pack-theme', next);
  });

  // Session ID
  document.getElementById('session-id').textContent = data.sessionId || '';
  document.getElementById('generated-at').textContent = data.generatedAt || '';

  function renderRound(roundIdx) {
    const round = getRound(roundIdx);
    const metrics = round.metrics || {};
    const patterns = round.patterns || {};
    const analysis = round.analysis || {};
    const testResults = round.testResults || {};

    // Verdict
    const banner = document.getElementById('verdict-banner');
    const icon = document.getElementById('verdict-icon');
    const text = document.getElementById('verdict-text');
    const detail = document.getElementById('verdict-detail');

    banner.className = 'verdict-banner';
    if (testResults.verdict === 'pass') {
      banner.classList.add('pass');
      icon.textContent = '\u2713';
      text.textContent = 'All Tests Passed';
      detail.textContent = testResults.summary || '';
    } else if (testResults.verdict === 'fail') {
      banner.classList.add('fail');
      icon.textContent = '\u2717';
      text.textContent = 'Tests Failed';
      detail.textContent = testResults.summary || '';
    } else {
      banner.classList.add('unknown');
      icon.textContent = '?';
      text.textContent = 'No Tests Ran';
      detail.textContent = 'Agent did not execute tests for this session';
    }

    // Stats — note: metrics field is lastModel (not model)
    const statsRow = document.getElementById('stats-row');
    const stats = [
      { value: metrics.lastModel || 'N/A', label: 'Model' },
      { value: formatNumber(metrics.totalTokens), label: 'Total Tokens' },
      { value: metrics.turnCount || 0, label: 'Turns' },
      { value: formatDuration(metrics.firstTimestamp, metrics.lastTimestamp), label: 'Duration' },
      { value: metrics.filesChanged || 0, label: 'Files Changed' },
      { value: `+${metrics.insertions || 0} / -${metrics.deletions || 0}`, label: 'Lines' },
    ];
    statsRow.innerHTML = stats.map(s =>
      `<div class="stat-item"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`
    ).join('');

    // Flags
    const flagsRow = document.getElementById('flags-row');
    const flags = patterns.flags || [];
    flagsRow.innerHTML = flags.map(f => {
      const countStr = f.count ? ` (${f.count})` : '';
      return `<span class="flag-chip ${f.level}">${f.label}${countStr}</span>`;
    }).join('');

    // Analysis
    const analysisSection = document.getElementById('analysis-section');
    if (analysis.retrospective || analysis.friction || analysis.promptQuality) {
      analysisSection.style.display = '';
      document.getElementById('tab-retrospective').innerHTML = renderMarkdown(analysis.retrospective || 'No retrospective available.');
      document.getElementById('tab-friction').innerHTML = renderMarkdown(analysis.friction || 'No friction report available.');
      document.getElementById('tab-prompt').innerHTML = renderMarkdown(analysis.promptQuality || 'No prompt quality analysis available.');
    }

    // Screenshots
    renderScreenshots(round.screenshots || []);
  }

  // Screenshots
  function renderScreenshots(screenshots) {
    const section = document.getElementById('screenshots-section');
    const grid = document.getElementById('screenshot-grid');
    if (screenshots.length === 0) { section.style.display = 'none'; return; }
    section.style.display = '';
    grid.innerHTML = '';
    screenshots.forEach(s => {
      const item = document.createElement('div');
      item.className = 'screenshot-item';
      item.dataset.path = s.path;
      const img = document.createElement('img');
      img.src = s.path;
      img.alt = s.label || '';
      img.loading = 'lazy';
      const label = document.createElement('div');
      label.className = 'screenshot-label';
      label.textContent = s.label || '';
      item.appendChild(img);
      item.appendChild(label);
      item.addEventListener('click', () => showModal(s.path));
      grid.appendChild(item);
    });
  }

  // Screenshot modal
  window.showModal = function (src) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const img = document.createElement('img');
    img.src = src;
    overlay.appendChild(img);
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  };

  // Tabs
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
      tab.classList.add('active');
      document.getElementById(`tab-${tab.dataset.tab}`).style.display = '';
    });
  });

  // Transcript
  function renderTranscript() {
    const container = document.getElementById('transcript-container');
    const transcript = data.transcript || [];
    container.innerHTML = transcript.map(turn => {
      const role = turn.type || 'unknown';
      const ts = turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString() : '';
      const content = escapeHtml(typeof turn.content === 'string' ? turn.content : JSON.stringify(turn.content, null, 2));
      return `<div class="turn ${role}">
        <div class="turn-header">
          <span class="turn-role">${role}</span>
          <span>${ts}</span>
        </div>
        <div class="turn-content">${content}</div>
      </div>`;
    }).join('');
  }

  // Rounds
  function renderRounds() {
    if (!data.rounds || data.rounds.length <= 1) return;
    const section = document.getElementById('rounds-section');
    section.style.display = '';
    const nav = document.getElementById('rounds-nav');
    nav.innerHTML = data.rounds.map((_, i) =>
      `<button class="round-btn ${i === activeRound ? 'active' : ''}" data-round="${i}">Round ${i + 1}</button>`
    ).join('');
    nav.querySelectorAll('.round-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        activeRound = parseInt(btn.dataset.round);
        renderRound(activeRound);
        renderRounds();
      });
    });
  }

  // Timeline (phase-level)
  function renderTimeline() {
    const bar = document.getElementById('timeline-bar');
    const legend = document.getElementById('timeline-legend');
    const phases = data.phases || [
      { name: 'Understanding', className: 'understanding', weight: 15 },
      { name: 'Planning', className: 'planning', weight: 10 },
      { name: 'Implementation', className: 'implementation', weight: 45 },
      { name: 'Testing', className: 'testing', weight: 20 },
      { name: 'Fixing', className: 'fixing', weight: 10 },
    ];
    bar.innerHTML = phases.map(p =>
      `<div class="timeline-segment ${p.className}" style="flex:${p.weight}">${p.name}</div>`
    ).join('');
    legend.innerHTML = phases.map(p =>
      `<div class="legend-item"><div class="legend-dot" style="background:var(--${getPhaseColor(p.className)})"></div>${p.name}</div>`
    ).join('');
  }

  // Helpers
  function formatNumber(n) {
    if (n == null) return 'N/A';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function formatDuration(start, end) {
    if (!start || !end) return 'N/A';
    const ms = new Date(end) - new Date(start);
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderMarkdown(text) {
    return escapeHtml(text)
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  function getPhaseColor(className) {
    const map = { understanding: 'accent', planning: 'accent', implementation: 'green', testing: 'amber', fixing: 'red' };
    return map[className] || 'accent';
  }

  // Init
  renderRound(activeRound);
  renderTranscript();
  renderRounds();
  renderTimeline();
})();
