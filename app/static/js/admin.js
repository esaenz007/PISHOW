(function () {
  const mediaGrid = document.getElementById('media-grid');
  const playlistList = document.getElementById('playlist-items');
  const uploadForm = document.getElementById('upload-form');
  const uploadStatus = document.getElementById('upload-status');
  const savePlaylistBtn = document.getElementById('save-playlist');
  const clearPlaylistBtn = document.getElementById('clear-playlist');

  const mediaMap = new Map();
  (window.initialMedia || []).forEach((item) => {
    mediaMap.set(item.id, item);
  });

  let playlistState = [];

  function hydrateInitialPlaylist() {
    const initial = (window.initialPlaylist && window.initialPlaylist.items) || [];
    playlistState = initial.map((item) => {
      const libraryItem = mediaMap.get(item.media_id) || item;
      const duration = item.duration ?? libraryItem.duration_default ?? (libraryItem.media_type === 'image' ? 8 : null);
      return {
        mediaId: item.media_id,
        name: libraryItem.original_name,
        mediaType: libraryItem.media_type,
        duration: duration,
        defaultDuration: libraryItem.duration_default ?? (libraryItem.media_type === 'image' ? 8 : null),
      };
    });
    renderPlaylist();
  }

  function renderPlaylist() {
    playlistList.innerHTML = '';
    if (!playlistState.length) {
      const empty = document.createElement('li');
      empty.textContent = 'Playlist is empty.';
      empty.style.listStyle = 'none';
      playlistList.appendChild(empty);
      return;
    }

    playlistState.forEach((item, index) => {
      const li = document.createElement('li');
      li.dataset.index = String(index);
      const label = document.createElement('span');
      label.textContent = `${index + 1}. ${item.name} (${item.mediaType})`;
      li.appendChild(label);

      if (item.mediaType === 'image' && playlistState.length > 1) {
        const durationInput = document.createElement('input');
        durationInput.type = 'number';
        durationInput.min = '1';
        durationInput.value = item.duration ?? item.defaultDuration ?? 8;
        durationInput.className = 'small';
        durationInput.style.width = '5rem';
        durationInput.addEventListener('change', () => {
          const value = parseInt(durationInput.value, 10);
          if (Number.isFinite(value) && value > 0) {
            item.duration = value;
          }
        });
        li.appendChild(durationInput);
        const labelSpan = document.createElement('span');
        labelSpan.textContent = 's';
        labelSpan.style.width = '1.5rem';
        li.appendChild(labelSpan);
      }

      const controls = document.createElement('div');
      controls.style.display = 'flex';
      controls.style.gap = '0.25rem';

      const upBtn = document.createElement('button');
      upBtn.textContent = '↑';
      upBtn.className = 'small secondary';
      upBtn.disabled = index === 0;
      upBtn.addEventListener('click', () => moveItem(index, index - 1));
      controls.appendChild(upBtn);

      const downBtn = document.createElement('button');
      downBtn.textContent = '↓';
      downBtn.className = 'small secondary';
      downBtn.disabled = index === playlistState.length - 1;
      downBtn.addEventListener('click', () => moveItem(index, index + 1));
      controls.appendChild(downBtn);

      const removeBtn = document.createElement('button');
      removeBtn.textContent = 'Remove';
      removeBtn.className = 'small contrast';
      removeBtn.addEventListener('click', () => {
        playlistState.splice(index, 1);
        renderPlaylist();
      });
      controls.appendChild(removeBtn);

      li.appendChild(controls);
      playlistList.appendChild(li);
    });
  }

  function moveItem(from, to) {
    if (to < 0 || to >= playlistState.length) {
      return;
    }
    const [item] = playlistState.splice(from, 1);
    playlistState.splice(to, 0, item);
    renderPlaylist();
  }

  async function handleUpload(event) {
    event.preventDefault();
    const file = uploadForm.querySelector('input[type="file"]').files[0];
    if (!file) {
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    uploadStatus.textContent = 'Uploading...';
    try {
      const response = await fetch('/api/media', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Upload failed');
      }
      uploadStatus.textContent = 'Upload complete';
      uploadForm.reset();
      addMediaCard(data.media);
    } catch (error) {
      uploadStatus.textContent = error.message;
    }
  }

  function addMediaCard(media) {
    mediaMap.set(media.id, media);
    const card = document.createElement('article');
    card.className = 'media-card';
    card.dataset.mediaId = String(media.id);
    card.innerHTML = `
      <header>${media.original_name} (${media.media_type})</header>
      ${media.media_type === 'image'
        ? `<img src="/media/${media.filename}" alt="${media.original_name}" />`
        : `<video src="/media/${media.filename}" muted loop></video>`
      }
      <footer>
        ${media.media_type === 'image'
          ? `<label>Default duration (seconds)
              <input type="number" min="1" name="duration" value="${media.duration_default || 8}" />
            </label>`
          : ''
        }
        <div style="display:flex; gap:0.5rem; margin-top:0.5rem;">
          ${media.media_type === 'image'
            ? `<button class="small secondary" data-action="set-duration" data-id="${media.id}">Save Duration</button>`
            : ''
          }
          <button class="small" data-action="add-to-playlist" data-id="${media.id}">Add to Playlist</button>
          <button class="small contrast" data-action="delete-media" data-id="${media.id}">Delete</button>
        </div>
      </footer>
    `;
    mediaGrid.prepend(card);
  }

  function handleMediaGridClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) {
      return;
    }
    const mediaId = parseInt(button.dataset.id, 10);
    const action = button.dataset.action;
    const card = button.closest('[data-media-id]');

    if (action === 'add-to-playlist') {
      const media = mediaMap.get(mediaId);
      if (!media) {
        return;
      }
      playlistState.push({
        mediaId: media.id,
        name: media.original_name,
        mediaType: media.media_type,
        duration: media.media_type === 'image' ? (media.duration_default || 8) : null,
        defaultDuration: media.media_type === 'image' ? (media.duration_default || 8) : null,
      });
      renderPlaylist();
    }

    if (action === 'delete-media') {
      if (!confirm('Delete this media item?')) {
        return;
      }
      fetch(`/api/media/${mediaId}`, { method: 'DELETE' })
        .then((response) => {
          if (!response.ok) {
            throw new Error('Delete failed');
          }
          mediaMap.delete(mediaId);
          card.remove();
          playlistState = playlistState.filter((item) => item.mediaId !== mediaId);
          renderPlaylist();
        })
        .catch((error) => {
          alert(error.message);
        });
    }

    if (action === 'set-duration') {
      const input = card.querySelector('input[name="duration"]');
      const value = parseInt(input.value, 10);
      if (!Number.isFinite(value) || value <= 0) {
        alert('Duration must be a positive number');
        return;
      }
      fetch(`/api/media/${mediaId}/duration`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: value }),
      })
        .then((response) => {
          if (!response.ok) {
            return response.json().then((data) => {
              throw new Error(data.error || 'Failed to save duration');
            });
          }
          const media = mediaMap.get(mediaId);
          if (media) {
            media.duration_default = value;
          }
          playlistState = playlistState.map((item) =>
            item.mediaId === mediaId ? { ...item, duration: value, defaultDuration: value } : item,
          );
          renderPlaylist();
        })
        .catch((error) => alert(error.message));
    }
  }

  async function savePlaylist() {
    if (!playlistState.length) {
      alert('Playlist is empty.');
      return;
    }
    const payloadItems = playlistState.map((item) => {
      let duration = item.duration;
      if (item.mediaType !== 'image') {
        duration = null;
      }
      return { media_id: item.mediaId, duration };
    });
    if (payloadItems.length === 1) {
      const [onlyItem] = payloadItems;
      if (mediaMap.get(onlyItem.media_id)?.media_type === 'image') {
        onlyItem.duration = null; // infinite display for single image
      }
    }
    try {
      const response = await fetch('/api/playlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: payloadItems }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to save playlist');
      }
      alert('Playlist sent to projector.');
    } catch (error) {
      alert(error.message);
    }
  }

  async function clearPlaylist() {
    try {
      const response = await fetch('/api/playlist', { method: 'DELETE' });
      if (!response.ok) {
        throw new Error('Failed to clear playlist');
      }
      playlistState = [];
      renderPlaylist();
    } catch (error) {
      alert(error.message);
    }
  }

  uploadForm.addEventListener('submit', handleUpload);
  mediaGrid.addEventListener('click', handleMediaGridClick);
  savePlaylistBtn.addEventListener('click', savePlaylist);
  clearPlaylistBtn.addEventListener('click', clearPlaylist);

  hydrateInitialPlaylist();
})();
