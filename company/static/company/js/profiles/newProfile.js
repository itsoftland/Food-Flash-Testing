import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { ImageLibraryService } from '../services/imageLibraryService.js';
import { ModalService } from '/food_flash/static/utils/js/services/modalService.js';
import { API_ENDPOINTS, WEB_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';

document.addEventListener('DOMContentLoaded', async () => {
  ImageLibraryService.init();
  setupFormSubmitHandler();
  setupTimeSlotHandlers();
  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });
});

// =================== SELECT ALL DAYS ===================
document.getElementById('select-all-days').addEventListener('change', function () {
  const isChecked = this.checked;
  document.querySelectorAll('.day-checkbox').forEach(cb => {
    cb.checked = isChecked;
  });
});

// =================== FORM SUBMIT ===================
function setupFormSubmitHandler() {
  document.getElementById('create-profile-form').addEventListener('submit', async function (e) {
    e.preventDefault();

    const payload = {
      name: document.getElementById('profile-name').value,
      date_start: document.getElementById('date-start').value || null,
      date_end: document.getElementById('date-end').value || null,
      days_active: Array.from(document.querySelectorAll('.day-checkbox:checked')).map(cb => cb.value),
      priority: parseInt(document.getElementById('priority').value),
      image_ids: ImageLibraryService.getSelectedImageIds(),
      time_slots: getTimeSlots()
    };

    if (!validateAllTimeSlots()) return;

    try {
      const res = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_AD_PROFILE, {
        method: 'POST',
        headers: { 'X-CSRFToken': AppUtils.getCSRFToken() },
        body: JSON.stringify(payload)
      });

      const result = await res.json();

      if (res.ok) {
        ModalService.showSuccess("Profile Created Successfully", () => {
          this.reset();
          document.getElementById('selected-images-preview').innerHTML = '';
          window.location.href = WEB_ENDPOINTS.PROFILE_LIST;
        });
      } else {
        let msg = "Something went wrong.";
        if (result?.details) {
          const errorDetails = result.details;
          if (Array.isArray(errorDetails.non_field_errors)) {
            msg = errorDetails.non_field_errors.join('\n');
          } else {
            msg = Object.entries(errorDetails).map(
              ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
            ).join('\n');
          }
        } else if (result?.error) msg = result.error;
        else if (result?.message) msg = result.message;

        ModalService.showError(msg);
      }
    } catch (err) {
      ModalService.showError("Unexpected error while creating profile.");
    }
  });
}

// =================== IMAGE LIBRARY ===================
document.getElementById('open-image-library-btn')?.addEventListener('click', () => {
  ImageLibraryService.open();
});

// =================== TIME SLOT HANDLERS ===================
function setupTimeSlotHandlers() {
  const slotsContainer = document.getElementById('time-slots-container');
  const addSlotBtn = document.getElementById('add-slot-btn');

  // Initialize existing slots
  slotsContainer.querySelectorAll('.time-slot').forEach(slot => setupSlotValidation(slot));

  // Add new slot
  addSlotBtn.addEventListener('click', () => {
    const slots = slotsContainer.querySelectorAll('.time-slot');
    const lastSlot = slots[slots.length - 1];
    const newSlot = lastSlot.cloneNode(true);

    newSlot.querySelectorAll('input').forEach(input => input.value = '');
    newSlot.querySelector('.remove-slot-btn').classList.remove('d-none');

    slotsContainer.appendChild(newSlot);
    setupSlotValidation(newSlot);
  });

  // Remove slot
  slotsContainer.addEventListener('click', e => {
    if (e.target.closest('.remove-slot-btn')) {
      e.target.closest('.time-slot').remove();
      document.querySelectorAll('.time-slot').forEach(slot => updateEndTimeMin(slot));
    }
  });
}

// =================== TIME SLOT VALIDATION ===================
function setupSlotValidation(slot) {
  const startInput = slot.querySelector('.start-time');
  const endInput = slot.querySelector('.end-time');

  // Validate start against previous slot and its own end
  startInput.addEventListener('change', () => {
    const slots = [...document.querySelectorAll('.time-slot')];
    const index = slots.indexOf(slot);
    const startMins = getTimeValue(startInput.value);

    // Previous slot end validation
    if (index > 0) {
      const prevEnd = slots[index - 1].querySelector('.end-time').value;
      if (prevEnd && startMins <= getTimeValue(prevEnd)) {
        ModalService.showError(`Slot ${index + 1}: Start time must be after previous slot's end time.`);
        startInput.value = '';
        return;
      }
    }

    // Must be before its own end time if filled
    if (endInput.value) {
      const endMins = getTimeValue(endInput.value);
      if (startMins >= endMins) {
        ModalService.showError(`Slot ${index + 1}: Start time must be before its end time.`);
        startInput.value = '';
        return;
      }
    }

    // Update min for current slot end
    updateEndTimeMin(slot);
  });

  // Validate end against start in real-time
  endInput.addEventListener('change', () => {
    if (!startInput.value) return;
    const startMins = getTimeValue(startInput.value);
    const endMins = getTimeValue(endInput.value);
    if (endMins <= startMins) {
      ModalService.showError('End time must be after start time.');
      endInput.value = '';
    }
  });

  updateEndTimeMin(slot);
}


