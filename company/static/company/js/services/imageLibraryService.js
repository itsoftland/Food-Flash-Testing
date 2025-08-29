import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
export const ImageLibraryService = (() => {
  let selectedImageIds = new Set();
  let imageList = [];

  // Fetch images from server
  const fetchImages = async () => {
    try {
      const res = await fetchWithAutoRefresh('/company/api/banner_list/');
      const data = await res.json();
      imageList = data.banners || [];
    } catch (err) {
      console.error('Error fetching images:', err);
      imageList = [];
    }
  };

  // Render image grid in modal
  const renderLibrary = () => {
    const grid = document.getElementById('image-library-grid');
    grid.innerHTML = '';

    imageList.forEach(img => {
      const box = document.createElement('div');
      box.className = 'image-box thumb-container';
      box.dataset.id = img.id;

      box.innerHTML = `<img src="${img.image_url}" class="thumb-image rounded">`;

      if (selectedImageIds.has(img.id)) {
        box.classList.add('selected');
      }

      box.addEventListener('click', () => {
        toggleImageSelection(img.id, box);
        updateSelectAllCheckbox(); // keep it in sync
        updateConfirmButton();
      });

      grid.appendChild(box);
    });

    updateSelectAllCheckbox();
    updateConfirmButton();
  };


  // Toggle selection state
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

  // Sync select-all checkbox
  const updateSelectAllCheckbox = () => {
    const selectAllCheckbox = document.getElementById('select-all-images');
    const allSelected = imageList.length > 0 && imageList.every(img => selectedImageIds.has(img.id));
    selectAllCheckbox.checked = allSelected;
  };

  // Enable/disable confirm button
  const updateConfirmButton = () => {
    const confirmBtn = document.getElementById('confirm-image-selection');
    confirmBtn.disabled = selectedImageIds.size === 0;
  };

  // Handle select-all checkbox change
  const bindModalEvents = () => {
    const selectAll = document.getElementById('select-all-images');
    const confirmBtn = document.getElementById('confirm-image-selection');

    selectAll.addEventListener('change', () => {
      if (selectAll.checked) {
        imageList.forEach(img => selectedImageIds.add(img.id));
      } else {
        selectedImageIds.clear();
      }
      renderLibrary(); // re-render with updated selection
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

  // Open the modal
  const open = async (reset = false) => {
    if (reset) selectedImageIds.clear();
    await fetchImages();
    renderLibrary();
    $('#imageLibraryModal').modal('show');
  };

  return {
    init: bindModalEvents,
    open,
    getSelectedImageIds: () => Array.from(selectedImageIds),
    getSelectedImages: () => imageList.filter(img => selectedImageIds.has(img.id))
  };
})();
