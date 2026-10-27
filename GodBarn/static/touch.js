/* God Barn touch layout, shared by every God Barn surface.
 * Canonical copy: GodBarn/static/touch.js (loaded by God Barn's own index.html on desktop and Bifrost).
 * The iPad app injects an identical copy so servers that predate it still get the layout;
 * the shared window.__fvGodBarnTouch flag keeps it from running twice.
 * Keeps God Barn's FarmVillage skin (logo, sky, wood, glossy buttons, FVCaslon) and its own logic.
 * God Barn delegates every event from `document`, so layout changes never detach its handlers. */
(() => {
  'use strict';
  const path = location.pathname;
  const onBarn = path === '/god-barn' || path.startsWith('/god-barn/') || window.__fvGodBarnTouchForce === true
    || Boolean(document.currentScript && document.currentScript.hasAttribute('data-god-barn-touch'));
  if (!onBarn || window.__fvGodBarnTouch) return;
  window.__fvGodBarnTouch = true;

  const css = `
  html.fv-touch-barn { --fv-top: 64px; --fv-tabs: 78px; --fv-safe-t: env(safe-area-inset-top, 0px); --fv-safe-l: env(safe-area-inset-left, 0px);
    --fv-safe-r: env(safe-area-inset-right, 0px); --fv-safe-b: env(safe-area-inset-bottom, 0px); }
  html.fv-touch-barn, html.fv-touch-barn body { -webkit-text-size-adjust: 100%; overscroll-behavior: none; }
  html.fv-touch-barn * { -webkit-tap-highlight-color: transparent; }
  html.fv-touch-barn .app-shell {
    max-width: none !important;
    padding: calc(var(--fv-top) + var(--fv-safe-t) + 10px) calc(12px + var(--fv-safe-r)) calc(var(--fv-tabs) + var(--fv-safe-b) + 14px) calc(12px + var(--fv-safe-l)) !important;
  }

  /* ── Branded top bar: logo and wordmark on the left, farm controls on the right ── */
  html.fv-touch-barn .sidebar {
    position: fixed !important; inset: 0 0 auto 0 !important; height: calc(var(--fv-top) + var(--fv-safe-t)); z-index: 30;
    display: flex !important; align-items: center !important; gap: 0 !important;
    /* Notch insets (viewport-fit=cover): the bar grows down by the top inset and stops short of side notches. Zero insets change nothing. */
    margin: 0 var(--fv-safe-r) 0 var(--fv-safe-l) !important;
    padding: var(--fv-safe-t) 12px 0 16px !important;
    background: linear-gradient(#bfe9fb, #8fd2f2) !important; border: 0 !important;
    border-bottom: 10px solid transparent !important;
    border-image: url('static/assets/ui/wood-grain.png') 24 round !important;
    box-shadow: 0 4px 8px #553a2040 !important;
  }
  html.fv-touch.fv-touch-barn .sidebar { padding-left: 64px !important; } /* clear the iPad app's round menu button */
  @media (min-width: 1300px) { html.fv-touch-barn .main { max-width: 1320px; margin: 0 auto !important; } }
  html.fv-touch-barn .brand { min-width: 0 !important; gap: 10px !important; height: 100%;
    display: flex !important; flex-direction: row !important; align-items: center !important; }
  html.fv-touch-barn .brand > * { position: static !important; inset: auto !important; transform: none !important; margin: 0 !important; }
  html.fv-touch-barn .brand img { height: 40px !important; width: auto !important; }
  html.fv-touch-barn .brand-sub, html.fv-touch-barn .nav-label, html.fv-touch-barn .sidebar-bottom { display: none !important; }

  html.fv-touch-barn .topbar {
    position: fixed !important; top: var(--fv-safe-t) !important; right: calc(12px + var(--fv-safe-r)) !important; left: auto !important;
    height: var(--fv-top); z-index: 31; display: flex !important; align-items: center !important;
    background: none !important; border: 0 !important; box-shadow: none !important; padding: 0 !important; margin: 0 !important;
  }
  html.fv-touch-barn .topbar .breadcrumb { display: none !important; }
  html.fv-touch-barn .top-actions { gap: 8px !important; flex-wrap: nowrap !important; }
  html.fv-touch-barn .top-actions .button { min-height: 44px; padding: 8px 14px !important; white-space: nowrap; }
  html.fv-touch-barn .top-actions .farm-select { min-height: 44px; max-width: 170px; font-size: 16px !important; }

  /* ── Bottom tab bar: all sections, icon over label, gold when active ── */
  html.fv-touch-barn .nav {
    position: fixed !important; left: 0; right: 0; bottom: 0; z-index: 30;
    height: calc(var(--fv-tabs) + var(--fv-safe-b));
    padding: 6px calc(8px + var(--fv-safe-r)) calc(6px + var(--fv-safe-b)) calc(8px + var(--fv-safe-l)) !important;
    display: grid !important; grid-auto-flow: column; grid-auto-columns: minmax(84px, 1fr); gap: 6px !important;
    overflow-x: auto; -webkit-overflow-scrolling: touch; overscroll-behavior-x: contain; scrollbar-width: none;
    margin: 0 !important; flex-wrap: nowrap !important;
    background: #7a5530 url('static/assets/ui/wood-grain.png') center/240px repeat !important;
    border-top: 3px solid #4f3418; box-shadow: 0 -4px 10px #2b1c0d55;
  }
  html.fv-touch-barn .nav::-webkit-scrollbar { display: none; }
  html.fv-touch-barn .nav button {
    display: flex !important; flex-direction: column !important; align-items: center !important; justify-content: center !important;
    gap: 3px !important; min-height: 0 !important; height: 100% !important; width: auto !important; margin: 0 !important;
    padding: 4px 4px 5px !important; border-radius: 14px !important; font-size: 11.5px !important; line-height: 1.1 !important;
    text-align: center !important; white-space: normal !important; touch-action: manipulation;
  }
  html.fv-touch-barn .nav button img { width: 30px !important; height: 30px !important; margin: 0 !important; object-fit: contain; }
  html.fv-touch-barn .nav button span { display: block; max-width: 100%; overflow-wrap: anywhere; hyphens: auto; }
  html.fv-touch-barn .nav button:active { transform: translateY(1px) scale(.97); }

  /* ── Content frame uses the full width ── */
  html.fv-touch-barn .main { margin: 0 !important; min-height: 0 !important; }
  html.fv-touch-barn .content { padding: 18px 18px 22px !important; }
  html.fv-touch-barn .page-heading h1 { font-size: 30px !important; }

  /* ── Touch targets ── */
  html.fv-touch-barn :is(.button, .chip, select, .select, .field, .text-button, summary, input[type="date"]) { min-height: 44px; }
  html.fv-touch-barn .button { font-size: 15px !important; padding: 10px 18px !important; border-radius: 12px !important; }
  html.fv-touch-barn .button.tiny { min-height: 44px; padding: 8px 14px !important; font-size: 14px !important; }
  html.fv-touch-barn .chip { min-width: 52px; padding: 8px 14px !important; font-size: 15px !important; border-radius: 22px !important; }
  html.fv-touch-barn .chips { gap: 8px !important; flex-wrap: wrap; }
  html.fv-touch-barn .field, html.fv-touch-barn .select { font-size: 17px !important; }
  html.fv-touch-barn :is(.button, .chip, .quick-action, .item-card, .catalog-types button):active {
    transform: translateY(1px); filter: brightness(.96);
  }
  html.fv-touch-barn input[type="checkbox"] { width: 28px; height: 28px; margin: 8px; accent-color: #5aa12b; }
  /* Bare checkboxes are wrapped in a transparent 44px label (addHitAreas); the 28px box keeps its look. */
  html.fv-touch-barn label.fv-hit { display: inline-flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; cursor: pointer; }
  html.fv-touch-barn label.fv-hit > input[type="checkbox"] { margin: 0; }
  html.fv-touch-barn .checkbox-label { min-height: 48px; display: flex !important; align-items: center; gap: 6px; font-size: 15px; }
  html.fv-touch-barn .crop-table :is(td, th) { height: 54px; padding-top: 4px !important; padding-bottom: 4px !important; }
  html.fv-touch-barn .crop-table tbody tr { cursor: pointer; }
  html.fv-touch-barn .item-card { min-height: 180px; }
  html.fv-touch-barn .item-card .fav { min-width: 44px !important; min-height: 44px !important; font-size: 24px !important;
    display: inline-flex !important; align-items: center; justify-content: center; }
  html.fv-touch-barn .quick-action { min-height: 64px; }

  /* Sliders: big gold thumb */
  html.fv-touch-barn input[type="range"] { -webkit-appearance: none; appearance: none; height: 48px; width: 100%; background: none; touch-action: pan-y; }
  html.fv-touch-barn input[type="range"]::-webkit-slider-runnable-track {
    height: 10px; border-radius: 5px; background: linear-gradient(#c9a25e, #e7cd8d); box-shadow: inset 0 1px 2px #6b4a2266;
  }
  html.fv-touch-barn input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none; width: 38px; height: 38px; border-radius: 50%; margin-top: -14px;
    background: linear-gradient(#ffef9d, #ffd45e 47%, #ecb432 50%, #d99a27); border: 2px solid #a8701f;
    box-shadow: inset 0 2px 0 #fff7c8, 0 3px 4px #0005;
  }

  /* Steppers */
  html.fv-touch-barn .fv-stepper { display: inline-flex; align-items: stretch; gap: 8px; flex: 1 1 auto; min-width: 0; }
  html.fv-touch-barn .fv-stepper > input { flex: 1 1 auto; min-width: 80px; text-align: center; font-size: 20px !important; font-weight: 700; }
  html.fv-touch-barn .fv-step {
    flex: 0 0 auto; width: 52px; min-height: 48px; padding: 0; border-radius: 12px; cursor: pointer;
    font: 700 28px/1 FVCaslon, Georgia, serif; color: #5f3b18; border: 2px solid #b17a38;
    background: linear-gradient(#fff4be 0, #f9dd8c 47%, #ecc26c 49%, #e5b455);
    box-shadow: inset 0 2px 0 #fff9df, 0 2px 0 #81522255; touch-action: manipulation; -webkit-user-select: none; user-select: none;
  }
  html.fv-touch-barn .fv-step:active { transform: translateY(1px); filter: brightness(.94); }
  html.fv-touch-barn .fv-step:disabled { opacity: .4; }
  /* The −/+ buttons replace the native spinners, so hide the spinners themselves. */
  html.fv-touch-barn input[type="number"] { appearance: textfield; -moz-appearance: textfield; }
  html.fv-touch-barn input[type="number"]::-webkit-inner-spin-button, html.fv-touch-barn input[type="number"]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }

  /* Segmented control replacing short dropdowns */
  html.fv-touch-barn .input-row:has(.fv-seg) { flex-wrap: wrap !important; gap: 10px !important; }
  html.fv-touch-barn .input-row:has(.fv-seg) > .fv-seg { flex: 1 1 100%; }
  html.fv-touch-barn .input-row:has(.fv-seg) > .fv-stepper { flex: 1 1 100%; }
  /* Segmented switches never clip: they shrink, wrap inside their row, and take a full line when the row is full. */
  html.fv-touch-barn :has(> .fv-seg) { flex-wrap: wrap; }
  html.fv-touch-barn .fv-seg { flex: 1 1 auto; min-width: 0; max-width: 100%; display: flex; flex-wrap: wrap; gap: 0;
    border: 2px solid #b17a38; border-radius: 13px; overflow: visible; box-shadow: 0 2px 0 #81522233; background: #fff9df; }
  html.fv-touch-barn .fv-seg button { flex: 1 1 0; min-width: 44px; min-height: 46px; padding: 8px 16px; border: 0; border-left: 1px solid #d9b56c;
    background: none; white-space: normal; overflow-wrap: anywhere; text-align: center; line-height: 1.15;
    font: 700 15px FVCaslon, Georgia, serif; color: #6b4520; cursor: pointer; touch-action: manipulation; }
  html.fv-touch-barn .fv-seg button:first-child { border-left: 0; border-radius: 11px 0 0 11px; }
  html.fv-touch-barn .fv-seg button:last-child { border-radius: 0 11px 11px 0; }
  html.fv-touch-barn .fv-seg button:focus-visible { outline: 3px solid #f5b318; outline-offset: -4px; }
  /* Pressed green keeps its gloss; the darkest stop keeps white bold text at 4.5:1 or better. */
  html.fv-touch-barn .fv-seg button[aria-pressed="true"] { background: linear-gradient(#368012, #2c690b); color: #fff;
    text-shadow: 0 1px 0 #2e6a0b; box-shadow: inset 0 1px 0 #b7ec7a80; }
  html.fv-touch-barn select.fv-seg-hidden { position: absolute !important; opacity: 0 !important; pointer-events: none !important; width: 1px !important; height: 1px !important; }

  /* Time machine dial */
  html.fv-touch-barn .clock.fv-dial { width: 210px !important; height: 210px !important; cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none; }
  html.fv-touch-barn .clock.fv-dial:before, html.fv-touch-barn .clock.fv-dial:after { display: none !important; }
  html.fv-touch-barn .clock.fv-dial:focus-visible { outline: 3px solid #f5b318; outline-offset: 4px; }
  html.fv-touch-barn .fv-dial-hand { position: absolute; left: 50%; top: 50%; width: 8px; height: 78px; margin-left: -4px; margin-top: -74px;
    border-radius: 4px; background: #8a5a22; transform-origin: 50% 74px; box-shadow: 0 1px 2px #0004; pointer-events: none; }
  html.fv-touch-barn .fv-dial-knob { position: absolute; left: 50%; top: 50%; width: 34px; height: 34px; margin: -17px; border-radius: 50%;
    background: linear-gradient(#ffef9d, #ecb432); border: 2px solid #a8701f; box-shadow: 0 2px 3px #0005; pointer-events: none;
    transform-origin: 50% 50%; }
  html.fv-touch-barn .fv-dial-hint { text-align: center; font: 700 13px FVCaslon, Georgia, serif; color: #8a5a22; margin-top: -10px; }

  /* Pop-ups become bottom sheets */
  html.fv-touch-barn #overlay, html.fv-touch-barn .modal-shade { z-index: 60 !important; }
  html.fv-touch-barn .modal-shade { align-items: flex-end !important; justify-content: center !important; padding: 0 !important; }
  html.fv-touch-barn .modal {
    width: min(820px, 100vw) !important; max-width: 100vw !important; max-height: 88vh !important; margin: 0 !important;
    border-bottom-width: 0 !important; border-radius: 22px 22px 0 0 !important; animation: fv-sheet .22s ease-out;
    padding-bottom: var(--fv-safe-b);
  }
  html.fv-touch-barn .modal-footer { position: sticky; bottom: 0; }
  html.fv-touch-barn .modal-footer .button { min-height: 50px; flex: 1 1 0; }
  html.fv-touch-barn .modal .close { width: 44px !important; height: 44px !important; font-size: 26px !important; }
  @keyframes fv-sheet { from { transform: translateY(40px); opacity: .4; } to { transform: none; opacity: 1; } }

  /* Toasts sit above the tab bar */
  html.fv-touch-barn #toast { bottom: calc(var(--fv-tabs) + var(--fv-safe-b) + 14px) !important; }

  /* Portrait / narrow: keep tabs at least 64px wide and let the tab bar scroll sideways instead of squeezing them */
  @media (max-width: 820px) {
    html.fv-touch-barn .top-actions .button { padding: 8px 10px !important; font-size: 13px !important; }
    html.fv-touch-barn .top-actions .farm-select { max-width: 120px; }
    html.fv-touch-barn .nav { grid-auto-columns: minmax(64px, 1fr); gap: 4px !important; padding-left: calc(5px + var(--fv-safe-l)) !important; padding-right: calc(5px + var(--fv-safe-r)) !important; }
    html.fv-touch-barn .nav button { font-size: 10px !important; padding: 4px 2px 5px !important; border-radius: 11px !important; letter-spacing: -.01em; }
    html.fv-touch-barn .nav button img { width: 27px !important; height: 27px !important; }
  }
  /* Phones: the FarmVille logo gives way and the farm controls shrink to two-line buttons, clear of the God Barn wordmark */
  /* Long dropdowns (more than four choices) stay native; give them room and let their row wrap on narrow screens. */
  html.fv-touch-barn .input-row { flex-wrap: wrap; }
  html.fv-touch-barn .input-row > select.select:not(.fv-seg-hidden) { flex: 1 1 140px; min-width: 120px; }
  @media (max-width: 620px) {
    html.fv-touch-barn .brand img.farmville-wordmark { display: none !important; }
    html.fv-touch-barn .top-actions { gap: 6px !important; }
    html.fv-touch-barn .top-actions .farm-select { max-width: 84px; }
    html.fv-touch-barn .top-actions .button { min-height: 44px; max-width: 64px; padding: 6px 4px !important; font-size: 12px !important;
      line-height: 1.15; white-space: normal !important; text-align: center; }
  }
  @media (max-width: 420px) {
    html.fv-touch-barn .fv-seg button { padding-inline: 6px; white-space: normal; }
  }
  @media (prefers-reduced-motion: reduce){ html.fv-touch-barn .modal{animation:none!important} html.fv-touch-barn *{transition:none!important} }
  `;

  /* ── Steppers ── */
  const decimals = step => (String(step).split('.')[1] || '').length;
  // Visible text of a field's <label>, leaving out any controls nested inside it.
  const textOf = node => [...node.childNodes].map(child => {
    if (child.nodeType === 3) return child.textContent;
    if (child.nodeType === 1 && !/^(INPUT|SELECT|TEXTAREA|BUTTON|OPTION)$/.test(child.tagName)) return textOf(child);
    return '';
  }).join('');
  const labelText = control => {
    const label = control.labels?.[0];
    return label ? textOf(label).replace(/\s+/g, ' ').trim() : '';
  };
  function bounds(input) {
    const min = input.min === '' ? -Infinity : Number(input.min);
    const max = input.max === '' ? Infinity : Number(input.max);
    const raw = input.step === '' || input.step === 'any' ? 1 : Number(input.step);
    return { min, max, step: raw > 0 ? raw : 1 };
  }
  function setValue(input, value) {
    if (String(value) === input.value) return false;
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  function nudge(input, direction, multiplier) {
    const { min, max, step } = bounds(input);
    const current = input.value === '' || Number.isNaN(Number(input.value)) ? (Number.isFinite(min) ? min : 0) : Number(input.value);
    const next = Math.min(max, Math.max(min, current + direction * step * multiplier));
    return setValue(input, next.toFixed(decimals(step)));
  }
  function refreshStepper(wrapper) {
    const input = wrapper.querySelector('input');
    const [down, up] = wrapper.querySelectorAll('.fv-step');
    const { min, max } = bounds(input);
    const value = Number(input.value);
    down.disabled = input.disabled || (!Number.isNaN(value) && value <= min);
    up.disabled = input.disabled || (!Number.isNaN(value) && value >= max);
  }
  function stepButton(label, direction, name, input, wrapper) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'fv-step';
    button.textContent = label;
    button.setAttribute('aria-label', (direction > 0 ? 'Increase ' : 'Decrease ') + name);
    let timer = null, repeats = 0;
    const stop = () => { clearTimeout(timer); timer = null; refreshStepper(wrapper); };
    // Holding accelerates through 1×, 10×, 100× and 1000× the field's own step.
    const tick = () => {
      repeats += 1;
      const multiplier = repeats < 8 ? 1 : repeats < 20 ? 10 : repeats < 34 ? 100 : 1000;
      if (!nudge(input, direction, multiplier)) return stop();
      refreshStepper(wrapper);
      timer = setTimeout(tick, repeats < 8 ? 160 : 90);
    };
    button.addEventListener('pointerdown', event => {
      event.preventDefault();
      repeats = 0;
      nudge(input, direction, 1);
      refreshStepper(wrapper);
      timer = setTimeout(tick, 450);
    });
    for (const type of ['pointerup', 'pointercancel', 'pointerleave']) button.addEventListener(type, stop);
    button.addEventListener('click', event => { if (event.detail === 0) { nudge(input, direction, 1); refreshStepper(wrapper); } });
    return button;
  }
  // Keyboard: PageUp/PageDown move ten steps; Home and End jump to the field's own limits when it has them.
  function stepperKey(event, input, wrapper) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const { min, max, step } = bounds(input);
    if (event.key === 'PageUp' || event.key === 'PageDown') nudge(input, event.key === 'PageUp' ? 1 : -1, 10);
    else if (event.key === 'Home' && Number.isFinite(min)) setValue(input, min.toFixed(decimals(step)));
    else if (event.key === 'End' && Number.isFinite(max)) setValue(input, max.toFixed(decimals(step)));
    else return;
    event.preventDefault();
    refreshStepper(wrapper);
  }
  function addSteppers(root) {
    for (const input of root.querySelectorAll('input[type="number"]:not([data-fv-stepper])')) {
      input.dataset.fvStepper = '1';
      input.setAttribute('inputmode', decimals(bounds(input).step) ? 'decimal' : 'numeric');
      // Read the name before replaceWith(): moving the field out of the page empties its labels.
      const name = input.getAttribute('aria-label') || labelText(input) || 'value';
      const wrapper = document.createElement('span');
      wrapper.className = 'fv-stepper';
      input.replaceWith(wrapper);
      wrapper.append(stepButton('−', -1, name, input, wrapper), input, stepButton('+', 1, name, input, wrapper));
      input.addEventListener('input', () => refreshStepper(wrapper));
      input.addEventListener('keydown', event => stepperKey(event, input, wrapper));
      refreshStepper(wrapper);
    }
  }

  /* Bare checkboxes (the plot pickers) get a 44px hit area. The 8px margin around the 28px box is not clickable, so the
     box moves into a transparent 44px label with the same footprint: it looks the same and the table rows do not move. */
  function addHitAreas(root) {
    for (const box of root.querySelectorAll('input[type="checkbox"]:not([data-fv-hit])')) {
      box.dataset.fvHit = '1';
      if (box.closest('label')) continue; // already inside a label, which is already a large target
      const wrapper = document.createElement('label');
      wrapper.className = 'fv-hit';
      box.before(wrapper);
      wrapper.append(box);
    }
  }

  /* ── Segmented controls for short dropdowns (2–4 options) ── */
  function addSegments(root) {
    for (const select of root.querySelectorAll('select:not([data-fv-seg]):not(#farm-picker):not([multiple])')) {
      const options = [...select.options];
      // Flag only after the length check: a list that fills in later (land-deed sizes load asynchronously) gets segmented then.
      if (options.length < 2 || options.length > 4 || options.some(o => o.textContent.trim().length > 18)) continue;
      select.dataset.fvSeg = '1';
      const group = document.createElement('div');
      group.className = 'fv-seg';
      group.setAttribute('role', 'group');
      const name = select.getAttribute('aria-label') || labelText(select) || select.getAttribute('name');
      if (name) group.setAttribute('aria-label', name);
      const sync = () => { for (const b of group.children) b.setAttribute('aria-pressed', String(b.dataset.value === select.value)); };
      for (const option of options) {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.value = option.value;
        button.textContent = option.textContent.trim();
        button.disabled = option.disabled;
        button.addEventListener('click', () => {
          if (select.value === option.value) return;
          select.value = option.value;
          select.dispatchEvent(new Event('input', { bubbles: true }));
          select.dispatchEvent(new Event('change', { bubbles: true }));
          sync();
        });
        group.appendChild(button);
      }
      select.classList.add('fv-seg-hidden');
      // The select keeps its value, change events and form submission (it is not display:none), but is no longer a tab stop.
      select.tabIndex = -1;
      select.setAttribute('aria-hidden', 'true');
      select.after(group);
      select.addEventListener('change', sync);
      sync();
    }
  }

  /* ── Time machine: spin the clock. One turn = 12 hours, range 1–72 like the slider. ── */
  const DIAL_MIN = 1, DIAL_MAX = 72;
  let refreshDial = null;
  // One document listener serves whichever dial is on screen, so re-renders do not stack listeners.
  document.addEventListener('input', event => {
    if (refreshDial && (event.target.id === 'time-range' || event.target.id === 'time-hours')) refreshDial();
  });
  function addDial(root) {
    const clock = root.querySelector?.('.clock:not(.fv-dial)') || (root.classList?.contains('clock') && !root.classList.contains('fv-dial') ? root : null);
    const range = document.getElementById('time-range');
    if (!clock || !range) return;
    clock.classList.add('fv-dial');
    clock.setAttribute('role', 'slider');
    clock.setAttribute('tabindex', '0');
    clock.setAttribute('aria-label', 'Spin to choose hours forward');
    clock.setAttribute('aria-valuemin', String(DIAL_MIN));
    clock.setAttribute('aria-valuemax', String(DIAL_MAX));
    const hand = document.createElement('div');
    hand.className = 'fv-dial-hand';
    const knob = document.createElement('div');
    knob.className = 'fv-dial-knob';
    clock.append(hand, knob);
    const hint = document.createElement('div');
    hint.className = 'fv-dial-hint';
    hint.textContent = 'Spin the clock ↻';
    clock.after(hint);
    const clamp = value => Math.min(DIAL_MAX, Math.max(DIAL_MIN, value));
    const hours = () => Number(document.getElementById('time-hours')?.value || range.value) || DIAL_MIN;
    const show = () => {
      const now = clamp(hours());
      hand.style.transform = `rotate(${(now % 12) / 12 * 360}deg)`;
      clock.setAttribute('aria-valuenow', String(now));
      clock.setAttribute('aria-valuetext', `${now} ${now === 1 ? 'hour' : 'hours'}`);
    };
    refreshDial = show;
    // Drag and keyboard both write through here. The input event reaches God Barn's own handler, which updates #time-hours,
    // so show() runs after the dispatch and reads the new value.
    const commit = whole => {
      if (String(whole) === range.value) return;
      range.value = String(whole);
      range.dispatchEvent(new Event('input', { bubbles: true }));
      show();
    };
    let last = null, total = 0, pointer = null;
    const angleOf = event => {
      const rect = clock.getBoundingClientRect();
      return Math.atan2(event.clientX - (rect.left + rect.width / 2), -(event.clientY - (rect.top + rect.height / 2))) * 180 / Math.PI;
    };
    clock.addEventListener('pointerdown', event => {
      if (pointer !== null) return; // a second finger or pointer must not steer the dial too
      event.preventDefault();
      pointer = event.pointerId;
      clock.setPointerCapture(event.pointerId);
      clock.focus({ preventScroll: true });
      last = angleOf(event);
      total = hours();
    });
    clock.addEventListener('pointermove', event => {
      if (last === null || event.pointerId !== pointer) return;
      const now = angleOf(event);
      let delta = now - last;
      if (delta > 180) delta -= 360;
      if (delta < -180) delta += 360;
      last = now;
      total = clamp(total + delta / 30);
      commit(Math.round(total));
      hand.style.transform = `rotate(${(total % 12) / 12 * 360}deg)`;
    });
    const end = event => {
      if (event.pointerId !== pointer) return;
      pointer = null;
      last = null;
      show();
    };
    clock.addEventListener('pointerup', end);
    clock.addEventListener('pointercancel', end);
    clock.addEventListener('lostpointercapture', end);
    // Keyboard: arrows move one hour, Page keys six, Home and End jump to the ends of the range.
    clock.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const now = Math.round(clamp(hours()));
      const moves = { ArrowUp: now + 1, ArrowRight: now + 1, ArrowDown: now - 1, ArrowLeft: now - 1,
        PageUp: now + 6, PageDown: now - 6, Home: DIAL_MIN, End: DIAL_MAX };
      if (!Object.prototype.hasOwnProperty.call(moves, event.key)) return;
      event.preventDefault();
      commit(clamp(moves[event.key]));
    });
    show();
  }

  /* Tap anywhere on a crop row to toggle its checkbox. */
  document.addEventListener('click', event => {
    const row = event.target.closest?.('.crop-table tbody tr');
    if (!row || event.target.closest('input, button, a, select, label')) return;
    const box = row.querySelector('input[type="checkbox"]:not(:disabled)');
    if (box) box.click();
  });

  function enhance(root) {
    addSteppers(root);
    addSegments(root);
    addDial(root);
    addHitAreas(root);
  }

  function start() {
    document.documentElement.classList.add('fv-touch-barn');
    const style = document.createElement('style');
    style.id = 'farmvillage-godbarn-touch';
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
    enhance(document);
    // God Barn re-renders pages and sheets; enhance new content as it appears.
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; enhance(document); });
    }).observe(document.body || document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
