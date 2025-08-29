export default function createLoaderService(form) {
  const loaderOverlay = document.getElementById("loaderOverlay");
  const loaderStatus = document.getElementById("loaderStatus");
  const okButton = document.getElementById("loaderOkBtn");
  const submitButton = form.querySelector('button[type="submit"]');

  let okCallback = null; // Store callback for OK button

  function showLoader(message = "Submitting data...", waitForUser = false, callback = null) {

    if (loaderOverlay) {
      loaderOverlay.style.display = "flex";
    }

    if (loaderStatus) {
      loaderStatus.textContent = message;
    }

    if (submitButton) {
      submitButton.disabled = true;
    }

    if (okButton) {
      if (waitForUser) {
        okButton.style.display = "inline-block";
        okCallback = callback;
      } else {
        okButton.style.display = "none";
        okCallback = null;
      }
    }
  }

  function updateLoaderStatus(message, waitForUser = false, callback = null) {

    if (loaderStatus) {
      loaderStatus.textContent = message;
    }

    if (okButton) {
      if (waitForUser) {
        okButton.style.display = "inline-block";
        okCallback = callback;

        if (loaderOverlay) {
          loaderOverlay.style.display = "flex"
        }

        if (submitButton) {
          submitButton.disabled = true;
        }
      } else {
        okButton.style.display = "none";
        okCallback = null;

        if (loaderOverlay) {
          loaderOverlay.style.display = "none";
        }

        if (submitButton) {
          submitButton.disabled = false;
        }
      }
    }
  }
  async function awaitConfirmation(message) {
    return new Promise((resolve) => {
      updateLoaderStatus(message, true, () => resolve(true));
    });
  }
  function hideLoader() {
    if (loaderOverlay) {
      loaderOverlay.style.display = "none";
    }

    if (submitButton) {
      submitButton.disabled = false;
    }

    if (okButton) {
      okButton.style.display = "none";
    }
  }

  // Bind OK button only once
  if (okButton && !okButton.dataset.bound) {
    okButton.addEventListener("click", () => {
      if (okCallback) {
        const callback = okCallback;
        okCallback = null;
        hideLoader();       
        callback();         
      } else {
        hideLoader();
      }
    });
    okButton.dataset.bound = "true";
  }
  

  return {
    showLoader,
    updateLoaderStatus,
    hideLoader,
    awaitConfirmation
  };
}
