export const MenuFileManagerService = (() => {
    const fileListContainer = document.getElementById("menu-files-container"); 
    const menuContent = document.getElementById("menuContent");
    const menuModal = document.getElementById("menuImageModal");
    let modalInstance = null;

    let currentFiles = [];

    const renderFileList = () => {
        fileListContainer.innerHTML = "";

        if (currentFiles.length === 0) {
            fileListContainer.innerHTML = `<p class="text-muted">No menu files selected.</p>`;
            return;
        }

        currentFiles.forEach((url, index) => {
            const fileItem = document.createElement("div");
            // Add a custom class "file-item" for any additional styling if needed.
            fileItem.className = "d-flex align-items-center justify-content-between mb-2 p-2 border rounded bg-light file-item";

            const fileName = url.split('/').pop();

            const label = document.createElement("span");
            label.textContent = fileName;
            // Use a custom class "file-label" instead of inline styles.
            label.className = "fw-medium px-2 py-1 rounded file-label";

            label.addEventListener("click", () => openPreviewModal(url));

            const removeBtn = document.createElement("button");
            removeBtn.innerHTML = "&times;";
            // Use a custom class "remove-btn" for the remove button.
            removeBtn.className = "ms-2 px-2 py-1 border-0 rounded-circle remove-btn";
            removeBtn.title = "Remove";

            removeBtn.addEventListener("click", () => {
                currentFiles.splice(index, 1);
                renderFileList(); // re-render after deletion
            });

            fileItem.appendChild(label);
            fileItem.appendChild(removeBtn);
            fileListContainer.appendChild(fileItem);
        });
    };

    const openPreviewModal = (url) => {
        menuContent.innerHTML = "";

        if (url.endsWith(".pdf")) {
            menuContent.innerHTML = `<iframe src="${url}" width="100%" height="500px" frameborder="0"></iframe>`;
        } else {
            menuContent.innerHTML = `<img src="${url}" class="img-fluid rounded" alt="Menu Preview" onerror="this.src='/static/orders/files/menu.jpg'">`;
        }

        if (!modalInstance) {
            modalInstance = new bootstrap.Modal(menuModal, {
                backdrop: 'static',
                keyboard: true
            });
        }

        modalInstance.show();
    };

    const setFiles = (fileUrls) => {
        currentFiles = [...fileUrls];
        renderFileList();
    };

    const getFiles = () => currentFiles;

    return {
        init: setFiles,
        getFiles,
        openPreviewModal,
    };
})();
