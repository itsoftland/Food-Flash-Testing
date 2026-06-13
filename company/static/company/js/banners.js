import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
 
  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;
  
  const uploadForm = document.getElementById('banner-upload-form');
  const bannerContainer = document.getElementById('banner-tiles-container');
  const modalImage = document.getElementById('bannerModalImage');
  const selectAllCheckbox = document.getElementById('selectAllBanners');
  const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
  const selectedBannerIds = new Set();

  let cachedBannerList = [];

  fetchBanners();
  uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const allowedTypes = ['image/png', 'image/jpeg', 'image/webp'];
    const files = Array.from(uploadForm.querySelector('#banner_images').files);

    for (const file of files) {
      if (!allowedTypes.includes(file.type)) {
        ModalService.showError(`Invalid file type: ${file.name}. Only PNG, JPG, and WEBP are allowed.`);
        return;
      }
    }

    const formData = new FormData(uploadForm);
    const progressContainer = document.getElementById('uploadProgressContainer');
    const progressBar = document.getElementById('uploadProgressBar');

    progressContainer.classList.remove('d-none');
    progressBar.style.width = '0%';
    progressBar.textContent = 'Uploading...';

    // --- Simulate progress while fetchWithAutoRefresh runs ---
    let simulatedPercent = 0;
    const interval = setInterval(() => {
      simulatedPercent += Math.floor(Math.random() * 3) + 1; // increase 1-3% randomly
      if (simulatedPercent > 70) simulatedPercent = 70;       // 70% max for "uploading"
      progressBar.style.width = `${simulatedPercent}%`;
      progressBar.textContent = `Uploading ${simulatedPercent}%`;
    }, 200);

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_UPLOAD, {
        method: 'POST',
        body: formData
      });

      clearInterval(interval); // stop simulated upload

      if (response.ok) {
        // --- Stage 2: Conversion Animation ---
        fetchBanners();
        progressBar.textContent = 'Converting images...';
        let convertPercent = 70;
        const convertInterval = setInterval(() => {
          convertPercent += 1;
          progressBar.style.width = `${convertPercent}%`;
          if (convertPercent >= 100) {
            clearInterval(convertInterval);
            progressBar.textContent = 'Completed!';
            setTimeout(() => {
              progressContainer.classList.add('d-none');
              uploadForm.reset();
              ModalService.showSuccess('Banners uploaded and converted successfully!');
            }, 500);
          }
        }, 30); // adjust speed for smooth effect
      } else {
        progressContainer.classList.add('d-none');
        ModalService.showError('Banner upload failed.');
      }
    } catch (err) {
      clearInterval(interval);
      progressContainer.classList.add('d-none');
      ModalService.showError('Banner upload failed due to network error.');
      console.error(err);
    }
  });

  async function fetchBanners() {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_LIST, {
      method: 'GET'
    });
    const banners = await response.json();
    cachedBannerList = banners.banners;

    bannerContainer.innerHTML = '';
    selectedBannerIds.clear();
    selectAllCheckbox.checked = false;
    toggleDeleteSelectedBtn();

    cachedBannerList.forEach((banner) => {
      const tile = document.createElement('div');
      tile.className = 'banner-tile position-relative';
      tile.setAttribute('data-id', banner.id);

      // Image (clickable for selection)
      const image = document.createElement('img');
      image.src = banner.image_url;
      image.alt = "Banner";
      image.className = 'selectable-banner';
      image.addEventListener('click', () => toggleSelection(tile, banner.id));

      // Actions
      const actions = document.createElement('div');
      actions.className = 'banner-actions';
      const viewBtn = document.createElement('button');
      viewBtn.type = 'button';
      viewBtn.title = 'View';
      viewBtn.innerHTML = '<i class="fas fa-eye"></i>';
      viewBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        viewBanner(banner.image_url);
      });
      actions.appendChild(viewBtn);

      tile.appendChild(image);
      tile.appendChild(actions);

      bannerContainer.appendChild(tile);
    });
  }

  function toggleSelection(tile, id) {
    const selected = tile.classList.toggle('selected');
    if (selected) {
      selectedBannerIds.add(id);
    } else {
      selectedBannerIds.delete(id);
      selectAllCheckbox.checked = false;
    }
    toggleDeleteSelectedBtn();
  }

  selectAllCheckbox.addEventListener('change', () => {
    const tiles = document.querySelectorAll('.banner-tile');
    selectedBannerIds.clear();

    tiles.forEach(tile => {
      const id = parseInt(tile.getAttribute('data-id'));
      const image = tile.querySelector('img');

      if (selectAllCheckbox.checked) {
        tile.classList.add('selected');
        selectedBannerIds.add(id);
      } else {
        tile.classList.remove('selected');
        selectedBannerIds.delete(id);
      }
    });

    toggleDeleteSelectedBtn();
  });

  const selectionCount = document.getElementById('selectionCount');

  const toggleDeleteSelectedBtn = () => {
    if (selectedBannerIds.size > 0) {
      deleteSelectedBtn.classList.remove('hidden');
      selectionCount.textContent = `${selectedBannerIds.size}`;
    } else {
      deleteSelectedBtn.classList.add('hidden');
      selectionCount.textContent = '';
    }
  };


  deleteSelectedBtn.addEventListener('click', async () => {
    const confirmed = await ConfirmModalService.show(`Delete ${selectedBannerIds.size} selected banner(s)?`);
    if (!confirmed) return;

    try {
      await Promise.all(
        Array.from(selectedBannerIds).map(id =>
          fetchWithAutoRefresh(`${API_ENDPOINTS.BANNER_DELETE}?banner_id=${id}`, {
            method: 'DELETE'
          })
        )
      );
      selectedBannerIds.clear();
      fetchBanners();
    } catch (err) {
      console.error("Bulk delete error:", err);
    }
  });

  const isDineFlashBannerPreview =
    window.PROJECT_NAME === 'dine_flash' || window.PROJECT_NAME === 'dine_flash_buffet';

  const viewBanner = (url) => {
    modalImage.src = url;
    const bannerModalEl = document.getElementById('bannerModal');
    if (!bannerModalEl) return;

    if (isDineFlashBannerPreview) {
      bootstrap.Modal.getOrCreateInstance(bannerModalEl).show();
    } else {
      $('#bannerModal').modal('show');
    }
  };

  window.deleteBanner = async (id) => {
    const confirmed = await ConfirmModalService.show("Do you want to discard this banner?");
    if (!confirmed) return;

    try {
      const response = await fetchWithAutoRefresh(`${API_ENDPOINTS.BANNER_DELETE}?banner_id=${id}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        fetchBanners();
      }
    } catch (err) {
      console.error("Banner delete error:", err);
    }
  };
});
