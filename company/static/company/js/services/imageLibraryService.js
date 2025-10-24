export const ImageLibraryService = (() => {
  let selectedImageIds = new Set();
  let imageList = [];
  let fetchWithAutoRefresh = null;
  let API_ENDPOINTS = null;

  // Initialize dependencies
  const init = (fetchFn, endpoints) => {
    fetchWithAutoRefresh = fetchFn;
    API_ENDPOINTS = endpoints;
    bindModalEvents();
  };

  // Fetch images from server
  const fetchImages = async () => {
    try {
      const res = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_LIST);
      const data = await res.json();
      imageList = data.banners || [];
    } catch (err) {
      console.error('Error fetching images:', err);
      imageList = [];
    }
  };

  const renderLibrary = () => {
    const grid = document.getElementById('image-library-grid');
    grid.innerHTML = '';

    if (!imageList || imageList.length === 0) {
      const emptyState = document.createElement('div');
      emptyState.className = 'empty-state text-center p-4';
      emptyState.innerHTML = `
        <div class="placeholder-mask mb-3">
          <i class="bi bi-image text-muted" style="font-size: 3rem;"></i>
        </div>
        <p class="text-muted mb-1">No images available</p>
        <small class="text-secondary">Upload new banners to see them here.</small>
      `;
      grid.appendChild(emptyState);
      return;
    }

    imageList.forEach(img => {
      const box = document.createElement('div');
      box.className = 'image-box thumb-container';
      box.dataset.id = img.id;

      const imgUrl = img.image_url;
      loadImageWithRetry(imgUrl, box);

      if (selectedImageIds.has(img.id)) {
        box.classList.add('selected');
        box.style.borderColor = '#f0a934';
      }

      box.addEventListener('click', () => {
        toggleImageSelection(img.id, box);
        updateSelectAllCheckbox();
        updateConfirmButton();
      });

      grid.appendChild(box);
    });

    updateSelectAllCheckbox();
    updateConfirmButton();
  };

  const loadImageWithRetry = (imgUrl, box, maxRetries = 10, interval = 3000) => {
    let attempt = 0;

    const getAlternateUrl = (url) => url.replace(/\.[^/.]+$/, "") + ".webp";

    const tryLoad = () => {
      const testImg = new Image();

      testImg.onload = () => {
        box.innerHTML = `<img src="${testImg.src}" class="thumb-image rounded fade-in">`;
      };

      testImg.onerror = () => {
        attempt++;

        if (attempt < maxRetries) {
          box.innerHTML = `
            <div class="thumb-placeholder d-flex flex-column align-items-center justify-content-center">
              <div class="spinner-border text-warning mb-2" role="status" style="width: 1.5rem; height: 1.5rem;"></div>
              <small class="text-muted">Processing...</small>
            </div>
          `;
          const altUrl = getAlternateUrl(imgUrl);
          const candidateUrl = attempt % 2 === 0 ? imgUrl : altUrl;
          setTimeout(() => {
            testImg.src = `${candidateUrl}?t=${Date.now()}`;
          }, interval);
        } else {
          box.innerHTML = `
            <div class="thumb-placeholder d-flex flex-column align-items-center justify-content-center">
              <i class="bi bi-exclamation-triangle text-warning mb-2" style="font-size: 1.2rem;"></i>
              <small class="text-muted">Image unavailable</small>
            </div>
          `;
        }
      };

      testImg.src = `${imgUrl}?t=${Date.now()}`;
    };

    tryLoad();
  };

  const toggleImageSelection = (id, box) => {
    if (selectedImageIds.has(id)) {
      selectedImageIds.delete(id);
      box.classList.remove('selected');
      box.style.borderColor = 'transparent';
    } else {
      selectedImageIds.add(id);
      box.classList.add('selected');
      box.style.borderColor = '#f0a934';
    }
  };

  const updateSelectAllCheckbox = () => {
    const selectAllCheckbox = document.getElementById('select-all-images');
    const allSelected = imageList.length > 0 && imageList.every(img => selectedImageIds.has(img.id));
    selectAllCheckbox.checked = allSelected;
  };

  const updateConfirmButton = () => {
    const confirmBtn = document.getElementById('confirm-image-selection');
    confirmBtn.disabled = selectedImageIds.size === 0;
  };

  const bindModalEvents = () => {
    const selectAll = document.getElementById('select-all-images');
    const confirmBtn = document.getElementById('confirm-image-selection');

    selectAll.addEventListener('change', () => {
      if (selectAll.checked) {
        imageList.forEach(img => selectedImageIds.add(img.id));
      } else {
        selectedImageIds.clear();
      }
      renderLibrary();
    });

    confirmBtn.addEventListener('click', () => {
      const selected = Array.from(selectedImageIds);
      const preview = document.getElementById('selected-images-preview');
      preview.innerHTML = '';

      imageList
        .filter(img => selected.includes(img.id))
        .forEach(img => {
          const thumb = document.createElement('img');
          thumb.src = img.image_url;
          thumb.className = 'preview-thumb';
          preview.appendChild(thumb);
        });

      $('#imageLibraryModal').modal('hide');
    });
  };

  const open = async (reset = false) => {
    if (reset) selectedImageIds.clear();
    await fetchImages();
    renderLibrary();
    $('#imageLibraryModal').modal('show');
  };

  return {
    init,
    open,
    getSelectedImageIds: () => Array.from(selectedImageIds),
    getSelectedImages: () => imageList.filter(img => selectedImageIds.has(img.id))
  };
})();
