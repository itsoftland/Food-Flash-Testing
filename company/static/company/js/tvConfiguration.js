// company/static/company/js/tvConfiguration.js

document.addEventListener('DOMContentLoaded', async function () {
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const ModalService = modalModule.ModalService;

    // DOM references
    const form = document.getElementById('tv-config-form');
    const showQrCheckbox = document.getElementById('show-qr');
    const qrSettingsGroup = document.getElementById('qr-settings-group');
    const utilitiesSelect = document.getElementById('utilities-select');
    const colorPickers = document.querySelectorAll('.color-picker');
    const enableAdsCheckbox = document.getElementById('enable-ads');
    const adFilesInput = document.getElementById('ad-files');
    const uploadAdsBtn = document.getElementById('upload-ads-btn');
    const adListContainer = document.getElementById('ad-list');
    const footerEnabledCheckbox = document.getElementById('footer-enabled');
    const footerTextsInput = document.getElementById('footer-texts');
    const footerTextsGroup = document.getElementById('footer-texts-group');
    const mappedDevicesSelect = document.getElementById('mapped-devices-select');

    function parseTvConfigPageFlags() {
        const defaults = { requireLinkedTv: false, hasLinkedTvChoices: false };
        const el = document.getElementById('tv-config-page-flags');
        if (!el) return defaults;
        try {
            return { ...defaults, ...JSON.parse(el.textContent) };
        } catch {
            return defaults;
        }
    }

    let choicesInstance = null;
    let selectedAdIds = [];

    function getOppositeAdPosition(qrPlacement) {
        return String(qrPlacement || '').includes('right') ? 'left' : 'right';
    }

    /* ------------------------------------
       Initialize Choices.js
    ------------------------------------ */
    function initializeChoices() {
        if (!utilitiesSelect) return;
        if (choicesInstance) choicesInstance.destroy();
        choicesInstance = new Choices(utilitiesSelect, {
            removeItemButton: true,
            itemSelectText: 'Click to select',
            placeholder: true,
            placeholderValue: 'Click to select utilities...',
            shouldSort: false,
        });
    }

    /* ------------------------------------
       Load active utilities
    ------------------------------------ */
    async function loadActiveUtilities() {
        if (!utilitiesSelect) return;
        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_UTILITIES, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json().catch(() => ({}));
            let utilities =
                data.utilities || data.results || (Array.isArray(data) ? data : []);

            utilitiesSelect.innerHTML = '';
            utilities.forEach(u => {
                const option = document.createElement('option');
                option.value = u.id;
                option.textContent = u.display_name || u.utility_name || u.name;
                utilitiesSelect.appendChild(option);
            });
            initializeChoices();

            if (!response.ok) {
                const msg =
                    data.error ||
                    data.message ||
                    'Could not load utilities. Check that an admin outlet is selected and try again.';
                ModalService.showError(msg);
            }
        } catch (error) {
            console.error('Error loading utilities:', error);
            utilitiesSelect.innerHTML = '';
            initializeChoices();
            ModalService.showError('Could not load utilities. Please refresh the page.');
        }
    }

    function adDeleteUrl(id) {
        return API_ENDPOINTS.TV_ADS_DELETE.replace('{id}', id);
    }
    function adUpdateUrl(id) {
        return API_ENDPOINTS.TV_ADS_UPDATE.replace('{id}', id);
    }

    function renderAds(ads) {
        if (!adListContainer) return;
        if (!ads || ads.length === 0) {
            adListContainer.innerHTML = '<p class="text-muted mb-0">No advertisements uploaded.</p>';
            selectedAdIds = [];
            return;
        }

        adListContainer.innerHTML = ads.map((ad) => `
            <div class="d-flex align-items-center justify-content-between border-bottom py-2">
                <div class="d-flex align-items-center gap-2">
                    <input type="checkbox" class="form-check-input ad-select" data-id="${ad.id}" checked />
                    <span class="badge bg-secondary">${ad.media_type.toUpperCase()}</span>
                    <input type="number" class="form-control form-control-sm ad-sequence" data-id="${ad.id}" value="${ad.sequence || 1}" min="1" style="width: 80px;" title="Sequence" />
                    <a href="${ad.media_url}" target="_blank" rel="noopener noreferrer">${ad.title || `Ad #${ad.id}`}</a>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger ad-remove" data-id="${ad.id}">
                    Remove
                </button>
            </div>
        `).join('');
        selectedAdIds = ads.map((ad) => ad.id);
    }

    async function loadAds() {
        if (!API_ENDPOINTS.TV_ADS_LIST) return;
        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.TV_ADS_LIST, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) return;
            const data = await response.json();
            renderAds(data.ads || []);
        } catch (error) {
            console.error('Error loading ads:', error);
        }
    }

    const MAX_TV_AD_BYTES = 100 * 1024 * 1024;
    const MAX_ADS_PER_CONFIG = 15;

    async function uploadAds() {
        const files = adFilesInput?.files;
        if (!files || files.length === 0) {
            ModalService.showError('Please choose at least one ad file.');
            return;
        }

        const oversized = Array.from(files).filter((f) => f.size > MAX_TV_AD_BYTES);
        if (oversized.length > 0) {
            ModalService.showError(
                `Each file must be 100MB or smaller. Too large: ${oversized.map((f) => f.name).join(', ')}`
            );
            return;
        }

        const body = new FormData();
        Array.from(files).forEach((file) => body.append('ads', file));

        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.TV_ADS_UPLOAD, {
                method: 'POST',
                body
            });
            const result = await response.json();
            if (!response.ok) {
                ModalService.showError(result.error || 'Failed to upload advertisements.');
                return;
            }
            adFilesInput.value = '';
            ModalService.showSuccess(result.message || 'Advertisements uploaded.');
            await loadAds();
        } catch (error) {
            console.error('Error uploading ads:', error);
            ModalService.showError('Failed to upload advertisements.');
        }
    }

    /* ------------------------------------
       Handle QR Toggle
    ------------------------------------ */
    showQrCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            qrSettingsGroup.classList.remove('hidden');
        } else {
            qrSettingsGroup.classList.add('hidden');
        }
    });

    footerEnabledCheckbox?.addEventListener('change', (e) => {
        if (!footerTextsGroup) return;
        footerTextsGroup.style.display = e.target.checked ? '' : 'none';
    });

    uploadAdsBtn?.addEventListener('click', uploadAds);

    adListContainer?.addEventListener('click', async (e) => {
        const removeBtn = e.target.closest('.ad-remove');
        if (!removeBtn) return;
        const adId = removeBtn.dataset.id;
        if (!adId) return;
        try {
            const response = await fetchWithAutoRefresh(adDeleteUrl(adId), { method: 'DELETE' });
            const result = await response.json();
            if (!response.ok) {
                ModalService.showError(result.error || 'Failed to delete advertisement.');
                return;
            }
            await loadAds();
        } catch (error) {
            console.error('Error deleting ad:', error);
            ModalService.showError('Failed to delete advertisement.');
        }
    });

    adListContainer?.addEventListener('change', (e) => {
        const seqInput = e.target.closest('.ad-sequence');
        if (seqInput) {
            const adId = parseInt(seqInput.dataset.id, 10);
            const sequence = parseInt(seqInput.value, 10);
            if (!adId || !sequence || sequence < 1) return;
            fetchWithAutoRefresh(adUpdateUrl(adId), {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sequence })
            }).then(() => loadAds()).catch((error) => console.error('Error updating ad sequence:', error));
            return;
        }

        const checkbox = e.target.closest('.ad-select');
        if (!checkbox) return;
        const adId = parseInt(checkbox.dataset.id, 10);
        if (!adId) return;
        if (checkbox.checked) {
            if (!selectedAdIds.includes(adId)) selectedAdIds.push(adId);
        } else {
            selectedAdIds = selectedAdIds.filter((id) => id !== adId);
        }
    });

    /* ------------------------------------
       Handle Color Pickers
    ------------------------------------ */
    colorPickers.forEach(picker => {
        picker.addEventListener('input', (e) => {
            const span = e.target.parentElement.querySelector('.color-code');
            if (span) span.textContent = e.target.value.toUpperCase();
        });
    });

    /* ------------------------------------
       Handle Form Submission
    ------------------------------------ */
    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const tvFlags = parseTvConfigPageFlags();
        if (tvFlags.requireLinkedTv) {
            if (!tvFlags.hasLinkedTvChoices) {
                ModalService.showError(
                    'No unmapped vendor-linked TVs are available. Link a TV to an outlet on Android TVs, then return here.'
                );
                return;
            }
            if (mappedDevicesSelect && !String(mappedDevicesSelect.value || '').trim()) {
                ModalService.showError('Please select a TV to link to this configuration.');
                return;
            }
        }

        const formData = new FormData(form);
        const footerTexts = (footerTextsInput?.value || '')
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
        const payload = {
            screen_orientation: formData.get('screen_orientation'),
            token_font_size: formData.get('token_font_size'),
            counter_font_size: formData.get('counter_font_size'),
            utility_font_size: formData.get('utility_font_size'),
            token_text_color: formData.get('token_text_color'),
            counter_text_color: formData.get('counter_text_color'),
            utility_text_color: formData.get('utility_text_color'),
            header_font_size: formData.get('header_font_size'),
            header_font_style: formData.get('header_font_style'),
            header_text_color: formData.get('header_text_color'),
            show_customer_name: formData.get('show_customer_name') === 'on',
            show_phone_number: formData.get('show_phone_number') === 'on',
            show_order_details: formData.get('show_order_details') === 'on',
            audio_enabled: formData.get('audio_enabled') === 'on',
            announcement_language: formData.get('announcement_language'),
            blink_token: formData.get('blink_token') === 'on',
            blink_utility: formData.get('blink_utility') === 'on',
            show_qr: showQrCheckbox.checked,
            qr_placement: formData.get('qr_placement'),
            qr_base_url: formData.get('qr_base_url') || null,
            items_to_show: parseInt(formData.get('items_to_show')),
            utility_name_mode: formData.get('utility_name_mode'),
            // Dine Flash display is driven by visibility switches; keep a stable token field for API validation.
            booking_fields: ['token'],
            utilities: choicesInstance
                ? choicesInstance
                    .getValue()
                    .map((i) => parseInt(i.value, 10))
                    .filter((id) => Number.isFinite(id))
                : [],
            enable_ads: enableAdsCheckbox ? enableAdsCheckbox.checked : false,
            ad_position: getOppositeAdPosition(formData.get('qr_placement')),
            ad_interval: parseInt(formData.get('ad_interval') || '8', 10),
            video_ad_mode: formData.get('video_ad_mode') || 'play_full',
            footer_enabled: footerEnabledCheckbox ? footerEnabledCheckbox.checked : false,
            footer_texts: footerTexts,
            advertisement_ids: selectedAdIds
        };
        if (mappedDevicesSelect) {
            const raw = mappedDevicesSelect.value;
            const one = raw ? parseInt(raw, 10) : NaN;
            if (Number.isFinite(one)) {
                payload.device_ids = [one];
            }
        }

        if (formData.has('display_rows')) {
            payload.display_rows = parseInt(formData.get('display_rows'));
        }
        if (formData.has('display_columns')) {
            payload.display_columns = parseInt(formData.get('display_columns'));
        }

        if (payload.footer_texts.length > 8) {
            ModalService.showError('Maximum 8 footer texts are allowed.');
            return;
        }
        if (payload.footer_enabled && payload.footer_texts.length === 0) {
            ModalService.showError('Add at least one footer text when footer is enabled.');
            return;
        }
        if (payload.advertisement_ids.length > MAX_ADS_PER_CONFIG) {
            ModalService.showError(`You can assign at most ${MAX_ADS_PER_CONFIG} advertisements per configuration.`);
            return;
        }

        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_TV_CONFIG, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (response.ok) {
                ModalService.showSuccess(result.message || 'Configuration created successfully!', () => {
                    window.location.href = `${window.BASE}company/tv_config_list_page/`;
                });
            } else {
                let detailedError = result.message || result.error;
                if (!detailedError && result.errors && typeof result.errors === 'object') {
                    detailedError = Object.entries(result.errors)
                        .map(([field, msgs]) => {
                            const messageText = Array.isArray(msgs) ? msgs.join(', ') : String(msgs);
                            return `${field}: ${messageText}`;
                        })
                        .join('\n');
                }
                ModalService.showError(detailedError || 'Failed to save configuration.');
            }
        } catch (error) {
            console.error('Error saving config:', error);
            ModalService.showError('An unexpected error occurred.');
        }
    });

    /* ------------------------------------
       Initialize
    ------------------------------------ */
    await loadActiveUtilities();
    await loadAds();
    if (footerTextsGroup && footerEnabledCheckbox && !footerEnabledCheckbox.checked) {
        footerTextsGroup.style.display = 'none';
    }
});
