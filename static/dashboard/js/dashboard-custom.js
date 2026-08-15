document.addEventListener('DOMContentLoaded', () => {
  const toastElements = document.querySelectorAll('.js-dashboard-toast');
  toastElements.forEach((toastElement) => {
    const duration = Number(toastElement.dataset.duration || 3200);
    const closeButton = toastElement.querySelector('.js-dashboard-toast-close');

    requestAnimationFrame(() => {
      toastElement.classList.add('is-visible');
    });

    const dismissToast = () => {
      toastElement.classList.remove('is-visible');
      toastElement.classList.add('is-leaving');
      toastElement.addEventListener(
        'animationend',
        () => {
          toastElement.remove();
        },
        { once: true },
      );
    };

    window.setTimeout(dismissToast, duration);
    closeButton?.addEventListener('click', dismissToast);
  });

  document.querySelectorAll('.js-auto-submit').forEach((inputElement) => {
    inputElement.addEventListener('change', () => {
      const formElement = inputElement.form;
      if (formElement) {
        formElement.submit();
      }
    });
  });

  document.querySelectorAll('.js-user-role-selector').forEach((selectElement) => {
    selectElement.addEventListener('change', () => {
      const redirectUrl = selectElement.dataset.redirectUrl;
      if (!redirectUrl) {
        return;
      }

      const nextUrl = new URL(redirectUrl, window.location.origin);
      nextUrl.searchParams.set('role', selectElement.value);
      window.location.assign(nextUrl.toString());
    });
  });

  const selectAllProducts = document.querySelector('.js-product-select-all');
  const productSelections = document.querySelectorAll('.js-product-select');
  selectAllProducts?.addEventListener('change', () => {
    productSelections.forEach((selection) => {
      selection.checked = selectAllProducts.checked;
    });
  });

  const deleteModalElement = document.getElementById('dashboardDeleteConfirmModal');
  const BootstrapModal = window.bootstrap?.Modal;
  if (deleteModalElement && BootstrapModal && !deleteModalElement.dataset.deleteConfirmInitialized) {
    deleteModalElement.dataset.deleteConfirmInitialized = 'true';
    const deleteModal = BootstrapModal.getOrCreateInstance(deleteModalElement);
    const confirmButton = deleteModalElement.querySelector('.js-confirm-delete');
    const itemNameElement = deleteModalElement.querySelector('.js-delete-item-name');
    let activeForm = null;
    let generatedDeleteForm = null;

  const showDeleteConfirmation = (trigger, formElement) => {
    activeForm = formElement;
    if (itemNameElement) {
      itemNameElement.textContent = trigger.dataset.deleteItemName
        || trigger.getAttribute('aria-label')?.replace(/^Delete\s*/i, '')
        || 'this item';
    }
    deleteModal.show();
  };

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const trigger = event.target.closest('.js-delete-trigger');
    if (!trigger) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    const formId = trigger.dataset.deleteFormId;
    const formElement = formId ? document.getElementById(formId) : null;
    if (!formElement) {
      console.error('Delete form not found:', formId);
      return;
    }

    showDeleteConfirmation(trigger, formElement);
  });

  document.querySelectorAll('a[href*="/delete/"]').forEach((trigger) => {
    if (trigger.dataset.deleteConfirmBound) {
      return;
    }
    trigger.dataset.deleteConfirmBound = 'true';
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const formElement = document.createElement('form');
      formElement.method = 'post';
      formElement.action = trigger.href;
      formElement.className = 'd-none';
      const csrfInput = document.createElement('input');
      csrfInput.type = 'hidden';
      csrfInput.name = 'csrfmiddlewaretoken';
      csrfInput.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
      formElement.append(csrfInput);
      document.body.append(formElement);
      generatedDeleteForm = formElement;
      showDeleteConfirmation(trigger, formElement);
    });
  });

  document.querySelectorAll('.js-product-bulk-form').forEach((formElement) => {
    if (formElement.dataset.deleteConfirmBound) {
      return;
    }
    formElement.dataset.deleteConfirmBound = 'true';
    formElement.addEventListener('submit', (event) => {
      const action = formElement.querySelector('[name="action"]')?.value;
      if (action !== 'delete') {
        return;
      }
      if (formElement.dataset.deleteConfirmed === 'true') {
        delete formElement.dataset.deleteConfirmed;
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      activeForm = formElement;
      if (itemNameElement) {
        itemNameElement.textContent = 'the selected products';
      }
      deleteModal.show();
    });
  });

    confirmButton?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!activeForm) {
        return;
      }

      const formToSubmit = activeForm;
      activeForm = null;
      const generatedFormToSubmit = generatedDeleteForm;
      generatedDeleteForm = null;
      confirmButton.disabled = true;
      deleteModal.hide();
      if (formToSubmit.matches('.js-product-bulk-form')) {
        formToSubmit.dataset.deleteConfirmed = 'true';
      }
      if (typeof formToSubmit.requestSubmit === 'function') {
        formToSubmit.requestSubmit();
      } else {
        formToSubmit.submit();
      }
      generatedFormToSubmit?.remove();
    });
    deleteModalElement.addEventListener('hidden.bs.modal', () => {
      activeForm = null;
      generatedDeleteForm?.remove();
      generatedDeleteForm = null;
      if (confirmButton) {
        confirmButton.disabled = false;
      }
    });
  }

  const trackingModalElement = document.getElementById('dashboardOrderTrackingModal');
  if (!trackingModalElement || !BootstrapModal) {
    return;
  }

  const trackingModal = BootstrapModal.getOrCreateInstance(trackingModalElement);
  const trackingTitle = trackingModalElement.querySelector('.modal-title');
  const trackingBody = trackingModalElement.querySelector('.js-order-tracking-body');
  const trackingDetailLink = trackingModalElement.querySelector('.js-order-tracking-detail');

  const setTrackingLoading = () => {
    trackingTitle.textContent = 'Loading order...';
    trackingDetailLink.classList.add('d-none');
    trackingDetailLink.removeAttribute('href');
    trackingBody.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'd-flex justify-content-center align-items-center py-5 text-muted gap-2';
    loading.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Loading tracking history...';
    trackingBody.append(loading);
  };

  const renderTracking = (tracking) => {
    trackingTitle.textContent = `Order ${tracking.order_number}`;
    trackingBody.innerHTML = tracking.html;
    trackingDetailLink.href = tracking.detail_url;
    trackingDetailLink.classList.remove('d-none');
  };

  const showTrackingError = () => {
    trackingTitle.textContent = 'Tracking unavailable';
    trackingBody.replaceChildren();
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger mb-0';
    alert.textContent = 'Tracking information could not be loaded. Please try again.';
    trackingBody.append(alert);
  };

  document.querySelectorAll('.js-order-tracking-trigger').forEach((trigger) => {
    trigger.addEventListener('click', async () => {
      const trackingUrl = trigger.dataset.orderTrackingUrl;
      if (!trackingUrl) {
        return;
      }
      setTrackingLoading();
      trackingModal.show();
      try {
        const response = await fetch(trackingUrl, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!response.ok) {
          throw new Error(`Tracking request failed: ${response.status}`);
        }
        renderTracking(await response.json());
      } catch (error) {
        showTrackingError();
      }
    });
  });
});
