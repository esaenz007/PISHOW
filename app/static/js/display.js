(function () {
  const displayContainer = document.getElementById('display-container');
  const noContentEl = document.getElementById('no-content');

  let playlist = (window.initialPlaylist && window.initialPlaylist.items) || [];
  let playlistVersion = (window.initialPlaylist && window.initialPlaylist.version) || null;
  let currentIndex = 0;
  let currentTimer = null;
  let pollTimer = null;

  function clearCurrentTimer() {
    if (currentTimer) {
      clearTimeout(currentTimer);
      currentTimer = null;
    }
  }

  function showNoContent() {
    clearCurrentTimer();
    displayContainer.innerHTML = '';
    if (noContentEl) {
      displayContainer.appendChild(noContentEl);
      noContentEl.style.display = 'block';
    }
  }

  function computeDuration(item) {
    if (item.media_type !== 'image') {
      return null; // videos handle duration via ended event
    }
    if (item.duration != null) {
      return item.duration;
    }
    if (item.default_duration != null) {
      return item.default_duration;
    }
    return 8;
  }

  function buildMediaElement(item) {
    if (item.media_type === 'image') {
      const img = document.createElement('img');
      img.src = `/media/${item.filename}`;
      img.alt = item.original_name || 'image';
      return img;
    }

    const video = document.createElement('video');
    video.src = `/media/${item.filename}`;
    video.autoplay = true;
    video.controls = false;
    video.loop = false;
    video.playsInline = true;
    video.style.maxHeight = '100%';
    video.style.maxWidth = '100%';
    return video;
  }

  function playItem(index) {
    if (!playlist.length) {
      showNoContent();
      return;
    }

    if (index >= playlist.length) {
      index = 0;
    }

    currentIndex = index;
    const item = playlist[index];
    clearCurrentTimer();

    if (noContentEl && noContentEl.parentElement === displayContainer) {
      displayContainer.removeChild(noContentEl);
    }

    displayContainer.innerHTML = '';
    const mediaEl = buildMediaElement(item);
    displayContainer.appendChild(mediaEl);

    if (item.media_type === 'image') {
      const duration = computeDuration(item);
      if (duration != null) {
        currentTimer = setTimeout(() => playItem(index + 1), duration * 1000);
      }
    } else {
      mediaEl.addEventListener('ended', () => {
        playItem(index + 1);
      });
      mediaEl.addEventListener('error', () => {
        playItem(index + 1);
      });
      mediaEl.play().catch(() => {
        // Autoplay might be blocked; retry on user interaction.
      });
    }
  }

  async function pollPlaylist() {
    try {
      const response = await fetch('/api/playlist');
      if (!response.ok) {
        throw new Error('Failed to fetch playlist');
      }
      const data = await response.json();
      if (!data || !data.items) {
        throw new Error('Invalid playlist data');
      }
      if (data.version !== playlistVersion) {
        playlistVersion = data.version;
        playlist = data.items;
        currentIndex = 0;
        if (playlist.length) {
          playItem(0);
        } else {
          showNoContent();
        }
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error(error);
    } finally {
      pollTimer = setTimeout(pollPlaylist, 5000);
    }
  }

  function init() {
    if (playlist.length) {
      playItem(0);
    } else {
      showNoContent();
    }
    pollPlaylist();
  }

  window.addEventListener('beforeunload', () => {
    clearCurrentTimer();
    if (pollTimer) {
      clearTimeout(pollTimer);
    }
  });

  init();
})();
