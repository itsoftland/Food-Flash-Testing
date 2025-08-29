export const ConfirmModalService = (() => {
  const modal = document.getElementById("confirmationModal");
  const messageEl = document.getElementById("confirmationMessage");
  const confirmBtn = document.getElementById("confirmOkBtn");
  const cancelBtn = document.getElementById("confirmCancelBtn");

  let resolveCallback = null;

  const show = (message = "Are you sure?") => {
    return new Promise((resolve) => {
      resolveCallback = resolve;
      messageEl.textContent = message;
      modal.classList.remove("hidden");
      bindEvents();
    });
  };

  const hide = () => {
    modal.classList.add("hidden");
    unbindEvents();
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
