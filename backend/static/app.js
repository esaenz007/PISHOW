const mediaList = document.querySelector('#media-list');
const uploadInput = document.querySelector('#upload-input');
const uploadButton = document.querySelector('#upload-button');
const statusText = document.querySelector('#status-text');
const statusChip = document.querySelector('#status-chip');
const statusDetails = document.querySelector('#status-details');
const stopButton = document.querySelector('#stop-button');
const refreshButton = document.querySelector('#refresh-button');

const API = {
  media: '/api/media',
  status: '/api/status',
  stop: '/api/stop',
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function refreshMedia() {
  try {
    const data = await fetchJson(API.media);
    renderMedia(data.items || []);
  } catch (error) {
    console.error('Failed to load media list', error);
  }
}

async function refreshStatus() {
  try {
    const data = await fetchJson(API.status);
    renderStatus(data);
  } catch (error) {
    console.error('Failed to load status', error);
  }
}

function renderMedia(items) {
  mediaList.innerHTML = '';
  if (!items.length) {
    mediaList.innerHTML = '<p>No media uploaded yet.</p>';
    return;
  }

  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'media-card';

    const previewWrapper = document.createElement('div');
    if (item.media_type === 'image') {
      const img = document.createElement('img');
      img.src = `/media/${item.filename}`;
      img.alt = item.original_name;
      previewWrapper.appendChild(img);
    } else {
      const video = document.createElement('video');
      video.src = `/media/${item.filename}`;
      video.muted = true;
      video.loop = true;
      video.autoplay = true;
      previewWrapper.appendChild(video);
    }

    const meta = document.createElement('div');
    meta.className = 'media-meta';
    const title = document.createElement('strong');
    title.textContent = item.original_name;
    meta.appendChild(title);

    const details = document.createElement('small');
    const created = new Date(item.created_at);
    details.textContent = `${item.media_type.toUpperCase()} • ${created.toLocaleString()}`;
    meta.appendChild(details);

    const actions = document.createElement('div');
    actions.className = 'media-actions';

    const playButton = document.createElement('button');
    playButton.textContent = 'Send to projector';
    playButton.addEventListener('click', () => playMedia(item.id));
    actions.appendChild(playButton);

    const deleteButton = document.createElement('button');
    deleteButton.textContent = 'Delete';
    deleteButton.className = 'secondary';
    deleteButton.addEventListener('click', () => deleteMedia(item.id, item.original_name));
    actions.appendChild(deleteButton);

    meta.appendChild(actions);

    card.appendChild(previewWrapper);
    card.appendChild(meta);
    mediaList.appendChild(card);
  }
}

function renderStatus(status) {
  if (!status || status.status !== 'playing') {
    statusChip.textContent = 'Idle';
    statusChip.classList.add('idle');
    statusText.textContent = 'Nothing is currently on the projector.';
    statusDetails.textContent = '';
    return;
  }

  statusChip.textContent = 'Playing';
  statusChip.classList.remove('idle');
  const media = status.media;
  const timestamp = media?.created_at ? new Date(media.created_at).toLocaleString() : '';
  statusText.textContent = media ? `${media.original_name}` : 'Unknown media';
  statusDetails.textContent = `${media?.media_type?.toUpperCase() || ''} • Added ${timestamp}`;
}

async function uploadMedia(file) {
  const formData = new FormData();
  formData.append('file', file);
  await fetchJson(API.media, {
    method: 'POST',
    body: formData,
  });
}

async function playMedia(mediaId) {
  try {
    await fetchJson(`${API.media}/${mediaId}/play`, { method: 'POST' });
    await refreshStatus();
  } catch (error) {
    alert(`Failed to start playback: ${error.message}`);
  }
}

async function deleteMedia(mediaId, name) {
  const ok = confirm(`Delete "${name}"?`);
  if (!ok) {
    return;
  }
  try {
    await fetchJson(`${API.media}/${mediaId}`, { method: 'DELETE' });
    await refreshMedia();
    await refreshStatus();
  } catch (error) {
    alert(`Failed to delete media: ${error.message}`);
  }
}

async function stopPlayback() {
  try {
    await fetchJson(API.stop, { method: 'POST' });
    await refreshStatus();
  } catch (error) {
    alert(`Failed to stop playback: ${error.message}`);
  }
}

function setupUpload() {
  uploadButton.addEventListener('click', (event) => {
    event.preventDefault();
    if (uploadButton.disabled) {
      return;
    }
    uploadInput.click();
  });

  uploadInput.addEventListener('change', async () => {
    if (!uploadInput.files?.length) {
      return;
    }
    const [file] = uploadInput.files;
    uploadButton.disabled = true;
    uploadButton.textContent = 'Uploading…';
    try {
      await uploadMedia(file);
      await refreshMedia();
    } catch (error) {
      alert(`Upload failed: ${error.message}`);
    } finally {
      uploadButton.disabled = false;
      uploadButton.textContent = 'Upload';
      uploadInput.value = '';
    }
  });
}

function setupControls() {
  stopButton.addEventListener('click', stopPlayback);
  refreshButton.addEventListener('click', () => {
    refreshMedia();
    refreshStatus();
  });
}

setupUpload();
setupControls();
refreshMedia();
refreshStatus();
setInterval(() => {
  refreshStatus();
}, 5000);
