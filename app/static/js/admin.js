document.getElementById('inventory-search')?.addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('.inventory-row').forEach((r) => {
    r.style.display = r.dataset.name.includes(q) || r.dataset.category.includes(q) ? '' : 'none';
  });
});

async function inlineEdit(productId, field, value) {
  const res = await fetch(`/admin/product/${productId}/inline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  });
  return res.json();
}

document.querySelectorAll('.inline-edit').forEach((el) => {
  el.addEventListener('click', async () => {
    const row = el.closest('.inventory-row');
    const productId = row.dataset.id;
    const field = el.dataset.field;
    let current = el.textContent.replace('$', '').trim();
    const next = prompt(`Edit ${field}:`, current);
    if (next === null || next === current) return;
    const result = await inlineEdit(productId, field, next);
    if (result.success) {
      el.textContent = field === 'price' ? `$${parseFloat(next).toFixed(2)}` : next;
    } else {
      alert('Update failed');
    }
  });
});

document.querySelectorAll('.edit-product-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const id = btn.dataset.id;
    document.getElementById('edit-product-form').action = `/admin/product/${id}/edit`;
    document.getElementById('edit-name').value = btn.dataset.name;
    document.getElementById('edit-price').value = btn.dataset.price;
    document.getElementById('edit-stock').value = btn.dataset.stock;
    document.getElementById('edit-category').value = btn.dataset.category;
    document.getElementById('edit-image').value = btn.dataset.image;
    const modal = document.getElementById('edit-product-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  });
});

document.getElementById('edit-product-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'edit-product-modal') {
    e.currentTarget.classList.add('hidden');
    e.currentTarget.classList.remove('flex');
  }
});
