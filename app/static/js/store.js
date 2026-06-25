const toastEl = document.getElementById('toast');
const fmt = (n) => Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function showToast(msg, type = 'success') {
  if (!toastEl) return;
  toastEl.textContent = msg;
  toastEl.className = `toast show fixed bottom-20 md:bottom-6 right-4 z-50 px-5 py-3 rounded-xl text-white text-sm font-medium shadow-lg ${type === 'error' ? 'bg-rose-500' : 'bg-emerald-500'}`;
  setTimeout(() => toastEl.classList.remove('show'), 2500);
}

function renderCart(cart) {
  const badge = document.getElementById('cart-badge');
  const subtotal = document.getElementById('cart-subtotal');
  const total = document.getElementById('cart-total');
  const checkoutBtn = document.getElementById('checkout-btn');
  const container = document.getElementById('cart-items-container');
  if (badge) badge.textContent = cart.total_items;
  if (subtotal) subtotal.textContent = '$' + fmt(cart.subtotal);
  if (total) total.textContent = '$' + fmt(cart.total);
  if (checkoutBtn) checkoutBtn.disabled = cart.total_items === 0;
  if (!container) return;
  if (!cart.items.length) {
    container.innerHTML = '<p class="text-sm text-slate-500 text-center py-8">Your cart is empty.</p>';
    return;
  }
  container.innerHTML = cart.items.map(item => `
    <div class="flex items-center justify-between border-b border-slate-800/20 pb-4">
      <div class="flex items-center space-x-3">
        <img src="${item.image_url}" class="w-12 h-12 rounded-lg object-cover border border-slate-700/30" alt="">
        <div><h4 class="text-sm font-semibold truncate w-28">${item.name}</h4><div class="text-xs text-indigo-400 font-mono">$${fmt(item.price)}</div></div>
      </div>
      <div class="flex items-center space-x-2">
        <button type="button" data-cart-action="decrease" data-item-id="${item.id}" class="p-1 rounded-md bg-slate-800 border border-slate-700/50">−</button>
        <span class="font-mono text-sm w-4 text-center">${item.quantity}</span>
        <button type="button" data-cart-action="increase" data-item-id="${item.id}" class="p-1 rounded-md bg-slate-800 border border-slate-700/50">+</button>
      </div>
    </div>`).join('');
  bindCartActions();
}

async function addToCart(productId) {
  const res = await fetch(`/cart/add/${productId}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
  const data = await res.json();
  if (data.success) { renderCart(data.cart); showToast('Added to cart'); }
  else showToast(data.message || 'Could not add', 'error');
}

async function updateCart(itemId, action) {
  const body = new FormData(); body.append('action', action);
  const res = await fetch(`/cart/update/${itemId}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }, body });
  const data = await res.json();
  if (data.success) { renderCart(data.cart); showToast('Cart updated'); }
}

function bindCartActions() {
  document.querySelectorAll('[data-cart-action]').forEach(btn => {
    btn.onclick = () => updateCart(btn.dataset.itemId, btn.dataset.cartAction);
  });
}

