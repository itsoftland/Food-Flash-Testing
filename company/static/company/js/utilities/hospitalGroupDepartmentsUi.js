function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function setGroupDepartmentCheckboxMessage(container, message) {
  if (!container) return;
  container.innerHTML = `<p class="text-muted small mb-0">${escapeHtml(message)}</p>`;
}

export function renderGroupDepartmentCheckboxes(container, departments, selectedIds = []) {
  if (!container) return;

  if (!Array.isArray(departments) || !departments.length) {
    setGroupDepartmentCheckboxMessage(container, 'No individual departments available');
    return;
  }

  const selected = new Set(
    (selectedIds || []).map((id) => Number(id)).filter((id) => !Number.isNaN(id))
  );

  container.innerHTML = departments.map((dept) => {
    const id = Number(dept.id);
    const label = `${dept.display_name || dept.utility_name} (${dept.display_code || dept.utility_name})`;
    const isChecked = Boolean(dept.selected) || selected.has(id);
    const inputId = `group-dept-cb-${id}`;

    return `
      <div class="form-check hospital-group-dept-check">
        <input
          class="form-check-input group-department-checkbox"
          type="checkbox"
          name="group_department_ids"
          value="${id}"
          id="${inputId}"
          ${isChecked ? 'checked' : ''}
        >
        <label class="form-check-label" for="${inputId}">${escapeHtml(label)}</label>
      </div>
    `;
  }).join('');
}

export function getSelectedGroupDepartmentIds(container) {
  if (!container) return [];

  return Array.from(container.querySelectorAll('input.group-department-checkbox:checked'))
    .map((input) => parseInt(input.value, 10))
    .filter((id) => !Number.isNaN(id));
}
