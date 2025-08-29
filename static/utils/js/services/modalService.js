// static/utils/js/services/modalService.js

export const ModalService = (() => {
  const showError = (message = "An unknown error occurred.", onOkCallback = null) => {
    const modalBody = document.getElementById('errorModalBody');
    modalBody.innerText = message;

    const errorModalEl = document.getElementById('errorModal');
    const errorModal = new bootstrap.Modal(errorModalEl, {
      backdrop: 'static',
      keyboard: false
    });

    // Replace OK button to remove old listeners
    const okBtn = errorModalEl.querySelector('.error-ok-btn');
    const newOkBtn = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOkBtn, okBtn);

    newOkBtn.addEventListener('click', () => {
      if (typeof onOkCallback === 'function') {
        onOkCallback();
      }
      errorModal.hide(); // Close modal after OK is clicked
    });

    errorModal.show();
  };


  const showSuccess = (message = "Operation completed successfully.", onOkCallback = null) => {
    const modalBody = document.getElementById('successModalBody');
    const successModalEl = document.getElementById('successModal');
    const successModal = new bootstrap.Modal(successModalEl, {
      backdrop: 'static',   // Prevent close on outside click
      keyboard: false       // Prevent close on ESC key
    });

    modalBody.innerText = message;

    // Replace OK button to remove any previous click listeners
    const okBtn = successModalEl.querySelector('.success-ok-btn');
    const newOkBtn = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOkBtn, okBtn);

    newOkBtn.addEventListener('click', () => {
      if (typeof onOkCallback === 'function') {
        onOkCallback();
      }
    });

    successModal.show();
  };

  const showCustom = ({ title, body, onShown }) => {
    const modalEl = document.getElementById("customModal");
    modalEl.querySelector(".modal-title").innerHTML = title;
    modalEl.querySelector(".modal-body").innerHTML = body;

    const modal = new bootstrap.Modal(modalEl, {
      backdrop: 'static',
      keyboard: false
    });

    modal.show();

    if (typeof onShown === 'function') {
      setTimeout(onShown, 100);
    }
  };

  return {
    showError,
    showSuccess,
    showCustom
  };
})();
