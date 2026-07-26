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
  if (deleteModalElement && typeof bootstrap !== 'undefined') {

  const deleteModal = new bootstrap.Modal(deleteModalElement);
  const confirmButton = deleteModalElement.querySelector('.js-confirm-delete');
  const itemNameElement = deleteModalElement.querySelector('.js-delete-item-name');
  let activeForm = null;

  document.querySelectorAll('.js-delete-trigger').forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const formId = trigger.dataset.deleteFormId;
      activeForm = formId ? document.getElementById(formId) : null;
      if (itemNameElement) {
        itemNameElement.textContent = trigger.dataset.deleteItemName || 'this item';
      }
      deleteModal.show();
    });
  });

  document.querySelectorAll('.js-product-bulk-form').forEach((formElement) => {
    formElement.addEventListener('submit', (event) => {
      const action = formElement.querySelector('[name="action"]')?.value;
      if (action !== 'delete') {
        return;
      }
      event.preventDefault();
      activeForm = formElement;
      if (itemNameElement) {
        itemNameElement.textContent = 'the selected products';
      }
      deleteModal.show();
    });
  });

    confirmButton?.addEventListener('click', () => {
      if (activeForm) {
        activeForm.submit();
      }
    });
  }

  const trackingModalElement = document.getElementById('dashboardOrderTrackingModal');
  if (!trackingModalElement || typeof bootstrap === 'undefined') {
    return;
  }

  const trackingModal = new bootstrap.Modal(trackingModalElement);
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
