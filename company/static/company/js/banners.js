// import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
// import { ConfirmModalService } from './services/confirmModalService.js';
// import { API_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';
// import { ModalService } from '/food_flash/static/utils/js/services/modalService.js';

// document.addEventListener('DOMContentLoaded', async () => {

//   const uploadForm = document.getElementById('banner-upload-form');
//   const bannerContainer = document.getElementById('banner-tiles-container');
//   const modalImage = document.getElementById('bannerModalImage');
//   const selectAllCheckbox = document.getElementById('selectAllBanners');
//   const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
//   const selectedBannerIds = new Set();

//   const progressContainer = document.getElementById('uploadProgressContainer');
//   const progressBar = document.getElementById('uploadProgressBar');

//   let cachedBannerList = [];

//   fetchBanners();

//   uploadForm.addEventListener('submit', async (e) => {
//     e.preventDefault();

//     const allowedTypes = ['image/png', 'image/jpeg', 'image/webp'];
//     const files = Array.from(uploadForm.querySelector('#banner_images').files);

//     if (!files.length) return;

//     for (const file of files) {
//       if (!allowedTypes.includes(file.type)) {
//         ModalService.showError(`Invalid file type: ${file.name}. Only PNG, JPG, and WEBP are allowed.`);
//         return;
//       }
//     }

//     const formData = new FormData(uploadForm);

//     // --- Show progress bar ---
//     progressContainer.classList.remove('d-none');
//     progressBar.style.width = '0%';
//     progressBar.textContent = 'Uploading...';

//     // --- Simulate progress ---
//     let fakePercent = 0;
//     const interval = setInterval(() => {
//       fakePercent += Math.floor(Math.random() * 3) + 1; // increase 1-3%
//       if (fakePercent > 90) fakePercent = 90; // cap at 90% until backend responds
//       progressBar.style.width = `${fakePercent}%`;
//       progressBar.textContent = `Uploading... ${fakePercent}%`;
//     }, 200);

//     try {
//       // --- Send request ---
//       const response = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_UPLOAD, {
//         method: 'POST',
//         body: formData
//       });

//       clearInterval(interval); // stop simulated progress

//       if (response.ok) {
//         // Complete the progress bar
//         progressBar.style.width = '100%';
//         progressBar.textContent = 'Completed!';

//         setTimeout(() => {
//           progressContainer.classList.add('d-none');
//           uploadForm.reset();
//           fetchBanners();
//           ModalService.showSuccess('Banners uploaded and converted successfully!');
//         }, 500);
//       } else {
//         progressContainer.classList.add('d-none');
//         ModalService.showError('Banner upload failed.');
//       }
//     } catch (err) {
//       clearInterval(interval);
//       progressContainer.classList.add('d-none');
//       ModalService.showError('Banner upload failed due to network error.');
//       console.error(err);
//     }
//   });

//   async function fetchBanners() {
//     try {
//       const response = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_LIST, { method: 'GET' });
//       const banners = await response.json();
//       cachedBannerList = banners.banners || [];

//       bannerContainer.innerHTML = '';
//       selectedBannerIds.clear();
//       selectAllCheckbox.checked = false;
//       toggleDeleteSelectedBtn();

//       cachedBannerList.forEach(banner => {
//         const tile = document.createElement('div');
//         tile.className = 'banner-tile position-relative';
//         tile.setAttribute('data-id', banner.id);

//         const image = document.createElement('img');
//         image.src = banner.image_url;
//         image.alt = "Banner";
//         image.className = 'selectable-banner';
//         image.addEventListener('click', () => toggleSelection(tile, banner.id));

//         const actions = document.createElement('div');
//         actions.className = 'banner-actions';
//         actions.innerHTML = `
//           <button onclick="viewBanner('${banner.image_url}')" title="View">
//             <i class="fas fa-eye"></i>
//           </button>
//         `;

