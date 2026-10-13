(() => {
  const offlineNotice = document.getElementById('offline-notice');

  function updateOnlineState() {
    if (offlineNotice) offlineNotice.hidden = navigator.onLine;
  }
  window.addEventListener('online', updateOnlineState);
  window.addEventListener('offline', updateOnlineState);
  updateOnlineState();

  document.querySelectorAll('form[data-submit-lock]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.submitting === '1') {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = '1';
      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((button) => {
        button.disabled = true;
        if (button.dataset.savingText) {
          button.dataset.originalText = button.textContent;
          button.textContent = button.dataset.savingText;
        }
      });
    });
  });

  document.querySelectorAll('form[data-draft-form]').forEach((form) => {
    const key = form.dataset.draftKey;
    const status = form.querySelector('[data-draft-status]');
    if (!key) return;

    const fields = Array.from(form.querySelectorAll('input[name]:not([type="hidden"]):not([type="file"]), textarea[name], select[name]'));
    let dirty = false;

    function collect() {
      const data = {};
      fields.forEach((field) => {
        if (field.type === 'checkbox' || field.type === 'radio') data[field.name] = field.checked;
        else data[field.name] = field.value;
      });
      data.savedAt = new Date().toISOString();
      return data;
    }

    function saveDraft() {
      if (!dirty) return;
      try {
        localStorage.setItem(key, JSON.stringify(collect()));
        if (status) status.textContent = 'Concept lokaal bewaard.';
      } catch (_) {
        if (status) status.textContent = 'Concept kon niet lokaal worden bewaard.';
      }
    }

    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('saved') === '1') {
        localStorage.removeItem(key);
        if (status) status.textContent = 'Dag is op de server opgeslagen.';
      } else {
        const raw = localStorage.getItem(key);
        if (raw) {
          const draft = JSON.parse(raw);
          fields.forEach((field) => {
            if (!(field.name in draft)) return;
            if (field.type === 'checkbox' || field.type === 'radio') field.checked = Boolean(draft[field.name]);
            else field.value = draft[field.name];
          });
          if (status) status.textContent = 'Lokaal concept hersteld. Sla de dag op om het naar de server te sturen.';
        }
      }
    } catch (_) {
      try { localStorage.removeItem(key); } catch (_) {}
    }

    fields.forEach((field) => {
      field.addEventListener('input', () => {
        dirty = true;
        saveDraft();
      });
      field.addEventListener('change', () => {
        dirty = true;
        saveDraft();
      });
    });

    form.addEventListener('submit', () => {
      dirty = true;
      saveDraft();
    });
  });
})();
