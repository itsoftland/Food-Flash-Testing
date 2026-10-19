/**
 * Shared helpers for Create / Edit advertisement profile forms.
 * Forms on a given page use the same element IDs (see new_profile.html / edit modal).
 */

export function setupSelectAllDays() {
  const selectAll = document.getElementById('select-all-days');
  if (!selectAll || selectAll.dataset.bound === '1') return;
  selectAll.dataset.bound = '1';
  selectAll.addEventListener('change', function () {
    const isChecked = this.checked;
    document.querySelectorAll('.day-checkbox').forEach(cb => {
      cb.checked = isChecked;
    });
  });
}

export function setupTimeSlotHandlers(ModalService) {
  const slotsContainer = document.getElementById('time-slots-container');
  const addSlotBtn = document.getElementById('add-slot-btn');
  if (!slotsContainer || !addSlotBtn || addSlotBtn.dataset.bound === '1') return;
  addSlotBtn.dataset.bound = '1';

  slotsContainer.querySelectorAll('.time-slot').forEach(slot => setupSlotValidation(slot, ModalService));

  addSlotBtn.addEventListener('click', () => {
    const slots = slotsContainer.querySelectorAll('.time-slot');
    const lastSlot = slots[slots.length - 1];
    const newSlot = lastSlot.cloneNode(true);

    newSlot.querySelectorAll('input').forEach(input => { input.value = ''; });
    newSlot.querySelector('.remove-slot-btn')?.classList.remove('d-none');

    slotsContainer.appendChild(newSlot);
    setupSlotValidation(newSlot, ModalService);
  });

  slotsContainer.addEventListener('click', e => {
    if (e.target.closest('.remove-slot-btn')) {
      e.target.closest('.time-slot').remove();
      document.querySelectorAll('.time-slot').forEach(slot => updateEndTimeMin(slot));
    }
  });
}

function setupSlotValidation(slot, ModalService) {
  const startInput = slot.querySelector('.start-time');
  const endInput = slot.querySelector('.end-time');

  startInput.addEventListener('change', () => {
    const slots = [...document.querySelectorAll('.time-slot')];
    const index = slots.indexOf(slot);
    const startMins = getTimeValue(startInput.value);

    if (index > 0) {
      const prevEnd = slots[index - 1].querySelector('.end-time').value;
      if (prevEnd && startMins <= getTimeValue(prevEnd)) {
        ModalService.showError(`Slot ${index + 1}: Start time must be after previous slot's end time.`);
        startInput.value = '';
        return;
      }
    }

    if (endInput.value) {
      const endMins = getTimeValue(endInput.value);
      if (startMins >= endMins) {
        ModalService.showError(`Slot ${index + 1}: Start time must be before its end time.`);
        startInput.value = '';
        return;
      }
    }

    updateEndTimeMin(slot);
  });

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

function getTimeValue(timeStr) {
  const [h, m] = timeStr.split(':').map(Number);
  return h * 60 + m;
}

function formatTime(totalMins) {
  const h = String(Math.floor(totalMins / 60)).padStart(2, '0');
  const m = String(totalMins % 60).padStart(2, '0');
  return `${h}:${m}`;
}

export function getTimeSlots() {
  return [...document.querySelectorAll('.time-slot')]
    .map(slot => ({
      start: slot.querySelector('.start-time').value,
      end: slot.querySelector('.end-time').value,
    }))
    .filter(slot => slot.start && slot.end);
}

export function validateAllTimeSlots(ModalService) {
  const slots = [...document.querySelectorAll('.time-slot')];
  let prevEndMins = null;

  for (let i = 0; i < slots.length; i++) {
    const slot = slots[i];
    const startInput = slot.querySelector('.start-time');
    const endInput = slot.querySelector('.end-time');

    if ((startInput.value && !endInput.value) || (!startInput.value && endInput.value)) {
      ModalService.showError(`Slot ${i + 1}: Both start and end times are required if either is provided.`);
      return false;
    }

    if (!startInput.value && !endInput.value) {
      continue;
    }

    const startMins = getTimeValue(startInput.value);
    const endMins = getTimeValue(endInput.value);

    if (endMins <= startMins) {
      ModalService.showError(`Slot ${i + 1}: End time must be after start time.`);
      return false;
    }

    if (prevEndMins !== null && startMins < prevEndMins) {
      ModalService.showError(`Slot ${i + 1}: Start time must be after previous slot's end time.`);
      return false;
    }

    prevEndMins = endMins;
  }

  return true;
}

export function buildProfilePayload(imageIds) {
  return {
    name: document.getElementById('profile-name').value,
    date_start: document.getElementById('date-start').value || null,
    date_end: document.getElementById('date-end').value || null,
    days_active: Array.from(document.querySelectorAll('.day-checkbox:checked')).map(cb => cb.value),
    priority: parseInt(document.getElementById('priority').value, 10),
    image_ids: imageIds,
    time_slots: getTimeSlots(),
  };
}

export function populateProfileForm(profile) {
  document.getElementById('profile-name').value = profile.name || '';
  document.getElementById('date-start').value = profile.date_start || '';
  document.getElementById('date-end').value = profile.date_end || '';
  document.getElementById('priority').value = String(profile.priority ?? 1);

  const activeDays = profile.days_active || [];
  document.querySelectorAll('.day-checkbox').forEach(cb => {
    cb.checked = activeDays.includes(cb.value);
  });
  const selectAll = document.getElementById('select-all-days');
  if (selectAll) {
    const allDays = document.querySelectorAll('.day-checkbox');
    selectAll.checked = allDays.length > 0 && [...allDays].every(cb => cb.checked);
  }

  populateTimeSlots(profile.time_slots || []);
}

export function rebindTimeSlotValidation(ModalService) {
  document.querySelectorAll('.time-slot').forEach(slot => {
    if (slot.dataset.slotBound === '1') return;
    slot.dataset.slotBound = '1';
    setupSlotValidation(slot, ModalService);
  });
}

export function populateTimeSlots(timeSlots) {
  const slotsContainer = document.getElementById('time-slots-container');
  if (!slotsContainer) return;

  const existing = slotsContainer.querySelector('.time-slot');
  if (!existing) return;
  const template = existing.cloneNode(true);

  slotsContainer.innerHTML = '';

  const slotsToRender = timeSlots.length > 0 ? timeSlots : [{ start: '', end: '' }];

  slotsToRender.forEach((slot, index) => {
    const row = template.cloneNode(true);
    row.querySelector('.start-time').value = slot.start || '';
    row.querySelector('.end-time').value = slot.end || '';
    const removeBtn = row.querySelector('.remove-slot-btn');
    if (removeBtn) {
      if (index === 0 && slotsToRender.length === 1) {
        removeBtn.classList.add('d-none');
      } else {
        removeBtn.classList.remove('d-none');
      }
    }
    slotsContainer.appendChild(row);
  });
}

export function parseApiErrorMessage(result) {
  let msg = 'Something went wrong.';
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
  return msg;
}
