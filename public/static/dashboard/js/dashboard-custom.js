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

  const deleteModalElement = document.getElementById('dashboardDeleteConfirmModal');
  if (!deleteModalElement || typeof bootstrap === 'undefined') {
    return;
  }

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

  confirmButton?.addEventListener('click', () => {
    if (activeForm) {
      activeForm.submit();
    }
  });
});
