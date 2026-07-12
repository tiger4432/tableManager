// Helper to get local time string in YYYY-MM-DD HH:MM:SS format
export function getLocalTimeString(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const yyyy = date.getFullYear();
  const MM = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = date.getHours();
  const mm = pad(date.getMinutes());
  const ss = pad(date.getSeconds());
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`;
}

// Premium Toast Notification Helper
export function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  else if (type === 'error') icon = '❌';
  else if (type === 'warning') icon = '⚠️';

  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${icon}</span>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  // Auto remove toast after 5 seconds
  setTimeout(() => {
    toast.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    toast.style.animation = 'none';
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-20px) scale(0.9)';

    setTimeout(() => {
      toast.remove();
      if (container.children.length === 0) {
        container.remove();
      }
    }, 400);
  }, 5000);
}

// Helper to strip user prefix and unique UUID suffixes from filename in client
export function getCleanFilename(filename) {
  if (!filename) return '';
  let clean = filename.replace(/^user\([^)]+\)_/, '');
  const lastDotIdx = clean.lastIndexOf('.');
  if (lastDotIdx !== -1) {
    let name = clean.slice(0, lastDotIdx);
    const ext = clean.slice(lastDotIdx);
    name = name.replace(/_[0-9a-fA-F]{8}$/, '');
    clean = name + ext;
  } else {
    clean = clean.replace(/_[0-9a-fA-F]{8}$/, '');
  }
  return clean;
}

// Floating Ingestion Progress Widget Helper
export function showIngestionProgress(tableName, filename, progress, processedRows, totalRows) {
  let container = document.getElementById('ingestion-progress-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'ingestion-progress-container';
    document.body.appendChild(container);
  }

  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  let card = document.getElementById(cardId);

  if (!card) {
    card = document.createElement('div');
    card.id = cardId;
    card.className = 'progress-card';
    container.appendChild(card);
  }

  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  const p = parseInt(progress, 10) || 0;
  const pr = parseInt(processedRows, 10) || 0;
  const tr = parseInt(totalRows, 10) || 0;

  card.innerHTML = `
    <div class="progress-header">
      <span class="progress-title">📤 파일 파싱 및 적재 중</span>
      <span class="progress-percent">${p}%</span>
    </div>
    <div class="progress-filename" title="${cleanFilename}">${cleanFilename}</div>
    <div class="progress-bar-container">
      <div class="progress-bar" style="width: ${p}%;"></div>
    </div>
    <div class="progress-stats">${pr.toLocaleString()} / ${tr.toLocaleString()} 행 처리됨</div>
  `;

  const isComplete = p >= 100 || (tr > 0 && pr >= tr);
  if (isComplete) {
    card.classList.add('status-auto-dismiss');
    card.classList.add('status-success');

    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';

    setTimeout(() => {
      card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
      card.style.animation = 'none';
      card.style.opacity = '0';
      card.style.transform = 'translateY(20px) scale(0.9)';

      setTimeout(() => {
        card.remove();
        const container = document.getElementById('ingestion-progress-container');
        if (container && container.children.length === 0) {
          container.remove();
        }
      }, 400);
    }, 2500);
  }
}

export function finishIngestionProgress(tableName, filename, status, errorMsg = null) {
  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  card.classList.add('status-auto-dismiss');

  if (status === 'SUCCESS') {
    card.classList.add('status-success');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';
  } else {
    card.classList.add('status-error');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '❌ 파일 적재 실패';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = errorMsg ? errorMsg.slice(0, 50) : '처리 중 예외 발생';
  }

  setTimeout(() => {
    card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    card.style.animation = 'none';
    card.style.opacity = '0';
    card.style.transform = 'translateY(20px) scale(0.9)';

    setTimeout(() => {
      card.remove();
      const container = document.getElementById('ingestion-progress-container');
      if (container && container.children.length === 0) {
        container.remove();
      }
    }, 400);
  }, 2500);
}

// Expose on window object dynamically for any non-ESM environment components if needed
window.showToast = showToast;
