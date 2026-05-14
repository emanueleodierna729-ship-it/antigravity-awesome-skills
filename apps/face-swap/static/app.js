'use strict';

// ---- State ----
const state = {
  sourceFile: null,
  targetFile: null,
  sourcePath: null,
  targetPath: null,
  isVideo: false,
  jobId: null,
  resultFilename: null,
  pollInterval: null,
};

// ---- System monitor ----
async function updateSystemInfo() {
  try {
    const res = await fetch('/system');
    if (!res.ok) return;
    const d = await res.json();

    document.getElementById('cpuText').textContent = `CPU ${d.cpu_percent.toFixed(0)}%`;
    document.getElementById('ramText').textContent = `RAM ${d.ram_percent.toFixed(0)}%`;

    const gpuEl = document.getElementById('gpuText');
    const gpuItem = document.getElementById('sysGpu');
    if (d.gpu && d.gpu !== 'No GPU') {
      const name = d.gpu.split('|')[0].trim();
      gpuEl.textContent = name.length > 20 ? name.slice(0, 18) + '…' : name;
      gpuItem.style.color = '#a78bfa';
    } else {
      gpuEl.textContent = 'CPU mode';
      gpuItem.style.color = '#64748b';
    }

    const dot = document.getElementById('modelDot');
    const modelText = document.getElementById('modelText');
    const banner = document.getElementById('modelBanner');
    if (d.model_ready) {
      dot.className = 'status-dot ok';
      modelText.textContent = 'Modello OK';
      banner.style.display = 'none';
    } else {
      dot.className = 'status-dot warn';
      modelText.textContent = 'Modello mancante';
      banner.style.display = 'flex';
    }
  } catch (_) {}
}

setInterval(updateSystemInfo, 5000);
updateSystemInfo();

// ---- Drag & Drop helpers ----
function onDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}
function onDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}
function onDropSource(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleSourceFile(file);
}
function onDropTarget(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleTargetFile(file);
}
function onSourceFileSelected(e) {
  const file = e.target.files[0];
  if (file) handleSourceFile(file);
}
function onTargetFileSelected(e) {
  const file = e.target.files[0];
  if (file) handleTargetFile(file);
}

// ---- Source file handling ----
function handleSourceFile(file) {
  if (!file.type.startsWith('image/')) {
    showToast('La sorgente deve essere un\'immagine.', 'error');
    return;
  }
  state.sourceFile = file;

  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('sourceImg').src = e.target.result;
    document.getElementById('sourceContent').style.display = 'none';
    document.getElementById('sourcePreview').style.display = 'flex';
  };
  reader.readAsDataURL(file);

  uploadSource(file);
  updateSwapButton();
}

async function uploadSource(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/upload/source', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();
    state.sourcePath = d.path;
    document.getElementById('sourceFaceBadge').style.display = 'flex';
    updateSwapButton();
  } catch (err) {
    showToast('Errore caricamento sorgente: ' + err.message, 'error');
  }
}

// ---- Target file handling ----
function handleTargetFile(file) {
  const isVideo = file.type.startsWith('video/');
  const isImage = file.type.startsWith('image/');
  if (!isVideo && !isImage) {
    showToast('Formato non supportato.', 'error');
    return;
  }

  state.targetFile = file;
  state.isVideo = isVideo;

  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('targetContent').style.display = 'none';
    const preview = document.getElementById('targetPreview');
    preview.style.display = 'flex';

    if (isVideo) {
      const vid = document.getElementById('targetVideo');
      vid.src = e.target.result;
      vid.style.display = 'block';
      document.getElementById('targetImg').style.display = 'none';
    } else {
      const img = document.getElementById('targetImg');
      img.src = e.target.result;
      img.style.display = 'block';
      document.getElementById('targetVideo').style.display = 'none';
    }
  };
  reader.readAsDataURL(file);

  // Media type badge
  const badge = document.getElementById('mediaTypeBadge');
  badge.style.display = 'block';
  document.getElementById('mediaTypeText').textContent = isVideo ? 'VIDEO' : 'IMMAGINE';

  // Video info chips
  const info = document.getElementById('videoInfo');
  const name = document.getElementById('infoName');
  const sizeEl = document.getElementById('infoSize');
  name.textContent = file.name.length > 30 ? file.name.slice(0, 28) + '…' : file.name;
  sizeEl.textContent = formatBytes(file.size);
  info.style.display = 'flex';

  if (isVideo) {
    const tmp = document.createElement('video');
    tmp.preload = 'metadata';
    tmp.onloadedmetadata = () => {
      const dur = tmp.duration;
      document.getElementById('infoDuration').textContent = formatDuration(dur);
      URL.revokeObjectURL(tmp.src);
    };
    tmp.src = URL.createObjectURL(file);
  } else {
    document.getElementById('infoDuration').textContent = '';
  }

  uploadTarget(file, isVideo);
  updateSwapButton();
}

async function uploadTarget(file, isVideo) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/upload/target', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();
    state.targetPath = d.path;
    updateSwapButton();
  } catch (err) {
    showToast('Errore caricamento target: ' + err.message, 'error');
  }
}