// =================== SHARED SLOT VALIDATION ===================
function validateSlotChange(slot, changedField) {
  const slots = [...document.querySelectorAll('.time-slot')];
  const index = slots.indexOf(slot);

  const startInput = slot.querySelector('.start-time');
  const endInput = slot.querySelector('.end-time');
  const startMins = getTimeValue(startInput.value || '00:00');
  const endMins = getTimeValue(endInput.value || '00:00');

  // Previous slot validation
  if (index > 0) {
    const prevEnd = getTimeValue(slots[index - 1].querySelector('.end-time').value || '00:00');
    if (startMins <= prevEnd) {
      if (changedField === 'start') startInput.value = '';
      ModalService.showError(`Slot ${index + 1}: Start time must be after previous slot's end time.`);
      return;
    }
  }

  // Current slot end validation
  if (endInput.value && endMins <= startMins) {
    if (changedField === 'end') endInput.value = '';
    if (changedField === 'end') ModalService.showError(`Slot ${index + 1}: End time must be after start time.`);
    return;
  }

  // Next slot start validation
  if (index < slots.length - 1) {
    const nextStartInput = slots[index + 1].querySelector('.start-time');
    const nextStart = getTimeValue(nextStartInput.value || '00:00');
    if (startMins >= nextStart && nextStartInput.value) {
      if (changedField === 'start') startInput.value = '';
      if (changedField === 'end') endInput.value = '';
      ModalService.showError(`Slot ${index + 1}: Cannot overlap next slot's start time.`);
      return;
    }

    const nextEndInput = slots[index + 1].querySelector('.end-time');
    const nextEnd = getTimeValue(nextEndInput.value || '00:00');
    if (endMins >= nextStart && nextStartInput.value) {
      if (changedField === 'end') endInput.value = '';
      ModalService.showError(`Slot ${index + 1}: End time cannot exceed next slot's start time.`);
      return;
    }
  }

  // Update min for current and subsequent slots
  for (let i = index; i < slots.length; i++) updateEndTimeMin(slots[i]);
}

// =================== UPDATE END TIME MIN ===================
function updateEndTimeMin(slot) {
  const startInput = slot.querySelector('.start-time');
  const endInput = slot.querySelector('.end-time');
  if (!startInput.value) return;

  const slots = [...document.querySelectorAll('.time-slot')];
  const index = slots.indexOf(slot);
  let minMins = getTimeValue(startInput.value);

  if (index > 0) {
    const prevEnd = slots[index - 1].querySelector('.end-time').value;
    if (prevEnd) minMins = Math.max(minMins, getTimeValue(prevEnd));
  }

  endInput.min = formatTime(minMins);

  if (endInput.value && getTimeValue(endInput.value) <= minMins) endInput.value = '';
}

// =================== HELPER: TIME TO MINUTES ===================
function getTimeValue(timeStr) {
  const [h, m] = timeStr.split(':').map(Number);
  return h * 60 + m;
}

// =================== HELPER: FORMAT MINUTES TO HH:MM ===================
function formatTime(totalMins) {
  const h = String(Math.floor(totalMins / 60)).padStart(2, '0');
  const m = String(totalMins % 60).padStart(2, '0');
  return `${h}:${m}`;
}

// =================== COLLECT TIME SLOTS ===================
function getTimeSlots() {
  return [...document.querySelectorAll('.time-slot')].map(slot => ({
    start: slot.querySelector('.start-time').value,
    end: slot.querySelector('.end-time').value
  }));
}

// =================== VALIDATE ALL SLOTS ===================
function validateAllTimeSlots() {
  const slots = [...document.querySelectorAll('.time-slot')];
  let prevEndMins = null;

  for (let i = 0; i < slots.length; i++) {
    const slot = slots[i];
    const startInput = slot.querySelector('.start-time');
    const endInput = slot.querySelector('.end-time');

    if (!startInput.value || !endInput.value) {
      ModalService.showError(`Slot ${i + 1}: Both start and end times are required.`);
      return false;
    }

    const startMins = getTimeValue(startInput.value);
    const endMins = getTimeValue(endInput.value);

    // End time must be after start time
    if (endMins <= startMins) {
      ModalService.showError(`Slot ${i + 1}: End time must be after start time.`);
      return false;
    }

    // Start must be after previous slot's end time
    if (prevEndMins !== null && startMins < prevEndMins) {
      ModalService.showError(`Slot ${i + 1}: Start time must be after previous slot's end time.`);
      return false;
    }

    // Start must be before current slot's end time
    if (startMins >= endMins) {
      startInput.value = '';
      ModalService.showError(`Slot ${i + 1}: Start time must be less than current slot's end time.`);
      return false;
    }

    prevEndMins = endMins;
  }

  return true;
}

