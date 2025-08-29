import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {

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
    const formData = new FormData(uploadForm);
    const response = await fetchWithAutoRefresh('/company/api/banner_upload/', {
      method: 'POST',
      body: formData
    });
    if (response.ok) {
      uploadForm.reset();
      fetchBanners();
    } else {
      alert("Banner upload failed.");
    }
  });

  async function fetchBanners() {
    const response = await fetchWithAutoRefresh('/company/api/banner_list/', {
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
      actions.innerHTML = `
        <button onclick="viewBanner('${banner.image_url}')" title="View">
          <i class="fas fa-eye"></i>
        </button>
      `;

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
          fetchWithAutoRefresh(`/company/api/banner_delete/?banner_id=${id}`, {
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

  window.viewBanner = (url) => {
    modalImage.src = url;
    $('#bannerModal').modal('show');
  };

  window.deleteBanner = async (id) => {
    const confirmed = await ConfirmModalService.show("Do you want to discard this banner?");
    if (!confirmed) return;

    try {
      const response = await fetchWithAutoRefresh(`/company/api/banner_delete/?banner_id=${id}`, {
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