// ---- Clear functions ----
function clearSource(e) {
  e.stopPropagation();
  state.sourceFile = null;
  state.sourcePath = null;
  document.getElementById('sourcePreview').style.display = 'none';
  document.getElementById('sourceContent').style.display = 'flex';
  document.getElementById('sourceFaceBadge').style.display = 'none';
  document.getElementById('sourceInput').value = '';
  updateSwapButton();
}

function clearTarget(e) {
  e.stopPropagation();
  state.targetFile = null;
  state.targetPath = null;
  state.isVideo = false;
  document.getElementById('targetPreview').style.display = 'none';
  document.getElementById('targetContent').style.display = 'flex';
  document.getElementById('mediaTypeBadge').style.display = 'none';
  document.getElementById('videoInfo').style.display = 'none';
  document.getElementById('targetInput').value = '';
  document.getElementById('targetVideo').src = '';
  document.getElementById('targetImg').src = '';
  updateSwapButton();
}

// ---- Swap button state ----
function updateSwapButton() {
  const ready = !!(state.sourcePath && state.targetPath);
  document.getElementById('btnSwap').disabled = !ready;
}

// ---- Start swap ----
async function startSwap() {
  if (!state.sourcePath || !state.targetPath) return;

  resetProgress();
  showSection('progress');

  try {
    const res = await fetch(
      `/swap?source_path=${encodeURIComponent(state.sourcePath)}&target_path=${encodeURIComponent(state.targetPath)}&is_video=${state.isVideo}`,
      { method: 'POST' }
    );
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();
    state.jobId = d.job_id;
    pollJob(state.jobId);
  } catch (err) {
    showError('Impossibile avviare il job: ' + err.message);
  }
}

function pollJob(jobId) {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/job/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();
      updateProgress(job);

      if (job.status === 'done' || job.status === 'error') {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
        if (job.status === 'done') showResult(job);
        else showError(job.error || 'Errore sconosciuto');
      }
    } catch (_) {}
  }, 800);
}

function updateProgress(job) {
  const pct = job.progress || 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressPct').textContent = pct + '%';

  let sub = 'Elaborazione in corso…';
  if (job.status === 'queued') sub = 'In coda…';
  else if (pct < 15) sub = 'Caricamento modelli AI…';
  else if (pct < 40) sub = 'Rilevamento viso sorgente…';
  else if (pct < 70) sub = 'Analisi visi nel target…';
  else if (pct < 90) sub = 'Applicazione face swap…';
  else sub = 'Finalizzazione output…';

  if (job.is_video && job.frames_done != null && job.total_frames > 0) {
    sub = `Frame ${job.frames_done} / ${job.total_frames} — ${sub}`;
  }
  document.getElementById('progressSub').textContent = sub;
}

// ---- Result ----
function showResult(job) {
  state.resultFilename = job.output;
  const url = `/download/${job.output}`;
  showSection('result');

  if (job.is_video) {
    const vid = document.getElementById('resultVideo');
    vid.src = url;
    vid.style.display = 'block';
    document.getElementById('resultImg').style.display = 'none';
  } else {
    const img = document.getElementById('resultImg');
    img.src = url;
    img.style.display = 'block';
    document.getElementById('resultVideo').style.display = 'none';
  }
}

function downloadResult() {
  if (!state.resultFilename) return;
  const a = document.createElement('a');
  a.href = `/download/${state.resultFilename}`;
  a.download = state.resultFilename;
  a.click();
}

// ---- Error ----
function showError(msg) {
  document.getElementById('errorMsg').textContent = msg;
  showSection('error');
}

// ---- Section visibility ----
function showSection(name) {
  document.getElementById('progressSection').style.display = name === 'progress' ? 'block' : 'none';
  document.getElementById('resultSection').style.display = name === 'result' ? 'block' : 'none';
  document.getElementById('errorSection').style.display = name === 'error' ? 'block' : 'none';
}

function resetProgress() {
  showSection('none');
  document.getElementById('progressFill').style.width = '0%';
  document.getElementById('progressPct').textContent = '0%';
  document.getElementById('progressSub').textContent = 'Inizializzazione modelli…';
}

function resetAll() {
  if (state.pollInterval) clearInterval(state.pollInterval);
  resetProgress();
  clearSource({ stopPropagation: () => {} });
  clearTarget({ stopPropagation: () => {} });
  state.jobId = null;
  state.resultFilename = null;
}

// ---- Utilities ----
function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDuration(s) {
  if (!s || isNaN(s)) return '';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

let _toastTimer = null;
function showToast(msg, type = 'info') {
  let toast = document.getElementById('_toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = '_toast';
    toast.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999;
      padding:12px 18px; border-radius:10px; font-size:0.82rem; font-weight:500;
      backdrop-filter:blur(12px); max-width:340px;
      border:1px solid; transition:opacity 0.3s;
    `;
    document.body.appendChild(toast);
  }
  const colors = {
    error: 'background:rgba(239,68,68,0.15); border-color:rgba(239,68,68,0.35); color:#fca5a5;',
    success: 'background:rgba(16,185,129,0.15); border-color:rgba(16,185,129,0.35); color:#6ee7b7;',
    info: 'background:rgba(124,58,237,0.15); border-color:rgba(124,58,237,0.35); color:#c4b5fd;',
  };
  toast.style.cssText += colors[type] || colors.info;
  toast.textContent = msg;
  toast.style.opacity = '1';
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 4000);
}
