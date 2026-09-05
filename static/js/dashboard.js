(function () {
    const MAX_FILE_SIZE = 20 * 1024 * 1024;
    const VALID_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp']);
    const VALID_MIME_TYPES = new Set([
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp'
    ]);

    const form = document.querySelector('#evaluateForm');
    if (!form) {
        return;
    }

    const alertBox = document.querySelector('#formAlert');
    const loadingScreen = document.querySelector('#loadingScreen');
    const evaluateBtn = document.querySelector('#evaluateBtn');
    const progressSteps = Array.from(document.querySelectorAll('[data-progress-step]'));
    const uploads = Array.from(document.querySelectorAll('[data-upload]'));
    const urls = new Map();
    let isSubmitting = false;

    function formatFileSize(bytes) {
        if (!bytes && bytes !== 0) return '';
        const mb = bytes / (1024 * 1024);
        if (mb >= 1) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
        return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }

    function escapeHtml(value) {
        return value.replace(/[&<>"]/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;'
        })[char]);
    }

    function getExtension(file) {
        return file.name.split('.').pop().toLowerCase();
    }

    function showAlert(message, type = 'error') {
        if (!alertBox) return;
        const icon = type === 'success' ? '✓' : type === 'info' ? 'i' : '⚠️';
        alertBox.className = `alert-custom ${type} visible`;
        alertBox.textContent = `${icon} ${message}`;
    }

    function clearAlert() {
        if (!alertBox) return;
        alertBox.className = 'alert-custom';
        alertBox.textContent = '';
    }

    function validateFile(file) {
        if (!file) {
            return { valid: false, message: 'No file selected.' };
        }

        if (file.size === 0) {
            return { valid: false, message: 'This file appears to be empty.' };
        }

        if (file.size > MAX_FILE_SIZE) {
            return { valid: false, message: 'File size must be below 20 MB.' };
        }

        const extension = getExtension(file);
        if (!VALID_EXTENSIONS.has(extension)) {
            return { valid: false, message: 'Unsupported file format. Upload a PDF or image file.' };
        }

        if (file.type && !VALID_MIME_TYPES.has(file.type) && !file.type.startsWith('image/')) {
            return { valid: false, message: 'Unsupported file format. Upload a PDF or image file.' };
        }

        return { valid: true };
    }

    function setInputFile(input, file) {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
    }

    function resetUpload(upload) {
        const input = upload.querySelector('input[type="file"]');
        const zone = upload.querySelector('.drag-drop-zone');
        const preview = upload.querySelector('[data-preview]');
        const previousUrl = urls.get(input.id);

        if (previousUrl) {
            URL.revokeObjectURL(previousUrl);
            urls.delete(input.id);
        }

        input.value = '';
        zone.classList.remove('has-file', 'drag-over');
        preview.innerHTML = '';
        clearAlert();
    }

    function renderPreview(upload, file) {
        const input = upload.querySelector('input[type="file"]');
        const zone = upload.querySelector('.drag-drop-zone');
        const preview = upload.querySelector('[data-preview]');
        const isImage = file.type.startsWith('image/');
        const previousUrl = urls.get(input.id);

        if (previousUrl) {
            URL.revokeObjectURL(previousUrl);
            urls.delete(input.id);
        }

        const safeName = escapeHtml(file.name);
        let media = '<div class="preview-doc" aria-hidden="true">PDF</div>';
        if (isImage) {
            const url = URL.createObjectURL(file);
            urls.set(input.id, url);
            media = `<div class="preview-thumb"><img src="${url}" alt="Preview of ${safeName}"></div>`;
        }

        preview.innerHTML = `
            <div class="preview-main">
                ${media}
                <div>
                    <p class="preview-name">${safeName}</p>
                    <p class="preview-meta">${formatFileSize(file.size)} · ${isImage ? 'Image file' : 'PDF document'}</p>
                </div>
            </div>
            <div class="preview-actions">
                <span class="status-badge ready">✓ Ready</span>
                <button class="btn-small" type="button" data-replace>Replace</button>
                <button class="btn-small" type="button" data-remove>Remove</button>
            </div>
        `;

        zone.classList.add('has-file');
    }

    function handleFile(upload, file) {
        const input = upload.querySelector('input[type="file"]');
        const result = validateFile(file);

        if (!result.valid) {
            resetUpload(upload);
            showAlert(result.message, 'error');
            return;
        }

        setInputFile(input, file);
        renderPreview(upload, file);
        showAlert(`${file.name} is ready for evaluation.`, 'success');
    }

    function setProgress(index) {
        progressSteps.forEach((step, stepIndex) => {
            step.classList.remove('done', 'active');
            const dot = step.querySelector('.step-dot');
            if (stepIndex < index) {
                step.classList.add('done');
                dot.textContent = '✓';
            } else if (stepIndex === index) {
                step.classList.add('active');
                dot.textContent = '●';
            } else {
                dot.textContent = '○';
            }
        });
    }

    function startLoadingState() {
        isSubmitting = true;
        evaluateBtn.disabled = true;
        evaluateBtn.textContent = 'Evaluation in progress...';
        loadingScreen.classList.remove('hidden');
        loadingScreen.setAttribute('aria-hidden', 'false');
        setProgress(0);

        [900, 1900, 3300, 5200].forEach((delay, index) => {
            window.setTimeout(() => setProgress(index + 1), delay);
        });
    }

    uploads.forEach((upload) => {
        const zone = upload.querySelector('.drag-drop-zone');
        const input = upload.querySelector('input[type="file"]');

        zone.addEventListener('click', (event) => {
            if (event.target.closest('button')) return;
            input.click();
        });

        zone.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                input.click();
            }
        });

        input.addEventListener('change', () => {
            if (input.files.length) {
                handleFile(upload, input.files[0]);
            }
        });

        ['dragenter', 'dragover'].forEach((eventName) => {
            zone.addEventListener(eventName, (event) => {
                event.preventDefault();
                zone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach((eventName) => {
            zone.addEventListener(eventName, (event) => {
                event.preventDefault();
                zone.classList.remove('drag-over');
            });
        });

        zone.addEventListener('drop', (event) => {
            const file = event.dataTransfer.files[0];
            if (file) {
                handleFile(upload, file);
            }
        });

        upload.addEventListener('click', (event) => {
            if (event.target.matches('[data-remove]')) {
                resetUpload(upload);
                showAlert('File removed.', 'info');
            }

            if (event.target.matches('[data-replace]')) {
                input.click();
            }
        });
    });

    form.addEventListener('submit', (event) => {
        clearAlert();

        if (isSubmitting) {
            event.preventDefault();
            return;
        }

        const questionInput = document.querySelector('#questionInput');
        const answerInput = document.querySelector('#answerInput');
        const keyInput = document.querySelector('#keyInput');

        if (!questionInput.files.length) {
            event.preventDefault();
            showAlert('Please upload the question paper.', 'error');
            return;
        }

        if (!answerInput.files.length) {
            event.preventDefault();
            showAlert('Please upload the student answer sheet.', 'error');
            return;
        }

        const files = [questionInput.files[0], answerInput.files[0]];
        if (keyInput.files.length) files.push(keyInput.files[0]);

        for (const file of files) {
            const result = validateFile(file);
            if (!result.valid) {
                event.preventDefault();
                showAlert(result.message, 'error');
                return;
            }
        }

        startLoadingState();
    });
})();
