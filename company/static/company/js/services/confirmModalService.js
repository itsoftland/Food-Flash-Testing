export const ConfirmModalService = (() => {
  const modal = document.getElementById("confirmationModal");
  const titleEl = document.getElementById("confirmationTitle");
  const messageEl = document.getElementById("confirmationMessage");
  const confirmBtn = document.getElementById("confirmOkBtn");
  const cancelBtn = document.getElementById("confirmCancelBtn");

  const defaultConfirmText = confirmBtn?.textContent?.trim() || "OK";
  const defaultCancelText = cancelBtn?.textContent?.trim() || "Cancel";

  let resolveCallback = null;

  const resetModalContent = () => {
    if (titleEl) {
      titleEl.textContent = "";
      titleEl.classList.add("hidden");
    }
    if (confirmBtn) confirmBtn.textContent = defaultConfirmText;
    if (cancelBtn) cancelBtn.textContent = defaultCancelText;
  };

  const show = (options = "Are you sure?") => {
    const config = typeof options === "string"
      ? { message: options }
      : (options || {});

    return new Promise((resolve) => {
      resolveCallback = resolve;

      if (titleEl) {
        if (config.title) {
          titleEl.textContent = config.title;
          titleEl.classList.remove("hidden");
        } else {
          titleEl.textContent = "";
          titleEl.classList.add("hidden");
        }
      }

      messageEl.innerHTML = config.message || "Are you sure?";
      if (confirmBtn && config.confirmButtonText) {
        confirmBtn.textContent = config.confirmButtonText;
      }
      if (cancelBtn && config.cancelButtonText) {
        cancelBtn.textContent = config.cancelButtonText;
      }

      modal.classList.remove("hidden");
      bindEvents();
    });
  };

  const hide = () => {
    modal.classList.add("hidden");
    unbindEvents();
    resetModalContent();
  };

  const bindEvents = () => {
    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
  };

  const unbindEvents = () => {
    confirmBtn.removeEventListener("click", onConfirm);
    cancelBtn.removeEventListener("click", onCancel);
  };

  const onConfirm = () => {
    resolveCallback?.(true);
    hide();
  };

  const onCancel = () => {
    resolveCallback?.(false);
    hide();
  };

  return {
    show
  };
})();
