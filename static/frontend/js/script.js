/* =============================================
   SB REVO - Main JavaScript
   ============================================= */

document.addEventListener('DOMContentLoaded', function () {

  /* =============================================
     HERO CAROUSEL
     ============================================= */
  const slides = document.querySelectorAll('.hero-slide');
  const dots = document.querySelectorAll('.carousel-dots .dot');
  let currentSlide = 0;
  let heroTimer = null;

  function loadSlideBackground(slide) {
    if (!slide || !slide.dataset.backgroundImage) return;
    slide.style.backgroundImage = `url("${slide.dataset.backgroundImage.replace(/"/g, '\\"')}")`;
    delete slide.dataset.backgroundImage;
  }

  function goToSlide(index) {
    if (!slides.length || !dots.length) return;
    slides[currentSlide].classList.remove('active');
    dots[currentSlide].classList.remove('active');
    currentSlide = (index + slides.length) % slides.length;
    loadSlideBackground(slides[currentSlide]);
    slides[currentSlide].classList.add('active');
    dots[currentSlide].classList.add('active');
  }

  function startHeroAuto() {
    heroTimer = setInterval(() => goToSlide(currentSlide + 1), 5000);
  }

  function resetHeroAuto() {
    clearInterval(heroTimer);
    startHeroAuto();
  }

  document.getElementById('heroNext')?.addEventListener('click', () => {
    goToSlide(currentSlide + 1);
    resetHeroAuto();
  });

  document.getElementById('heroPrev')?.addEventListener('click', () => {
    goToSlide(currentSlide - 1);
    resetHeroAuto();
  });

  dots.forEach((dot, i) => {
    dot.addEventListener('click', () => {
      goToSlide(i);
      resetHeroAuto();
    });
  });

  if (slides.length && dots.length) {
    startHeroAuto();
  }


  /* =============================================
     STICKY HEADER
     ============================================= */
  const header = document.getElementById('header');
  const navbar = document.getElementById('navbar');

  if (header) {
    const updateStickyHeaderHeight = () => {
      document.documentElement.style.setProperty('--sticky-header-height', `${header.offsetHeight}px`);
    };

    window.addEventListener('scroll', () => {
      if (window.scrollY > 80) {
        header.classList.add('scrolled');
      } else {
        header.classList.remove('scrolled');
      }
      window.requestAnimationFrame(updateStickyHeaderHeight);
    }, { passive: true });
    window.addEventListener('resize', updateStickyHeaderHeight);
    header.addEventListener('transitionend', updateStickyHeaderHeight);
    updateStickyHeaderHeight();
  }


  /* =============================================
     GLOBAL PAGE LINKS
     ============================================= */
  const frontendRoutes = window.sbRevoRoutes || {
    home: '/',
    products: '/products/',
    cart: '/cart/',
    checkout: '/checkout/',
    productDetails: '/product-details/',
    contact: '/contact/',
    cartAdd: '/cart/add/',
    cartUpdate: '/cart/update/',
    cartRemove: '/cart/remove/',
    cartClear: '/cart/clear/',
    cartSetDeliveryZone: '/cart/delivery-zone/'
  };

  document.querySelectorAll('.logo a').forEach(link => {
    if (!link.getAttribute('href') || link.getAttribute('href') === '#') {
      link.setAttribute('href', frontendRoutes.home);
    }
  });

  document.querySelectorAll('.cart-buttons .btn-primary').forEach(link => {
    link.setAttribute('href', frontendRoutes.checkout);
  });

  document.querySelectorAll('.view-detail').forEach(link => {
    if (!link.getAttribute('href') || link.getAttribute('href') === '#') {
      link.setAttribute('href', frontendRoutes.productDetails);
    }
  });


  /* =============================================
     CURRENCY NORMALIZATION
     ============================================= */
  const CURRENCY_SYMBOL = window.sbRevoCurrencySymbol || '৳';

  function formatCurrency(value) {
    const amount = typeof value === 'number'
      ? value
      : parseFloat(String(value).replace(/,/g, ''));
    const safeAmount = Number.isFinite(amount) ? amount : 0;

    return `${CURRENCY_SYMBOL}${safeAmount.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })}`;
  }

  document.querySelectorAll('.currency-selector select').forEach(select => {
    select.innerHTML = '<option>BDT ৳</option>';
  });

  function normalizeCurrencyText(root = document.body) {
    if (!root || typeof NodeFilter === 'undefined') return;

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const value = node.nodeValue || '';
        const parent = node.parentElement;
        if (!value.includes('$') || !parent || parent.closest('script, style')) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    const textNodes = [];
    while (walker.nextNode()) {
      textNodes.push(walker.currentNode);
    }

    textNodes.forEach(node => {
      node.nodeValue = node.nodeValue
        .replace(/USD\s*\$/g, 'BDT ৳')
        .replace(/AUD\s*\$/g, 'BDT ৳')
        .replace(/\$([0-9][0-9,]*(?:\.\d{1,2})?)/g, `${CURRENCY_SYMBOL}$1`);
    });
  }

  normalizeCurrencyText();

  function getCookie(name) {
    const cookieString = document.cookie || '';
    return cookieString
      .split(';')
      .map(cookie => cookie.trim())
      .find(cookie => cookie.startsWith(name + '='))
      ?.slice(name.length + 1) || '';
  }

  function getCsrfToken() {
    const cookieToken = decodeURIComponent(getCookie('csrftoken'));
    if (cookieToken) return cookieToken;

    const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    return metaToken && metaToken !== 'NOTPROVIDED' ? metaToken : '';
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify(payload || {}),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.message || 'Request failed.');
    }
    return data;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* =============================================
     BACK TO TOP
     ============================================= */
  const backToTop = document.getElementById('backToTop');

  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      backToTop.classList.add('visible');
    } else {
      backToTop.classList.remove('visible');
    }
  });

  backToTop?.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  /* =============================================
     PRODUCT CARD LINKS
     ============================================= */
  document.querySelectorAll('.product-card').forEach(card => {
    const detailsLink = card.querySelector('.product-info h4 a');
    if (!detailsLink) return;

    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');

    card.addEventListener('click', (e) => {
      if (e.target.closest('a, button, input, select, textarea, label')) return;
      window.location.href = detailsLink.href;
    });

    card.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      if (e.target.closest('a, button, input, select, textarea, label')) return;
      e.preventDefault();
      window.location.href = detailsLink.href;
    });
  });



  /* =============================================
     QUICK VIEW MODAL
     ============================================= */
  const quickViewModal = document.getElementById('quickViewModal');
  const quickViewClose = document.getElementById('quickViewClose');
  const qvImage = document.getElementById('qvImage');
  const qvName = document.getElementById('qvName');
  const qvCat = document.getElementById('qvCat');
  const qvPrice = document.getElementById('qvPrice');
  const qvReviews = document.getElementById('qvReviews');
  const qvDesc = document.getElementById('qvDesc');
  const qvDetailLink = document.getElementById('qvDetailLink');
  const qvAddToCart = quickViewModal?.querySelector('.add-to-cart.full');

  if (quickViewModal && qvImage && qvName && qvCat && qvPrice) {
    document.querySelectorAll('.product-actions button[title="Quick View"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const card = btn.closest('.product-card');
        if (!card) return;

        const img = card.querySelector('.product-image img');
        const name = card.querySelector('.product-info h4 a');
        const cat = card.querySelector('.product-cat');
        const price = card.querySelector('.product-price');
        const reviewText = card.querySelector('.product-rating span');
        const description = card.dataset.description;

        if (img) qvImage.src = img.src;
        if (name) qvName.textContent = name.textContent;
        if (cat) qvCat.textContent = cat.textContent;
        if (price) qvPrice.innerHTML = price.innerHTML;
        if (reviewText && qvReviews) qvReviews.textContent = reviewText.textContent;
        if (description && qvDesc) qvDesc.textContent = description;
        if (name && qvDetailLink) qvDetailLink.href = name.getAttribute('href') || frontendRoutes.productDetails;
        if (qvAddToCart) qvAddToCart.dataset.productId = card.dataset.productId || '';

        quickViewModal.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    });
  }

  function closeQuickView() {
    quickViewModal?.classList.remove('active');
    document.body.style.overflow = '';
  }

  quickViewClose?.addEventListener('click', closeQuickView);
  quickViewModal?.addEventListener('click', (e) => {
    if (e.target === quickViewModal) closeQuickView();
  });

  // Qty controls
  const qvQty = document.getElementById('qvQty');
  document.getElementById('qvQtyPlus')?.addEventListener('click', () => {
    if (qvQty) qvQty.value = parseInt(qvQty.value) + 1;
  });
  document.getElementById('qvQtyMinus')?.addEventListener('click', () => {
    if (qvQty && parseInt(qvQty.value) > 1) qvQty.value = parseInt(qvQty.value) - 1;
  });

  // Size buttons in quick view
  document.querySelectorAll('.size-btns button').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.size-btns').querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Color buttons in quick view
  document.querySelectorAll('.color-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.color-btns').querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });


  /* =============================================
     CART UI SHARED
     ============================================= */
  const cartBadge = document.querySelector('.cart-icon .badge');
  const cartPreviewItems = document.getElementById('cartPreviewItems');
  const cartPreviewSubtotal = document.getElementById('cartPreviewSubtotal');
  const cartPreviewTotalWrap = document.getElementById('cartPreviewTotalWrap');
  let cartCount = parseInt(cartBadge?.textContent || '0', 10);
  if (Number.isNaN(cartCount)) cartCount = 0;

  function updateCartCount(nextCount) {
    cartCount = typeof nextCount === 'number' ? Math.max(0, nextCount) : cartCount + 1;
    if (cartBadge) {
      cartBadge.textContent = cartCount;
      cartBadge.style.transform = 'scale(1.4)';
      setTimeout(() => cartBadge.style.transform = '', 300);
    }
  }

  function renderCartPreview(cart) {
    if (!cartPreviewItems) return;

    if (!cart || !cart.preview_items || !cart.preview_items.length) {
      cartPreviewItems.innerHTML = '<p class="cart-preview-empty" id="cartPreviewEmpty">Your cart is empty.</p>';
      if (cartPreviewSubtotal) cartPreviewSubtotal.textContent = formatCurrency(0);
      if (cartPreviewTotalWrap) cartPreviewTotalWrap.style.display = 'none';
      updateCartCount(0);
      return;
    }

    cartPreviewItems.innerHTML = cart.preview_items.map((item) => `
      <div class="cart-item">
        <img src="${item.image_url || '/static/frontend/images/product-placeholder.svg'}" alt="${escapeHtml(item.name)}" />
        <div>
          <p>${escapeHtml(item.name)}</p>
          <span>${formatCurrency(item.current_price)} x ${item.quantity}</span>
        </div>
        <button class="remove-item" data-product-id="${item.product_id}"><i class="fa fa-times"></i></button>
      </div>
    `).join('');

    if (cartPreviewSubtotal) cartPreviewSubtotal.textContent = formatCurrency(cart.subtotal);
    if (cartPreviewTotalWrap) cartPreviewTotalWrap.style.display = '';
    updateCartCount(cart.item_count);
  }

  function animateAddButton(button, addedText = 'Added!') {
    if (!button) return;
    const originalHtml = button.innerHTML;
    const originalBackground = button.style.background;
    button.innerHTML = addedText;
    button.style.background = 'var(--success)';
    setTimeout(() => {
      button.innerHTML = originalHtml;
      button.style.background = originalBackground;
    }, 1500);
  }

  function getProductIdFromButton(button) {
    return (
      button?.dataset.productId
      || button?.closest('.product-card')?.dataset.productId
      || button?.closest('.quickview-info')?.querySelector('.add-to-cart')?.dataset.productId
      || ''
    );
  }

  function getAddToCartQuantity(button) {
    if (button?.closest('.quickview-info')) {
      return parseInt(document.getElementById('qvQty')?.value || '1', 10) || 1;
    }
    return 1;
  }

  async function addProductToSessionCart(productId, quantity) {
    const data = await postJson(frontendRoutes.cartAdd, {
      product_id: productId,
      quantity: quantity,
    });
    renderCartPreview(data.cart);
    return data;
  }


  /* =============================================
     ADD TO CART
     ============================================= */
  document.querySelectorAll('.add-to-cart').forEach(btn => {
    btn.addEventListener('click', async function () {
      const card = this.closest('.product-card') || this.closest('.quickview-info');
      let name = 'Item';
      if (card) {
        const nameEl = card.querySelector('h4 a') || card.querySelector('h2');
        if (nameEl) name = nameEl.textContent.trim();
      }

      const productId = getProductIdFromButton(this);
      const quantity = getAddToCartQuantity(this);

      try {
        if (productId) {
          const data = await addProductToSessionCart(productId, quantity);
          animateAddButton(this);
          showToast(data.message || `"${name.substring(0, 30)}..." added to cart!`);
        } else {
          animateAddButton(this);
          showToast(`"${name.substring(0, 30)}..." added to cart!`);
          updateCartCount();
        }

        if (quickViewModal?.classList.contains('active')) {
          closeQuickView();
        }
      } catch (error) {
        showToast(error.message || 'Could not add item to cart.');
      }
    });
  });

  document.querySelectorAll('.buy-now').forEach(btn => {
    btn.addEventListener('click', async function () {
      const productId = getProductIdFromButton(this);

      try {
        if (productId) {
          await addProductToSessionCart(productId, 1);
        }
        window.location.href = frontendRoutes.cart;
      } catch (error) {
        showToast(error.message || 'Could not start checkout.');
      }
    });
  });


  /* =============================================
     TOAST NOTIFICATION
     ============================================= */
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');
  const toastIcon = document.getElementById('toastIcon');
  let toastTimer = null;

  function showToast(message, type = 'success') {
    if (toastMsg) toastMsg.textContent = message;
    if (toast) {
      toast.classList.remove('toast-success', 'toast-error');
      toast.classList.add(type === 'error' ? 'toast-error' : 'toast-success');
    }
    if (toastIcon) {
      toastIcon.className = type === 'error' ? 'fa fa-exclamation-circle' : 'fa fa-check-circle';
    }
    toast?.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast?.classList.remove('show'), 3000);
  }
  window.sbRevoShowToast = showToast;



  /* =============================================
     SEARCH BAR
     ============================================= */
  const searchForm = document.querySelector('.search-bar');
  const searchInput = document.querySelector('.search-bar input[name="q"]');
  const searchCategory = document.querySelector('.search-bar select[name="category"]');

  searchForm?.addEventListener('submit', (e) => {
    const query = searchInput?.value.trim() || '';
    const category = searchCategory?.value || '';

    if (!query && !category) {
      e.preventDefault();
      window.location.href = frontendRoutes.products;
    }
  });


  /* =============================================
     ALL CATEGORIES DROPDOWN TOGGLE
     ============================================= */
  const allCatBtn = document.querySelector('.all-cat-btn');
  const allCatDropdown = document.querySelector('.all-cat-dropdown');

  allCatBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    allCatDropdown.style.display = allCatDropdown.style.display === 'block' ? 'none' : 'block';
  });

  document.addEventListener('click', () => {
    if (allCatDropdown) allCatDropdown.style.display = 'none';
  });


  /* =============================================
     SMOOTH SCROLL FOR ANCHOR LINKS
     ============================================= */
  document.querySelectorAll('a[href="#"]').forEach(link => {
    link.addEventListener('click', (e) => e.preventDefault());
  });


  /* =============================================
     REMOVE CART ITEM
     ============================================= */
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('.remove-item');
    if (!button) return;

    const item = button.closest('.cart-item');
    const productId = button.dataset.productId;

    if (!productId) {
      item?.remove();
      if (cartCount > 0) updateCartCount(cartCount - 1);
      return;
    }

    try {
      const data = await postJson(frontendRoutes.cartRemove, { product_id: productId });
      if (item) {
        item.style.opacity = '0';
        item.style.maxHeight = '0';
        item.style.overflow = 'hidden';
        item.style.transition = 'all 0.3s ease';
      }
      setTimeout(() => renderCartPreview(data.cart), 250);
      showToast(data.message || 'Item removed from cart.');
    } catch (error) {
      showToast(error.message || 'Could not remove cart item.');
    }
  });


  /* =============================================
     PRODUCT DETAIL PAGE
     ============================================= */
  if (document.querySelector('.pd-section')) {
    const mainProductImg = document.getElementById('mainProductImg');
    const zoomedImg = document.getElementById('zoomedImg');
    const zoomOverlay = document.getElementById('imgZoomOverlay');
    const qtyInput = document.getElementById('pdQtyInput');
    const productImageFallback = '/static/frontend/images/product-placeholder.svg';
    let selectedRating = 0;

    // Keep the zoom overlay outside sticky/overflow containers so it always sits above the site chrome.
    if (zoomOverlay && zoomOverlay.parentElement !== document.body) {
      document.body.appendChild(zoomOverlay);
    }

    function attachProductFallback(img) {
      if (!img || img.dataset.fallbackBound === 'true') return;
      img.dataset.fallbackBound = 'true';
      img.addEventListener('error', () => {
        if (img.dataset.fallbackApplied === 'true') return;
        img.dataset.fallbackApplied = 'true';
        img.src = productImageFallback;
      });
    }

    [
      ...document.querySelectorAll('.pd-section img'),
      ...document.querySelectorAll('.related-section img'),
      ...document.querySelectorAll('.recently-viewed-section img'),
      ...document.querySelectorAll('#quickViewModal img'),
    ].forEach(attachProductFallback);

    document.querySelectorAll('.pd-thumb').forEach(thumb => {
      thumb.addEventListener('click', () => {
        const img = thumb.querySelector('img');
        if (!img) return;

        document.querySelectorAll('.pd-thumb').forEach(item => item.classList.remove('active'));
        thumb.classList.add('active');

        if (mainProductImg) mainProductImg.src = img.dataset.full || img.src;
        if (zoomedImg) zoomedImg.src = img.dataset.zoom || img.dataset.full || img.src;
      });
    });

    document.querySelector('.pd-main-img')?.addEventListener('click', (e) => {
      if (e.target.closest('.img-zoom-overlay')) return;
      if (!zoomOverlay) return;
      zoomOverlay.classList.add('open');
      document.body.style.overflow = 'hidden';
      document.body.classList.add('image-zoom-open');
    });

    function closeImageZoom() {
      if (!zoomOverlay) return;
      zoomOverlay.classList.remove('open');
      document.body.style.overflow = '';
      document.body.classList.remove('image-zoom-open');
    }

    document.getElementById('zoomClose')?.addEventListener('click', (e) => {
      e.stopPropagation();
      closeImageZoom();
    });
    zoomOverlay?.addEventListener('click', (e) => {
      if (e.target === zoomOverlay) closeImageZoom();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && zoomOverlay?.classList.contains('open')) {
        closeImageZoom();
      }
    });

    document.querySelectorAll('.color-swatch').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.color-swatch').forEach(item => item.classList.remove('active'));
        btn.classList.add('active');
        const label = document.getElementById('selectedColor');
        if (label) label.textContent = btn.dataset.color || '';
      });
    });

    document.querySelectorAll('.pd-size-btn:not(:disabled)').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.pd-size-btn').forEach(item => item.classList.remove('active'));
        btn.classList.add('active');
        const label = document.getElementById('selectedSize');
        if (label) label.textContent = btn.dataset.size || '';
      });
    });

    document.getElementById('pdQtyPlus')?.addEventListener('click', () => {
      if (!qtyInput) return;
      const max = parseInt(qtyInput.max || '10', 10);
      qtyInput.value = Math.min(max, (parseInt(qtyInput.value || '0', 10) || 0) + 1);
    });

    document.getElementById('pdQtyMinus')?.addEventListener('click', () => {
      if (!qtyInput) return;
      const min = parseInt(qtyInput.min || '1', 10);
      qtyInput.value = Math.max(min, (parseInt(qtyInput.value || '0', 10) || min) - 1);
    });

    qtyInput?.addEventListener('change', () => {
      const min = parseInt(qtyInput.min || '1', 10);
      const max = parseInt(qtyInput.max || '10', 10);
      let qty = parseInt(qtyInput.value || String(min), 10);
      if (Number.isNaN(qty)) qty = min;
      qtyInput.value = Math.min(max, Math.max(min, qty));
    });

    document.getElementById('pdAddToCart')?.addEventListener('click', async function () {
      const size = document.querySelector('.pd-size-btn.active');
      const color = document.querySelector('.color-swatch.active');
      const qty = parseInt(qtyInput?.value || '1', 10) || 1;
      const sizeText = size?.dataset.size || 'M';
      const colorText = color?.dataset.color || '';
      const productId = this.dataset.productId;

      try {
        if (productId) {
          const data = await addProductToSessionCart(productId, qty);
          this.innerHTML = '<i class="fa fa-check"></i> Added to Cart!';
          this.style.background = 'var(--success)';
          setTimeout(() => {
            this.innerHTML = '<i class="fa fa-shopping-cart"></i> Add to Cart';
            this.style.background = '';
          }, 2000);
          showToast(data.message || `Added ${qty}x (${colorText}, ${sizeText}) to cart!`);
        } else {
          updateCartCount(cartCount + qty);
          showToast(`Added ${qty}x (${colorText}, ${sizeText}) to cart!`);
        }
      } catch (error) {
        showToast(error.message || 'Could not add item to cart.');
      }
    });

    document.getElementById('pdBuyNow')?.addEventListener('click', async () => {
      const qty = parseInt(qtyInput?.value || '1', 10) || 1;
      const productId = document.getElementById('pdAddToCart')?.dataset.productId;

      try {
        if (productId) {
          await addProductToSessionCart(productId, qty);
        }
        window.location.href = frontendRoutes.cart;
      } catch (error) {
        showToast(error.message || 'Could not start checkout.');
      }
    });

    document.querySelectorAll('.pd-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.pd-tab-btn').forEach(item => item.classList.remove('active'));
        document.querySelectorAll('.pd-tab-content').forEach(item => item.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`pdtab-${btn.dataset.pdtab}`)?.classList.add('active');
      });
    });

    document.querySelector('.pd-write-review')?.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelector('[data-pdtab="reviews"]')?.click();
      document.querySelector('.write-review-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    const stars = document.querySelectorAll('#starPick i');
    const ratingInput = document.getElementById('reviewRatingInput');
    const ratingError = document.getElementById('reviewRatingError');
    selectedRating = parseInt(ratingInput?.value || '0', 10) || 0;

    function paintSelectedRating() {
      stars.forEach((item, itemIndex) => {
        item.className = itemIndex < selectedRating ? 'fa fa-star active' : 'far fa-star';
      });
      if (ratingInput) {
        ratingInput.value = selectedRating > 0 ? String(selectedRating) : '';
      }
    }

    stars.forEach((star, index) => {
      star.addEventListener('mouseenter', () => {
        stars.forEach((item, itemIndex) => {
          item.className = itemIndex <= index ? 'fa fa-star active' : 'far fa-star';
        });
      });

      star.addEventListener('mouseleave', () => {
        stars.forEach((item, itemIndex) => {
          item.className = itemIndex < selectedRating ? 'fa fa-star active' : 'far fa-star';
        });
      });

      star.addEventListener('click', () => {
        selectedRating = index + 1;
        if (ratingError) {
          ratingError.style.display = 'none';
        }
        paintSelectedRating();
      });
    });

    document.getElementById('reviewForm')?.addEventListener('submit', (e) => {
      if (selectedRating === 0) {
        e.preventDefault();
        if (ratingError) {
          ratingError.style.display = '';
        }
        showToast('Please select a star rating.');
        return;
      }
      if (ratingInput) {
        ratingInput.value = String(selectedRating);
      }
    });

    paintSelectedRating();
  }


  /* =============================================
     CART PAGE
     ============================================= */
  if (document.querySelector('.cart-section')) {
    const cartSection = document.querySelector('.cart-section');
    const coupons = { REVO20: 20, SAVE10: 10, WELCOME15: 15 };
    let appliedCoupon = null;
    const cartBody = document.getElementById('cartBody');
    const tableWrap = document.querySelector('.cart-table-wrap');
    const emptyState = document.getElementById('cartEmpty');
    const tableFooter = document.querySelector('.cart-table-footer');
    const couponSection = document.querySelector('.coupon-section');
    const clearCartBtn = document.getElementById('clearCartBtn');
    const checkoutBtn = document.getElementById('checkoutBtn');

    const getCartRows = () => Array.from(cartBody?.querySelectorAll('.cart-row') || []);

    function getRowQuantity(row) {
      const input = row?.querySelector('.cart-qty-input');
      const min = parseInt(input?.min || '1', 10);
      const max = parseInt(input?.max || '10', 10);
      let qty = parseInt(input?.value || String(min), 10);

      if (Number.isNaN(qty)) qty = min;
      qty = Math.min(max, Math.max(min, qty));
      if (input) input.value = qty;
      return qty;
    }

    function getItemCount() {
      return getCartRows().reduce((total, row) => total + getRowQuantity(row), 0);
    }

    function calcSubtotal() {
      return getCartRows().reduce((total, row) => {
        const price = parseFloat(row.dataset.price || '0');
        return total + (price * getRowQuantity(row));
      }, 0);
    }

    function getShipping() {
      const selected = document.querySelector('input[name="deliveryZone"]:checked');
      return selected ? parseInt(selected.value, 10) : 60;
    }

    function getSelectedDeliveryZone() {
      const selected = document.querySelector('input[name="deliveryZone"]:checked');
      return selected?.dataset.zone || 'inside_dhaka';
    }

    function updateDeliveryZoneSelection() {
      document.querySelectorAll('.ship-option').forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        option.classList.toggle('selected', Boolean(radio?.checked));
      });
    }

    function updateSummary() {
      const subtotal = calcSubtotal();
      const discountRate = appliedCoupon ? (coupons[appliedCoupon] || 0) / 100 : 0;
      const discount = subtotal * discountRate;
      const discountedSubtotal = subtotal - discount;
      const itemCount = getItemCount();
      const lineCount = getCartRows().length;
      const shipping = lineCount > 0 ? getShipping() : 0;

      const summarySubtotal = document.getElementById('summarySubtotal');
      const summaryShipping = document.getElementById('summaryShipping');
      const summaryTotal = document.getElementById('summaryTotal');
      const summaryItemCount = document.getElementById('summaryItemCount');
      const cartItemCount = document.getElementById('cartItemCount');
      const discountRow = document.getElementById('discountRow');
      const discountVal = document.getElementById('discountVal');

      if (summarySubtotal) summarySubtotal.textContent = formatCurrency(subtotal);
      if (summaryShipping) summaryShipping.textContent = formatCurrency(shipping);
      if (summaryTotal) summaryTotal.textContent = formatCurrency(discountedSubtotal + shipping);
      if (summaryItemCount) summaryItemCount.textContent = itemCount;
      if (cartItemCount) cartItemCount.textContent = `(${itemCount} item${itemCount !== 1 ? 's' : ''})`;
      updateCartCount(itemCount);

      if (discountRow) discountRow.style.display = discount > 0 ? 'flex' : 'none';
      if (discountVal) discountVal.textContent = formatCurrency(discount).replace(CURRENCY_SYMBOL, `-${CURRENCY_SYMBOL}`);

      const hasItems = lineCount > 0;
      if (tableWrap) tableWrap.style.display = hasItems ? 'block' : 'none';
      if (emptyState) emptyState.style.display = hasItems ? 'none' : 'block';
      if (tableFooter) tableFooter.style.display = hasItems ? 'flex' : 'none';
      if (couponSection) couponSection.style.display = hasItems ? 'block' : 'none';
      if (clearCartBtn) clearCartBtn.style.display = hasItems ? '' : 'none';
      if (checkoutBtn) checkoutBtn.style.pointerEvents = hasItems ? '' : 'none';
    }

    function renderCartRows(items) {
      if (!cartBody) return;
      cartBody.innerHTML = items.map((item) => `
        <tr class="cart-row" data-product-id="${item.product_id}" data-price="${item.current_price}">
          <td class="col-product">
            <div class="cart-product-cell">
              <a href="${item.detail_url}" class="cart-product-img">
                <img src="${item.image_url || '/static/frontend/images/product-placeholder.svg'}" alt="${escapeHtml(item.name)}" />
              </a>
              <div class="cart-product-details">
                <a href="${item.detail_url}" class="cart-product-name">${escapeHtml(item.name)}</a>
                <div class="cart-product-meta">
                  <span>Category: ${escapeHtml(item.category_name)}</span>
                  <span>Brand: ${escapeHtml(item.brand_name || 'Unbranded')}</span>
                  <span>SKU: ${escapeHtml(item.sku)}</span>
                </div>
              </div>
            </div>
          </td>
          <td class="col-price" data-label="Price">
            <span class="cart-price">${formatCurrency(item.current_price)}</span>
            ${item.is_on_sale ? `<span class="cart-price-old">${formatCurrency(item.regular_price)}</span>` : ''}
          </td>
          <td class="col-qty" data-label="Quantity">
            <div class="cart-qty-control">
              <button class="qty-dec" type="button"><i class="fa fa-minus"></i></button>
              <input type="number" class="cart-qty-input" value="${item.quantity}" min="1" max="10" />
              <button class="qty-inc" type="button"><i class="fa fa-plus"></i></button>
            </div>
          </td>
          <td class="col-subtotal" data-label="Subtotal">
            <span class="cart-subtotal">${formatCurrency(item.subtotal)}</span>
          </td>
          <td class="col-remove">
            <button class="cart-remove-btn" type="button" title="Remove item"><i class="fa fa-times"></i></button>
          </td>
        </tr>
      `).join('');
    }

    function syncCartPage(cart) {
      renderCartRows(cart.items || []);
      renderCartPreview(cart);
      updateSummary();
    }

    async function persistRowQuantity(row, quantity, successMessage = 'Cart updated.') {
      const productId = row?.dataset.productId;
      if (!productId) return;

      try {
        const data = await postJson(frontendRoutes.cartUpdate, {
          product_id: productId,
          quantity: quantity,
        });
        syncCartPage(data.cart);
        showToast(successMessage);
      } catch (error) {
        showToast(error.message || 'Could not update cart.');
      }
    }

    async function removeCartRow(row) {
      if (!row) return;
      try {
        const data = await postJson(frontendRoutes.cartRemove, {
          product_id: row.dataset.productId,
        });
        row.style.opacity = '0';
        row.style.transform = 'translateX(30px)';
        setTimeout(() => {
          syncCartPage(data.cart);
          showToast(data.message || 'Item removed from cart.');
        }, 220);
      } catch (error) {
        showToast(error.message || 'Could not remove cart item.');
      }
    }

    cartBody?.addEventListener('click', async (event) => {
      const increaseButton = event.target.closest('.qty-inc');
      if (increaseButton) {
        const row = increaseButton.closest('.cart-row');
        const input = row?.querySelector('.cart-qty-input');
        if (!row || !input) return;
        const max = parseInt(input.max || '10', 10);
        const nextQuantity = Math.min(max, (parseInt(input.value || '0', 10) || 0) + 1);
        input.value = nextQuantity;
        await persistRowQuantity(row, nextQuantity);
        return;
      }

      const decreaseButton = event.target.closest('.qty-dec');
      if (decreaseButton) {
        const row = decreaseButton.closest('.cart-row');
        const input = row?.querySelector('.cart-qty-input');
        if (!row || !input) return;
        const min = parseInt(input.min || '1', 10);
        const nextQuantity = Math.max(min, (parseInt(input.value || '0', 10) || min) - 1);
        input.value = nextQuantity;
        await persistRowQuantity(row, nextQuantity);
        return;
      }

      const removeButton = event.target.closest('.cart-remove-btn');
      if (removeButton) {
        await removeCartRow(removeButton.closest('.cart-row'));
      }
    });

    cartBody?.addEventListener('change', async (event) => {
      const input = event.target.closest('.cart-qty-input');
      if (!input) return;
      const row = input.closest('.cart-row');
      const quantity = getRowQuantity(row);
      await persistRowQuantity(row, quantity);
    });

    clearCartBtn?.addEventListener('click', async () => {
      if (!window.confirm('Remove all items from your cart?')) return;
      try {
        const data = await postJson(frontendRoutes.cartClear, {});
        syncCartPage(data.cart);
        showToast(data.message || 'Cart cleared.');
      } catch (error) {
        showToast(error.message || 'Could not clear cart.');
      }
    });

    document.getElementById('updateCartBtn')?.addEventListener('click', () => {
      updateSummary();
      showToast('Cart updated!');
    });

    document.getElementById('applyCoupon')?.addEventListener('click', () => {
      const input = document.getElementById('couponInput');
      const code = input?.value.trim().toUpperCase() || '';

      if (!code) {
        showToast('Please enter a coupon code.');
        return;
      }

      if (!(code in coupons)) {
        showToast('Invalid coupon code. Try REVO20, SAVE10, or WELCOME15.');
        return;
      }

      if (appliedCoupon === code) {
        showToast('Coupon already applied.');
        return;
      }

      appliedCoupon = code;
      const couponMsg = document.getElementById('couponMsg');
      const appliedCode = document.getElementById('appliedCode');
      const discountAmt = document.getElementById('discountAmt');
      const discountCode = document.getElementById('discountCode2');

      if (couponMsg) couponMsg.style.display = 'flex';
      if (appliedCode) appliedCode.textContent = code;
      if (discountAmt) discountAmt.textContent = `${coupons[code]}%`;
      if (discountCode) discountCode.textContent = code;

      updateSummary();
      showToast(`Coupon "${code}" applied - ${coupons[code]}% off!`);
    });

    document.getElementById('removeCoupon')?.addEventListener('click', () => {
      appliedCoupon = null;
      const couponMsg = document.getElementById('couponMsg');
      const input = document.getElementById('couponInput');
      if (couponMsg) couponMsg.style.display = 'none';
      if (input) input.value = '';
      updateSummary();
      showToast('Coupon removed.');
    });

    document.querySelectorAll('input[name="deliveryZone"]').forEach(radio => {
      radio.addEventListener('change', async () => {
        updateDeliveryZoneSelection();
        updateSummary();
        try {
          await postJson(frontendRoutes.cartSetDeliveryZone, {
            zone: getSelectedDeliveryZone(),
          });
        } catch (error) {
          showToast(error.message || 'Could not save delivery area.');
        }
      });
    });

    updateDeliveryZoneSelection();
    updateSummary();
  }


  /* =============================================
     PRODUCT CARD HOVER EFFECT
     ============================================= */
  document.querySelectorAll('.product-card').forEach(card => {
    card.addEventListener('mouseenter', function () {
      this.style.zIndex = '10';
    });
    card.addEventListener('mouseleave', function () {
      this.style.zIndex = '';
    });
  });


  /* =============================================
     ESCAPE KEY CLOSES MODALS
     ============================================= */
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeQuickView();
    }
  });


  /* =============================================
     LAZY IMAGE FADE-IN
     ============================================= */
  const images = document.querySelectorAll('img');
  const imgObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        imgObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  images.forEach(img => {
    img.style.opacity = '0';
    img.style.transition = 'opacity 0.5s ease';
    img.addEventListener('load', () => { img.style.opacity = '1'; });
    if (img.complete) img.style.opacity = '1';
    imgObserver.observe(img);
  });


  /* =============================================
     SECTION SCROLL ANIMATIONS
     ============================================= */
  const animEls = document.querySelectorAll('.product-card, .category-card, .feature-item');
  const scrollObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
        }, i * 60);
        scrollObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  animEls.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease, box-shadow 0.3s ease';
    scrollObserver.observe(el);
  });

});