async function toggleWishlist(productId, btn) {
  const res = await fetch(`/wishlist/toggle/${productId}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
  const data = await res.json();
  if (!data.success) { showToast(data.message || 'Login required', 'error'); return; }
  btn.classList.toggle('text-rose-400', data.wishlisted);
  btn.classList.toggle('text-slate-500', !data.wishlisted);
  showToast(data.wishlisted ? 'Added to wishlist' : 'Removed from wishlist');
}

async function openProductModal(productId) {
  const modal = document.getElementById('product-modal');
  const body = document.getElementById('product-modal-body');
  if (!modal || !body) return;
  body.innerHTML = '<div class="skeleton h-64 w-full"></div>';
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  const res = await fetch(`/api/v1/products/${productId}`);
  const json = await res.json();
  const p = json.data;
  const gallery = (p.gallery_urls || [p.image_url]).filter(Boolean).map(u => `<img src="${u}" class="w-20 h-20 rounded-lg object-cover border border-slate-700/30 cursor-pointer" alt="">`).join('');
  const reviews = (p.reviews || []).map(r => `<div class="text-sm border-b border-slate-800/30 py-2"><span class="text-amber-400">${'★'.repeat(r.rating)}</span> <b>${r.user}</b><p class="text-slate-400">${r.comment || ''}</p></div>`).join('') || '<p class="text-slate-500 text-sm">No reviews yet.</p>';
  const fbt = (p.frequently_bought_together || []).map(i => `<div class="text-xs bg-slate-800/50 rounded-lg p-2">${i.name} — $${fmt(i.price)}</div>`).join('');
  body.innerHTML = `
    <div class="grid md:grid-cols-2 gap-6">
      <div><img src="${p.image_url}" class="w-full h-64 object-cover rounded-xl" alt=""><div class="flex gap-2 mt-3 overflow-x-auto">${gallery}</div></div>
      <div class="space-y-4">
        <span class="text-xs text-indigo-400 uppercase">${p.category}</span>
        <h2 class="text-2xl font-bold">${p.name}</h2>
        <div class="flex items-center gap-2"><span class="text-2xl font-mono font-bold text-indigo-400">$${fmt(p.effective_price)}</span>${p.flash_sale ? `<span class="text-xs bg-rose-500/20 text-rose-400 px-2 py-1 rounded-full">Flash -${p.flash_sale.discount_percent}%</span>` : ''}</div>
        ${p.flash_sale ? `<div id="flash-countdown" data-ends="${p.flash_sale.ends_at}" class="text-xs text-amber-400"></div>` : ''}
        <p class="text-slate-400 text-sm">${p.description}</p>
        <div class="text-sm text-amber-400">★ ${p.avg_rating} (${p.review_count} reviews)</div>
        <div class="flex gap-2">
          <button onclick="addToCart(${p.id})" class="flex-1 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl py-3 text-sm font-semibold">Add to Cart</button>
          <button data-wishlist="${p.id}" class="px-4 border border-slate-700 rounded-xl">♥</button>
        </div>
        <div><h4 class="font-semibold text-sm mb-2">Frequently Bought Together</h4><div class="space-y-2">${fbt || '<span class="text-slate-500 text-xs">No data yet</span>'}</div></div>
        <div><h4 class="font-semibold text-sm mb-2">Reviews</h4>${reviews}
        <form id="review-form" class="mt-3 space-y-2 border-t border-slate-800/40 pt-3">
          <label class="text-xs text-slate-400">Your Rating</label>
          <select id="review-rating" class="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl p-2 text-sm"><option value="5">5 ★</option><option value="4">4 ★</option><option value="3">3 ★</option><option value="2">2 ★</option><option value="1">1 ★</option></select>
          <textarea id="review-comment" rows="2" placeholder="Write a review..." class="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl p-2 text-sm"></textarea>
          <button type="submit" class="w-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 rounded-xl py-2 text-xs font-semibold">Submit Review</button>
        </form></div>
      </div>
    </div>`;
  const wbtn = body.querySelector('[data-wishlist]');
  if (wbtn) wbtn.onclick = () => toggleWishlist(p.id, wbtn);
  const reviewForm = body.querySelector('#review-form');
  if (reviewForm) reviewForm.onsubmit = async (e) => {
    e.preventDefault();
    const rating = body.querySelector('#review-rating').value;
    const comment = body.querySelector('#review-comment').value;
    const res = await fetch(`/api/v1/products/${p.id}/reviews`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: parseInt(rating), comment }),
    });
    if (res.ok) { showToast('Review submitted'); openProductModal(p.id); }
    else { const err = await res.json(); showToast(err.errors?.[0]?.message || err.detail || 'Login required to review', 'error'); }
  };
  startFlashCountdown();
}

function closeProductModal() {
  const modal = document.getElementById('product-modal');
  if (modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }
}

function startFlashCountdown() {
  const el = document.getElementById('flash-countdown');
  if (!el) return;
  const end = new Date(el.dataset.ends).getTime();
  const tick = () => {
    const diff = end - Date.now();
    if (diff <= 0) { el.textContent = 'Flash sale ended'; return; }
    const h = Math.floor(diff / 3600000), m = Math.floor((diff % 3600000) / 60000), s = Math.floor((diff % 60000) / 1000);
    el.textContent = `Ends in ${h}h ${m}m ${s}s`;
    requestAnimationFrame(() => setTimeout(tick, 1000));
  };
  tick();
}

function initTheme() {
  const saved = localStorage.getItem('nexus-theme') || 'dark';
  document.documentElement.classList.toggle('dark', saved === 'dark');
  document.body.classList.toggle('light', saved === 'light');
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.onclick = () => {
    const isDark = document.documentElement.classList.contains('dark');
    document.documentElement.classList.toggle('dark', !isDark);
    document.body.classList.toggle('light', isDark);
    localStorage.setItem('nexus-theme', isDark ? 'light' : 'dark');
    showToast('Theme updated');
  };
}

function initWebSocket() {
  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/stock`);
    ws.onmessage = (e) => { const d = JSON.parse(e.data); if (d.type === 'stock_update') showToast(`Stock updated for product #${d.product_id}`); };
  } catch (_) {}
}

async function validateCoupon() {
  const input = document.getElementById('coupon-input');
  const msg = document.getElementById('coupon-msg');
  const subtotalEl = document.getElementById('cart-subtotal');
  if (!input || !msg) return;
  const subtotal = parseFloat((subtotalEl?.textContent || '0').replace(/[$,]/g, '')) || 0;
  const res = await fetch(`/api/coupon/validate?code=${encodeURIComponent(input.value)}&subtotal=${subtotal}`);
  const data = await res.json();
  msg.classList.remove('hidden');
  if (data.valid) {
    msg.textContent = `Coupon applied! You save $${fmt(data.discount)}`;
    msg.className = 'text-xs mt-1 text-emerald-400';
    showToast('Coupon valid');
  } else {
    msg.textContent = 'Invalid or expired coupon';
    msg.className = 'text-xs mt-1 text-rose-400';
    showToast('Invalid coupon', 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-add-cart]').forEach(btn => btn.onclick = () => addToCart(btn.dataset.addCart));
  document.querySelectorAll('[data-product-id]').forEach(card => card.onclick = (e) => {
    if (e.target.closest('button')) return;
    openProductModal(card.dataset.productId);
  });
  document.querySelectorAll('[data-wishlist-id]').forEach(btn => btn.onclick = (e) => { e.stopPropagation(); toggleWishlist(btn.dataset.wishlistId, btn); });
  bindCartActions();
  initTheme();
  initWebSocket();
  document.getElementById('apply-coupon-btn')?.addEventListener('click', validateCoupon);
  const grid = document.getElementById('product-grid');
  if (grid) grid.classList.remove('opacity-0');
});