//         tile.appendChild(image);
//         tile.appendChild(actions);
//         bannerContainer.appendChild(tile);
//       });
//     } catch (err) {
//       console.error('Error fetching banners:', err);
//     }
//   }

//   function toggleSelection(tile, id) {
//     const selected = tile.classList.toggle('selected');
//     if (selected) selectedBannerIds.add(id);
//     else {
//       selectedBannerIds.delete(id);
//       selectAllCheckbox.checked = false;
//     }
//     toggleDeleteSelectedBtn();
//   }

//   selectAllCheckbox.addEventListener('change', () => {
//     const tiles = document.querySelectorAll('.banner-tile');
//     selectedBannerIds.clear();

//     tiles.forEach(tile => {
//       const id = parseInt(tile.getAttribute('data-id'));
//       if (selectAllCheckbox.checked) {
//         tile.classList.add('selected');
//         selectedBannerIds.add(id);
//       } else {
//         tile.classList.remove('selected');
//       }
//     });

//     toggleDeleteSelectedBtn();
//   });

//   const selectionCount = document.getElementById('selectionCount');
//   const toggleDeleteSelectedBtn = () => {
//     if (selectedBannerIds.size > 0) {
//       deleteSelectedBtn.classList.remove('hidden');
//       selectionCount.textContent = `${selectedBannerIds.size}`;
//     } else {
//       deleteSelectedBtn.classList.add('hidden');
//       selectionCount.textContent = '';
//     }
//   };

//   deleteSelectedBtn.addEventListener('click', async () => {
//     const confirmed = await ConfirmModalService.show(`Delete ${selectedBannerIds.size} selected banner(s)?`);
//     if (!confirmed) return;

//     try {
//       await Promise.all(
//         Array.from(selectedBannerIds).map(id =>
//           fetchWithAutoRefresh(`/food_flash/company/api/banner_delete/?banner_id=${id}`, { method: 'DELETE' })
//         )
//       );
//       selectedBannerIds.clear();
//       fetchBanners();
//     } catch (err) {
//       console.error("Bulk delete error:", err);
//     }
//   });

//   window.viewBanner = (url) => {
//     modalImage.src = url;
//     $('#bannerModal').modal('show');
//   };

//   window.deleteBanner = async (id) => {
//     const confirmed = await ConfirmModalService.show("Do you want to discard this banner?");
//     if (!confirmed) return;

//     try {
//       const response = await fetchWithAutoRefresh(`/food_flash/company/api/banner_delete/?banner_id=${id}`, { method: 'DELETE' });
//       if (response.ok) fetchBanners();
//     } catch (err) {
//       console.error("Banner delete error:", err);
//     }
//   };
// });




import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { ConfirmModalService } from './services/confirmModalService.js';
import { API_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';
import { ModalService } from '/food_flash/static/utils/js/services/modalService.js';

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



  // uploadForm.addEventListener('submit', async (e) => {
  //   e.preventDefault();

  //   const allowedTypes = ['image/png', 'image/jpeg', 'image/webp'];
  //   const files = Array.from(uploadForm.querySelector('#banner_images').files);

  //   // Validate each selected file
  //   for (const file of files) {
  //     if (!allowedTypes.includes(file.type)) {
  //       ModalService.showError(`Invalid file type: ${file.name}. Only PNG, JPG, and WEBP are allowed.`);
  //       return;
  //     }
  //   }

  //   const formData = new FormData(uploadForm);
  //   const response = await fetchWithAutoRefresh(API_ENDPOINTS.BANNER_UPLOAD, {
  //     method: 'POST',
  //     body: formData
  //   });

  //   if (response.ok) {
  //     uploadForm.reset();
  //     fetchBanners();
  //   } else {
  //     alert("Banner upload failed.");
  //   }
  // });


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
          fetchWithAutoRefresh(`/food_flash/company/api/banner_delete/?banner_id=${id}`, {
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
      const response = await fetchWithAutoRefresh(`/food_flash/company/api/banner_delete/?banner_id=${id}`, {
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
