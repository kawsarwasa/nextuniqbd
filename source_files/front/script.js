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

  function goToSlide(index) {
    if (!slides.length || !dots.length) return;
    slides[currentSlide].classList.remove('active');
    dots[currentSlide].classList.remove('active');
    currentSlide = (index + slides.length) % slides.length;
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
    window.addEventListener('scroll', () => {
      if (window.scrollY > 80) {
        header.classList.add('scrolled');
      } else {
        header.classList.remove('scrolled');
      }
    });
  }


  /* =============================================
     GLOBAL PAGE LINKS
     ============================================= */
  const frontendRoutes = {
    home: '/',
    about: '/about/',
    products: '/products/',
    blog: '/blog/',
    article: '/blog-details/',
    cart: '/cart/',
    checkout: '/checkout/',
    productDetails: '/product-details/',
    contact: '/contact/'
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
    link.setAttribute('href', frontendRoutes.productDetails);
  });


  /* =============================================
     CURRENCY NORMALIZATION
     ============================================= */
  const CURRENCY_SYMBOL = '৳';

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


  /* =============================================
     PRODUCT TABS
     ============================================= */
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + target)?.classList.add('active');
    });
  });


  /* =============================================
     CATEGORY TABS
     ============================================= */
  const catTabBtns = document.querySelectorAll('.cat-tab-btn');
  catTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      catTabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  const subTabs = document.querySelectorAll('.sub-tab');
  subTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      subTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
    });
  });


  /* =============================================
     COUNTDOWN TIMER
     ============================================= */
  const saleEnd = new Date();
  saleEnd.setDate(saleEnd.getDate() + 2);
  saleEnd.setHours(23, 59, 59, 0);

  function updateCountdown() {
    const cdDays = document.getElementById('cd-days');
    if (!cdDays) return;

    const now = new Date();
    const diff = saleEnd - now;
    if (diff <= 0) return;

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const secs = Math.floor((diff % (1000 * 60)) / 1000);

    const pad = n => String(n).padStart(2, '0');
    cdDays.textContent = pad(days);
    document.getElementById('cd-hours').textContent = pad(hours);
    document.getElementById('cd-mins').textContent = pad(mins);
    document.getElementById('cd-secs').textContent = pad(secs);
  }

  updateCountdown();
  setInterval(updateCountdown, 1000);


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
     COOKIE BANNER
     ============================================= */
  const cookieBanner = document.getElementById('cookieBanner');
  const cookieAccepted = localStorage.getItem('cookieAccepted');

  if (!cookieAccepted) {
    setTimeout(() => cookieBanner?.classList.remove('hidden'), 1000);
  } else {
    cookieBanner?.classList.add('hidden');
  }

  document.getElementById('acceptCookies')?.addEventListener('click', () => {
    localStorage.setItem('cookieAccepted', 'true');
    cookieBanner.classList.add('hidden');
  });

  document.getElementById('declineCookies')?.addEventListener('click', () => {
    cookieBanner.classList.add('hidden');
  });


  /* =============================================
     NEWSLETTER MODAL
     ============================================= */
  const newsletterModal = document.getElementById('newsletterModal');
  const modalShown = sessionStorage.getItem('modalShown');

  if (newsletterModal && !modalShown) {
    setTimeout(() => {
      newsletterModal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }, 4000);
  }

  function closeNewsletterModal() {
    if (!newsletterModal) return;
    newsletterModal.classList.remove('active');
    document.body.style.overflow = '';
    sessionStorage.setItem('modalShown', 'true');
  }

  document.getElementById('modalClose')?.addEventListener('click', closeNewsletterModal);
  document.getElementById('modalSkip')?.addEventListener('click', closeNewsletterModal);

  newsletterModal?.addEventListener('click', (e) => {
    if (e.target === newsletterModal) closeNewsletterModal();
  });

  document.getElementById('modalForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    closeNewsletterModal();
    showToast('Subscribed! Check your email for the discount code.');
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
     BLOG CARD LINKS
     ============================================= */
  document.querySelectorAll('.blog-card').forEach(card => {
    const cardLinks = Array.from(card.querySelectorAll('a'));
    cardLinks.forEach(link => {
      const href = link.getAttribute('href');
      if (!href || href === '#') {
        link.setAttribute('href', frontendRoutes.article);
      }
    });

    const detailsLink = card.querySelector('.blog-card-title a, .blog-content h3 a, .blog-read-more, .read-more, .blog-card-img a, .blog-image a');
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

  document.querySelectorAll('.section-header .view-all').forEach(link => {
    if (!link.getAttribute('href') || link.getAttribute('href') === '#') {
      link.setAttribute('href', frontendRoutes.blog);
    }
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

  if (quickViewModal && qvImage && qvName && qvCat && qvPrice) {
    document.querySelectorAll('.product-actions button[title="Quick View"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const card = btn.closest('.product-card');
        if (!card) return;

        const img = card.querySelector('.product-image img');
        const name = card.querySelector('.product-info h4 a');
        const cat = card.querySelector('.product-cat');
        const price = card.querySelector('.product-price');

        if (img) qvImage.src = img.src;
        if (name) qvName.textContent = name.textContent;
        if (cat) qvCat.textContent = cat.textContent;
        if (price) qvPrice.innerHTML = price.innerHTML;

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
     ADD TO CART
     ============================================= */
  document.querySelectorAll('.add-to-cart').forEach(btn => {
    btn.addEventListener('click', function () {
      const card = this.closest('.product-card') || this.closest('.quickview-info');
      let name = 'Item';
      if (card) {
        const nameEl = card.querySelector('h4 a') || card.querySelector('h2');
        if (nameEl) name = nameEl.textContent.trim();
      }

      // Animate button
      this.textContent = 'Added!';
      this.style.background = 'var(--success)';
      const originalBtn = this;
      setTimeout(() => {
        originalBtn.textContent = 'Add to Cart';
        originalBtn.style.background = '';
      }, 1500);

      showToast(`"${name.substring(0, 30)}..." added to cart!`);
      updateCartCount();

      if (quickViewModal?.classList.contains('active')) {
        closeQuickView();
      }
    });
  });

  /* =============================================
     CART COUNT UPDATE
     ============================================= */
  const cartBadge = document.querySelector('.cart-icon .badge');
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


  /* =============================================
     TOAST NOTIFICATION
     ============================================= */
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');
  let toastTimer = null;

  function showToast(message) {
    if (toastMsg) toastMsg.textContent = message;
    toast?.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast?.classList.remove('show'), 3000);
  }


  /* =============================================
     NEWSLETTER FORM (footer)
     ============================================= */
  document.getElementById('newsletterForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    showToast('Thanks for subscribing! Welcome to SB Revo.');
    e.target.reset();
  });


  /* =============================================
     SEARCH BAR
     ============================================= */
  const searchInput = document.querySelector('.search-bar input');
  const searchBtn = document.querySelector('.search-btn');

  searchBtn?.addEventListener('click', () => {
    const query = searchInput?.value.trim();
    if (query) {
      showToast(`Searching for "${query}"...`);
    }
  });

  searchInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const query = searchInput.value.trim();
      if (query) showToast(`Searching for "${query}"...`);
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
  document.querySelectorAll('.remove-item').forEach(btn => {
    btn.addEventListener('click', function () {
      const item = this.closest('.cart-item');
      item.style.opacity = '0';
      item.style.maxHeight = '0';
      item.style.overflow = 'hidden';
      item.style.transition = 'all 0.3s ease';
      setTimeout(() => item.remove(), 300);
      if (cartCount > 0) {
        updateCartCount(cartCount - 1);
      }
    });
  });


  /* =============================================
     PRODUCT DETAIL PAGE
     ============================================= */
  if (document.querySelector('.pd-section')) {
    const mainProductImg = document.getElementById('mainProductImg');
    const zoomedImg = document.getElementById('zoomedImg');
    const zoomOverlay = document.getElementById('imgZoomOverlay');
    const qtyInput = document.getElementById('pdQtyInput');
    let selectedRating = 0;

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
    });

    function closeImageZoom() {
      if (!zoomOverlay) return;
      zoomOverlay.classList.remove('open');
      document.body.style.overflow = '';
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

    document.getElementById('pdAddToCart')?.addEventListener('click', function () {
      const size = document.querySelector('.pd-size-btn.active');
      const color = document.querySelector('.color-swatch.active');
      const qty = parseInt(qtyInput?.value || '1', 10) || 1;
      const sizeText = size?.dataset.size || 'M';
      const colorText = color?.dataset.color || '';

      this.innerHTML = '<i class="fa fa-check"></i> Added to Cart!';
      this.style.background = 'var(--success)';
      setTimeout(() => {
        this.innerHTML = '<i class="fa fa-shopping-cart"></i> Add to Cart';
        this.style.background = '';
      }, 2000);

      updateCartCount(cartCount + qty);
      showToast(`Added ${qty}x (${colorText}, ${sizeText}) to cart!`);
    });

    document.getElementById('pdBuyNow')?.addEventListener('click', () => {
      window.location.href = frontendRoutes.cart;
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
        stars.forEach((item, itemIndex) => {
          item.className = itemIndex < selectedRating ? 'fa fa-star active' : 'far fa-star';
        });
      });
    });

    document.getElementById('reviewForm')?.addEventListener('submit', (e) => {
      e.preventDefault();
      if (selectedRating === 0) {
        showToast('Please select a star rating.');
        return;
      }

      e.target.reset();
      selectedRating = 0;
      stars.forEach(star => { star.className = 'far fa-star'; });
      showToast('Review submitted! Thank you.');
    });
  }


  /* =============================================
     CART PAGE
     ============================================= */
  if (document.querySelector('.cart-section')) {
    const coupons = { REVO20: 20, SAVE10: 10, WELCOME15: 15 };
    let appliedCoupon = null;

    const getCartRows = () => Array.from(document.querySelectorAll('#cartBody .cart-row'));

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

    function calcSubtotal() {
      return getCartRows().reduce((total, row) => {
        const price = parseFloat(row.dataset.price || '0');
        return total + (price * getRowQuantity(row));
      }, 0);
    }

    function updateSubtotals() {
      getCartRows().forEach(row => {
        const price = parseFloat(row.dataset.price || '0');
        const subtotal = price * getRowQuantity(row);
        const subtotalEl = row.querySelector('.cart-subtotal');
        if (subtotalEl) subtotalEl.textContent = formatCurrency(subtotal);
      });
    }

    function getShipping() {
      const selected = document.querySelector('input[name="deliveryZone"]:checked');
      return selected ? parseInt(selected.value, 10) : 60;
    }

    function updateDeliveryZoneSelection() {
      document.querySelectorAll('.ship-option').forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        option.classList.toggle('selected', Boolean(radio?.checked));
      });
    }

    function updateSummary() {
      const rows = getCartRows();
      const subtotal = calcSubtotal();
      const discountRate = appliedCoupon ? (coupons[appliedCoupon] || 0) / 100 : 0;
      const discount = subtotal * discountRate;
      const discountedSubtotal = subtotal - discount;
      const shipping = getShipping();
      const itemCount = rows.length;

      const summarySubtotal = document.getElementById('summarySubtotal');
      const summaryShipping = document.getElementById('summaryShipping');
      const summaryTotal = document.getElementById('summaryTotal');
      const summaryItemCount = document.getElementById('summaryItemCount');
      const cartItemCount = document.getElementById('cartItemCount');
      const discountRow = document.getElementById('discountRow');
      const discountVal = document.getElementById('discountVal');
      const tableWrap = document.querySelector('.cart-table-wrap');
      const emptyState = document.getElementById('cartEmpty');
      const tableFooter = document.querySelector('.cart-table-footer');
      const couponSection = document.querySelector('.coupon-section');

      if (summarySubtotal) summarySubtotal.textContent = formatCurrency(subtotal);
      if (summaryShipping) summaryShipping.textContent = formatCurrency(shipping);
      if (summaryTotal) summaryTotal.textContent = formatCurrency(discountedSubtotal + shipping);
      if (summaryItemCount) summaryItemCount.textContent = itemCount;
      if (cartItemCount) cartItemCount.textContent = `(${itemCount} item${itemCount !== 1 ? 's' : ''})`;
      updateCartCount(itemCount);

      if (discountRow) discountRow.style.display = discount > 0 ? 'flex' : 'none';
      if (discountVal) discountVal.textContent = formatCurrency(discount).replace(CURRENCY_SYMBOL, `-${CURRENCY_SYMBOL}`);

      const hasItems = itemCount > 0;
      if (tableWrap) tableWrap.style.display = hasItems ? 'block' : 'none';
      if (emptyState) emptyState.style.display = hasItems ? 'none' : 'block';
      if (tableFooter) tableFooter.style.display = hasItems ? 'flex' : 'none';
      if (couponSection) couponSection.style.display = hasItems ? 'block' : 'none';
    }

    function removeCartRow(row) {
      if (!row) return;
      row.style.opacity = '0';
      row.style.transform = 'translateX(30px)';
      setTimeout(() => {
        row.remove();
        updateSummary();
        showToast('Item removed from cart.');
      }, 320);
    }

    document.querySelectorAll('.qty-inc').forEach(btn => {
      btn.addEventListener('click', () => {
        const input = btn.closest('.cart-qty-control')?.querySelector('.cart-qty-input');
        if (!input) return;
        const max = parseInt(input.max || '10', 10);
        input.value = Math.min(max, (parseInt(input.value || '0', 10) || 0) + 1);
        updateSubtotals();
        updateSummary();
      });
    });

    document.querySelectorAll('.qty-dec').forEach(btn => {
      btn.addEventListener('click', () => {
        const input = btn.closest('.cart-qty-control')?.querySelector('.cart-qty-input');
        if (!input) return;
        const min = parseInt(input.min || '1', 10);
        input.value = Math.max(min, (parseInt(input.value || '0', 10) || min) - 1);
        updateSubtotals();
        updateSummary();
      });
    });

    document.querySelectorAll('.cart-qty-input').forEach(input => {
      input.addEventListener('change', () => {
        getRowQuantity(input.closest('.cart-row'));
        updateSubtotals();
        updateSummary();
      });
    });

    document.querySelectorAll('.cart-remove-btn').forEach(btn => {
      btn.addEventListener('click', () => removeCartRow(btn.closest('.cart-row')));
    });

    document.getElementById('clearCartBtn')?.addEventListener('click', () => {
      if (!window.confirm('Remove all items from your cart?')) return;
      getCartRows().forEach(row => row.remove());
      updateSummary();
      showToast('Cart cleared.');
    });

    document.getElementById('updateCartBtn')?.addEventListener('click', () => {
      updateSubtotals();
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
      radio.addEventListener('change', () => {
        updateDeliveryZoneSelection();
        updateSummary();
      });
    });

    updateSubtotals();
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
      closeNewsletterModal();
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
  const animEls = document.querySelectorAll('.product-card, .category-card, .blog-card, .feature-item, .promo-banner');
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

