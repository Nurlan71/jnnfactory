<!-- JNN Dynamic Catalog (Template Card Pattern) -->
<style>
.catalog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px; }
.cat-card { border: 1px solid var(--line, #e5e5e5); border-radius: 16px; overflow: hidden; background: var(--paper, #fff); transition: transform .2s, box-shadow .2s; display: flex; flex-direction: column; }
.cat-card:hover { transform: translateY(-4px); box-shadow: 0 18px 44px rgba(20,20,20,0.09); }
.cat-img { aspect-ratio: 4/3; overflow: hidden; background: var(--soft, #fafafa); }
.cat-img img { width: 100%; height: 100%; object-fit: cover; transition: transform .4s; }
.cat-card:hover .cat-img img { transform: scale(1.04); }
.cat-body { padding: 16px 18px 20px; display: flex; flex-direction: column; flex: 1; }
.cat-art { font-size: 11px; color: var(--muted, #9ca3af); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; font-weight: 600; }
.cat-body h3 { font-size: 18px; font-weight: 700; margin: 0 0 8px; letter-spacing: -0.3px; }
.cat-desc { font-size: 13px; color: var(--muted, #6b7280); line-height: 1.5; margin-bottom: 12px; flex: 1; }
.cat-specs { font-size: 12px; color: var(--muted, #6b7280); margin-bottom: 14px; display: flex; flex-direction: column; gap: 4px; }
.cat-specs b { color: var(--text, #1d2327); font-weight: 600; }
.cat-price { display: flex; align-items: center; justify-content: space-between; margin-top: auto; }
.price { font-size: 20px; font-weight: 800; color: var(--accent, #2563eb); }
.cat-link { color: var(--accent, #2563eb); font-size: 14px; font-weight: 700; text-decoration: none; }
.cat-link:hover { text-decoration: underline; }
.cat-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; background: var(--accent, #2563eb); color: #fff; margin-bottom: 8px; }
.catalog-error { padding: 40px; text-align: center; color: var(--muted); font-size: 14px; }
</style>
<script>
// Dynamic catalog rendering - Template Card pattern
(async function renderCatalog() {
  const grid = document.querySelector('.catalog-grid');
  if (!grid) return;

  // Save the first static card as template
  const templateCard = grid.querySelector('.cat-card');
  if (!templateCard) return;

  try {
    const resp = await fetch('https://admin.jnnfactory.online/items/products');
    if (!resp.ok) throw new Error('API unavailable');
    const json = await resp.json();
    const products = json.data || [];

    if (products.length === 0) {
      console.log('Catalog: no products from Directus, keeping static content');
      return;
    }

    // Clone template and clear grid
    const templateHTML = templateCard.outerHTML;
    grid.innerHTML = '';

    products.forEach(p => {
      // Create fresh card from template
      const card = document.createElement('div');
      card.innerHTML = templateHTML;
      const el = card.firstElementChild;

      // Populate fields safely
      const setText = (sel, val) => { const e = el.querySelector(sel); if (e) e.textContent = val || ''; };
      const setAttr = (sel, attr, val) => { const e = el.querySelector(sel); if (e) e.setAttribute(attr, val); };
      const setSrc = (sel, src, alt) => {
        const e = el.querySelector(sel);
        if (e) { e.src = src || ''; if (alt) e.alt = alt; }
      };

      // Name
      setText('h3', p.name);

      // Price
      const priceEl = el.querySelector('.price');
      if (priceEl) {
        priceEl.innerHTML = (p.price ? 'от ' + p.price + ' <small>сом</small>' : '');
      }

      // Badge
      const badgeEl = el.querySelector('.cat-badge');
      if (badgeEl && p.badge) {
        badgeEl.textContent = p.badge;
      } else if (badgeEl) {
        badgeEl.style.display = 'none';
      }

      // Article/code
      setText('.cat-art', p.code || '');

      // Description
      setText('.cat-desc', p.description || p.subtitle || '');

      // Bullets (characteristics)
      setText('.cat-specs', p.bullets || '');

      // Image: take first if comma-separated
      const firstImg = (p.image || p.img_1 || '').split(',')[0].trim();
      if (firstImg) {
        setAttr('.cat-img img', 'src', firstImg);
        setAttr('.cat-img img', 'alt', p.name || '');
        setAttr('.cat-img', 'href', '/product.html?id=' + p.id);
      }

      // Link
      const slug = p.slug || (p.name || 'product').toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
      el.querySelectorAll('.cat-link').forEach(a => a.href = '/' + slug + '.html');
      el.querySelectorAll('.cat-img').forEach(a => a.href = '/' + slug + '.html');

      grid.appendChild(el);
    });

    console.log('Catalog: rendered ' + products.length + ' products from Directus');
  } catch (err) {
    console.warn('Catalog: Directus not available, keeping static fallback (' + err.message + ')');
    // Keep existing static cards untouched
  }
})();
</script>