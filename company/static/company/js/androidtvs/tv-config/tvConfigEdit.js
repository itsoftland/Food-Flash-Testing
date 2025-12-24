export function initEditHandlers(ctx) {
  window.addEventListener('tv-config-action', e => {
    const { action, id } = e.detail;

    if (action === 'view') openViewModal(id, ctx);
    if (action === 'edit') openEditModal(id, ctx);
    if (action === 'delete') openDeleteModal(id, ctx);
  });
}

/* ALL your existing edit/view/delete code goes here
   WITHOUT changing logic or names — only moved */
