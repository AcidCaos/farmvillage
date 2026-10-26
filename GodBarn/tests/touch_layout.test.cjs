'use strict';
// God Barn's touch layout (static/touch.js) runs in a vm context against a small DOM stub. The stub covers only what
// touch.js uses: the element tree, attributes, classes, labels, events with bubbling, and simple selectors.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'static', 'touch.js'), 'utf8');

class FakeEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = false;
    this.defaultPrevented = false;
    this.target = null;
    Object.assign(this, init);
  }
  preventDefault() { this.defaultPrevented = true; }
}

class Text {
  constructor(text) { this.nodeType = 3; this.textContent = text; this.parentNode = null; }
}

const toKebab = key => key.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`);

class El {
  constructor(tag, doc) {
    this.nodeType = 1;
    this.tagName = tag.toUpperCase();
    this.doc = doc;
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.listeners = {};
    this.style = {};
    this.valueSet = undefined;
    this.pointerCaptures = [];
  }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  hasAttribute(name) { return this.attributes.has(name); }
  removeAttribute(name) { this.attributes.delete(name); }
  get id() { return this.getAttribute('id') ?? ''; }
  set id(value) { this.setAttribute('id', value); }
  get className() { return this.getAttribute('class') ?? ''; }
  set className(value) { this.setAttribute('class', value); }
  get classList() {
    const names = () => this.className.split(/\s+/).filter(Boolean);
    return {
      add: (...added) => this.setAttribute('class', [...new Set([...names(), ...added])].join(' ')),
      remove: (...removed) => this.setAttribute('class', names().filter(name => !removed.includes(name)).join(' ')),
      contains: name => names().includes(name),
    };
  }
  get dataset() {
    return new Proxy({}, {
      get: (_, key) => this.getAttribute(`data-${toKebab(String(key))}`) ?? undefined,
      set: (_, key, value) => { this.setAttribute(`data-${toKebab(String(key))}`, value); return true; },
    });
  }
  get disabled() { return this.hasAttribute('disabled'); }
  set disabled(value) { if (value) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); }
  get tabIndex() { return Number(this.getAttribute('tabindex') ?? 0); }
  set tabIndex(value) { this.setAttribute('tabindex', value); }
  get min() { return this.getAttribute('min') ?? ''; }
  get max() { return this.getAttribute('max') ?? ''; }
  get step() { return this.getAttribute('step') ?? ''; }
  get children() { return this.childNodes.filter(node => node.nodeType === 1); }
  get options() { return this.children.filter(node => node.tagName === 'OPTION'); }
  get value() {
    if (this.tagName === 'OPTION') return this.getAttribute('value') ?? this.textContent;
    if (this.tagName === 'SELECT' && this.valueSet === undefined) {
      const chosen = this.options.find(option => option.hasAttribute('selected')) ?? this.options[0];
      return chosen ? chosen.value : '';
    }
    return this.valueSet ?? this.getAttribute('value') ?? '';
  }
  set value(value) { this.valueSet = String(value); }
  get textContent() { return this.childNodes.map(node => node.textContent).join(''); }
  set textContent(value) {
    for (const node of this.childNodes) node.parentNode = null;
    this.childNodes = [];
    if (value !== '') this.append(String(value));
  }
  get labels() {
    const id = this.id;
    const found = this.doc.all().filter(el => el.tagName === 'LABEL' && id !== '' && el.getAttribute('for') === id);
    for (let node = this.parentNode; node; node = node.parentNode) {
      if (node.tagName === 'LABEL' && !found.includes(node)) found.push(node);
    }
    return found;
  }
  removeNode(node) {
    this.childNodes = this.childNodes.filter(child => child !== node);
    node.parentNode = null;
  }
  insertBefore(node, reference) {
    if (node.parentNode) node.parentNode.removeNode(node);
    node.parentNode = this;
    const index = reference ? this.childNodes.indexOf(reference) : this.childNodes.length;
    this.childNodes.splice(index, 0, node);
    return node;
  }
  append(...nodes) {
    for (const node of nodes) this.insertBefore(typeof node === 'string' ? new Text(node) : node, null);
  }
  appendChild(node) { this.append(node); return node; }
  before(node) { this.parentNode.insertBefore(node, this); }
  after(node) {
    const siblings = this.parentNode.childNodes;
    this.parentNode.insertBefore(node, siblings[siblings.indexOf(this) + 1] ?? null);
  }
  replaceWith(node) {
    const parent = this.parentNode;
    parent.insertBefore(node, this);
    parent.removeNode(this);
  }
  addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); }
  dispatchEvent(event) {
    event.target ??= this;
    for (let node = this; node; node = node.parentNode) {
      for (const listener of [...(node.listeners[event.type] ?? [])]) listener.call(node, event);
      if (!event.bubbles) break;
    }
    return !event.defaultPrevented;
  }
  click() { this.dispatchEvent(new FakeEvent('click', { bubbles: true, detail: 1 })); }
  focus() { this.doc.activeElement = this; }
  setPointerCapture(pointerId) { this.pointerCaptures.push(pointerId); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 210, height: 210 }; }
  closest(selector) {
    for (let node = this; node && node.nodeType === 1; node = node.parentNode) {
      if (matches(node, selector)) return node;
    }
    return null;
  }
  querySelectorAll(selector) { return select(this, selector); }
  querySelector(selector) { return select(this, selector)[0] ?? null; }
}

// Selector support: compound selectors (tag, #id, .class, [attr], [attr="v"], :not(simple), :disabled),
// comma lists and descendant combinators. That is all touch.js uses.
const COMPOUND = /^(?:([a-zA-Z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|([^\]]*)))?\]|:not\(([^()]*)\)|:disabled)/;
function parseCompound(text) {
  const parts = [];
  let rest = text;
  while (rest.length) {
    const m = COMPOUND.exec(rest);
    if (!m) throw new Error(`selector not supported by the DOM stub: ${text}`);
    if (m[1]) parts.push({ tag: m[1].toUpperCase() });
    else if (m[2]) parts.push({ id: m[2] });
    else if (m[3]) parts.push({ cls: m[3] });
    else if (m[4]) parts.push({ attr: m[4], value: m[5] ?? m[6] });
    else if (m[7] !== undefined) parts.push({ not: parseCompound(m[7]) });
    else parts.push({ disabled: true });
    rest = rest.slice(m[0].length);
  }
  return parts;
}
function matchCompound(el, parts) {
  return parts.every(part => {
    if (part.tag) return el.tagName === part.tag;
    if (part.id) return el.id === part.id;
    if (part.cls) return el.classList.contains(part.cls);
    if (part.attr) return el.hasAttribute(part.attr) && (part.value === undefined || el.getAttribute(part.attr) === part.value);
    if (part.not) return !matchCompound(el, part.not);
    return el.hasAttribute('disabled');
  });
}
function matches(el, selector) {
  return selector.split(',').some(alternative => {
    const steps = alternative.trim().split(/\s+/).map(parseCompound);
    if (!matchCompound(el, steps[steps.length - 1])) return false;
    let index = steps.length - 2;
    for (let node = el.parentNode; node && index >= 0; node = node.parentNode) {
      if (node.nodeType === 1 && matchCompound(node, steps[index])) index -= 1;
    }
    return index < 0;
  });
}
function descendants(node, out = []) {
  for (const child of node.childNodes ?? []) {
    if (child.nodeType === 1) {
      out.push(child);
      descendants(child, out);
    }
  }
  return out;
}
function select(root, selector) { return descendants(root).filter(el => matches(el, selector)); }

function createDocument() {
  const doc = { nodeType: 9, parentNode: null, listeners: {}, activeElement: null, readyState: 'complete', currentScript: null };
  doc.childNodes = [];
  const html = new El('html', doc);
  html.parentNode = doc;
  doc.childNodes.push(html);
  doc.documentElement = html;
  doc.head = html.appendChild(new El('head', doc));
  doc.body = html.appendChild(new El('body', doc));
  doc.all = () => descendants(doc);
  doc.createElement = tag => new El(tag, doc);
  doc.getElementById = id => doc.all().find(el => el.id === id) ?? null;
  doc.querySelector = selector => select(doc, selector)[0] ?? null;
  doc.querySelectorAll = selector => select(doc, selector);
  doc.addEventListener = (type, listener) => { (doc.listeners[type] ??= []).push(listener); };
  return doc;
}

function el(doc, tag, attrs = {}, children = []) {
  const node = doc.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  node.append(...children);
  return node;
}

// The God Barn controls that touch.js reshapes, laid out as app.js renders them (abridged).
function barnPage() {
  const doc = createDocument();
  const panel = el(doc, 'section', { class: 'panel' });
  const plotBox = el(doc, 'input', { type: 'checkbox', 'data-plot': '7', 'aria-label': 'Select plot 7' });
  panel.append(
    el(doc, 'div', { class: 'clock' }, [el(doc, 'span', {}, ['XII']), el(doc, 'i')]),
    el(doc, 'input', { type: 'range', id: 'time-range', min: '1', max: '72', value: '6', 'aria-label': 'Hours to advance' }),
    el(doc, 'div', { class: 'input-row' }, [
      el(doc, 'label', { class: 'field-label', for: 'time-hours' }, ['Exact hours']),
      el(doc, 'input', { type: 'number', min: '0.1', max: '8760', step: '0.1', value: '6', id: 'time-hours', class: 'field', required: '' }),
    ]),
    el(doc, 'label', { class: 'checkbox-label' }, [
      el(doc, 'input', { id: 'protect-crops', type: 'checkbox', checked: '' }), 'Stop each crop at harvest readiness',
    ]),
    el(doc, 'label', { class: 'field-label', for: 'grant-quantity' }, [
      'Quantity',
      el(doc, 'input', { class: 'field', id: 'grant-quantity', type: 'number', min: '1', max: '10000', value: '1', required: '' }),
    ]),
    el(doc, 'input', { type: 'number', id: 'loose', value: '3' }),
    el(doc, 'select', { id: 'helper-status', 'aria-label': 'Quest progress' }, [
      el(doc, 'option', { value: 'all' }, ['All']),
      el(doc, 'option', { value: 'incomplete' }, ['Missing']),
    ]),
    el(doc, 'select', { id: 'farm-picker', 'aria-label': 'Choose farm' }, [
      el(doc, 'option', { value: 'a' }, ['Practice farm']),
      el(doc, 'option', { value: 'b' }, ['Second farm']),
    ]),
    el(doc, 'label', { class: 'field-label', for: 'farm-size' }, ['New farm size']),
    el(doc, 'select', { id: 'farm-size', class: 'select', required: '' }, [
      el(doc, 'option', { value: '' }, ['Loading land deeds…']),
    ]),
    el(doc, 'table', { class: 'crop-table' }, [
      el(doc, 'tbody', {}, [el(doc, 'tr', {}, [el(doc, 'td', {}, [plotBox]), el(doc, 'td', {}, ['Corn'])])]),
    ]),
  );
  doc.body.append(panel);
  // app.js setHours(): the slider and the exact-hours field follow each other.
  doc.addEventListener('input', event => {
    const { id, value } = event.target;
    if (id === 'time-range') doc.getElementById('time-hours').value = value;
    else if (id === 'time-hours') doc.getElementById('time-range').value = String(Math.min(72, Math.max(1, value)));
  });
  return doc;
}

// Runs touch.js in a fresh context. settle() plays the MutationObserver callback and its animation frames after a re-render.
function load(doc, pathname = '/god-barn/') {
  const frames = [], observers = [];
  const sandbox = {
    document: doc,
    location: { pathname },
    Event: FakeEvent,
    requestAnimationFrame: callback => { frames.push(callback); },
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe() {}
    },
    setTimeout: () => 0,
    clearTimeout: () => {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  const run = () => vm.runInContext(SOURCE, sandbox, { filename: 'static/touch.js' });
  run();
  return {
    window: sandbox,
    run,
    settle() {
      for (const observer of observers) observer.callback([]);
      while (frames.length) frames.shift()();
    },
  };
}

const key = (type, name, init = {}) => new FakeEvent(type, { key: name, bubbles: true, ...init });
const css = doc => doc.getElementById('farmvillage-godbarn-touch').textContent;

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

test('the injected stylesheet carries the reduced-motion, focus, and phone-width rules', () => {
  const doc = barnPage();
  load(doc);
  const sheet = css(doc);
  assert.match(sheet, /@media \(prefers-reduced-motion: reduce\)\{ html\.fv-touch-barn \.modal\{animation:none!important\} html\.fv-touch-barn \*\{transition:none!important\} \}/);
  assert.match(sheet, /\.modal \{[^}]*animation: fv-sheet/, 'the sheet still animates when motion is allowed');
  assert.match(sheet, /\.clock\.fv-dial:focus-visible \{ outline: 3px solid #f5b318; outline-offset: 4px; \}/);
  assert.match(sheet, /\.fv-seg \{[^}]*overflow: visible/);
  assert.doesNotMatch(sheet, /\.fv-seg \{[^}]*overflow: hidden/);
  assert.match(sheet, /\.fv-seg button:focus-visible \{ outline: 3px solid #f5b318; outline-offset: -4px; \}/);
  assert.match(sheet, /\(max-width: 420px\) \{\s*html\.fv-touch-barn \.fv-seg button \{ padding-inline: 6px; white-space: normal; \}/);
  assert.match(sheet, /grid-auto-columns: minmax\(64px, 1fr\)/);
  assert.doesNotMatch(sheet, /minmax\(0, 1fr\)/, 'tabs no longer squeeze below 64px');
  assert.match(sheet, /\.top-actions \.farm-select \{[^}]*font-size: 16px !important/);
  assert.doesNotMatch(sheet, /brand-title/, 'the dead .brand-title rules are gone');
  const phone = sheet.slice(sheet.indexOf('(max-width: 620px)'));
  assert.match(phone, /\.brand img\.farmville-wordmark \{ display: none !important; \}/);
  assert.match(phone, /\.top-actions \.button \{ min-height: 44px;/);
  assert.match(sheet, /html\.fv-touch-barn input\[type="number"\] \{ appearance: textfield; -moz-appearance: textfield; \}/);
  assert.match(sheet, /input\[type="number"\]::-webkit-inner-spin-button, html\.fv-touch-barn input\[type="number"\]::-webkit-outer-spin-button \{ -webkit-appearance: none; margin: 0; \}/);
  assert.match(sheet, /label\.fv-hit \{[^}]*min-width: 44px; min-height: 44px/);
});

test('no background is brighter than the approved pale cream #fff9df', () => {
  const doc = barnPage();
  load(doc);
  const cream = luminance('#fff9df');
  const fills = [...css(doc).matchAll(/background(?:-color)?:[^;}]*/g)].flatMap(m => m[0].match(/#[0-9a-f]{6}(?![0-9a-f])/gi) ?? []);
  assert.ok(fills.length > 5);
  for (const fill of fills) {
    assert.ok(luminance(fill) <= cream + 1e-9, `${fill} is brighter than #fff9df`);
  }
  assert.doesNotMatch(css(doc), /background(?:-color)?:[^;}]*\bwhite\b/i);
});

test('segmented switches wrap and take a full line instead of clipping', () => {
  const doc = barnPage();
  load(doc);
  const sheet = css(doc);
  assert.match(sheet, /:has\(> \.fv-seg\) \{ flex-wrap: wrap; \}/, 'the parent row wraps');
  assert.match(sheet, /\.fv-seg \{ flex: 1 1 auto; min-width: 0; max-width: 100%; display: flex; flex-wrap: wrap;/);
  assert.match(sheet, /\.fv-seg button \{ flex: 1 1 0; min-width: 44px; min-height: 46px;[^}]*white-space: normal;[^}]*text-align: center;/);
  assert.doesNotMatch(sheet, /\.fv-seg button \{[^}]*white-space: nowrap/);
  assert.doesNotMatch(sheet, /\.fv-seg \{[^}]*overflow: hidden/);
});

test('the pressed segment keeps white bold text at 4.5:1 or better across its gradient', () => {
  const doc = barnPage();
  load(doc);
  const pressed = css(doc).match(/button\[aria-pressed="true"\] \{ background: linear-gradient\(([^)]*)\)/);
  assert.ok(pressed, 'pressed gradient is present');
  const stops = pressed[1].split(',').map(stop => stop.trim()).filter(stop => /^#[0-9a-f]{6}$/i.test(stop));
  assert.ok(stops.length >= 2);
  for (const stop of stops) {
    assert.ok(contrast('#ffffff', stop) >= 4.5, `${stop} is ${contrast('#ffffff', stop).toFixed(2)}:1 against white`);
  }
  assert.ok(contrast('#ffffff', '#6cbf2c') < 4.5, 'the old pressed green was below 4.5:1');
});

test('the time dial is an operable slider: focusable, with a range, a text value and keyboard steps', () => {
  const doc = barnPage();
  load(doc);
  const clock = doc.querySelector('.clock');
  const range = doc.getElementById('time-range');
  const hours = doc.getElementById('time-hours');
  assert.equal(clock.getAttribute('role'), 'slider');
  assert.equal(clock.getAttribute('tabindex'), '0');
  assert.equal(clock.getAttribute('aria-valuemin'), '1');
  assert.equal(clock.getAttribute('aria-valuemax'), '72');
  assert.equal(clock.getAttribute('aria-valuenow'), '6');
  assert.equal(clock.getAttribute('aria-valuetext'), '6 hours');

  const writes = [];
  range.addEventListener('input', () => writes.push(range.value));
  const press = (name, init) => {
    const event = key('keydown', name, init);
    clock.dispatchEvent(event);
    return event.defaultPrevented;
  };
  assert.equal(press('ArrowUp'), true);
  assert.equal(range.value, '7');
  assert.equal(hours.value, '7', 'the same path as the drag: #time-hours follows the slider');
  assert.equal(clock.getAttribute('aria-valuenow'), '7');
  assert.equal(clock.getAttribute('aria-valuetext'), '7 hours');
  press('ArrowLeft');
  press('PageUp');
  assert.equal(range.value, '12');
  press('PageDown');
  press('ArrowRight');
  press('ArrowDown');
  assert.equal(range.value, '6');
  assert.equal(press('End'), true);
  assert.equal(range.value, '72');
  assert.equal(press('ArrowUp'), true, 'a handled key is prevented even at the limit');
  assert.equal(range.value, '72');
  assert.equal(press('Home'), true);
  assert.equal(range.value, '1');
  assert.equal(press('PageDown'), true);
  assert.equal(range.value, '1');
  assert.equal(clock.getAttribute('aria-valuenow'), '1');
  assert.equal(clock.getAttribute('aria-valuetext'), '1 hour');
  assert.equal(press('a'), false, 'other keys are left alone');
  assert.equal(press('ArrowUp', { ctrlKey: true }), false, 'browser shortcuts keep their keys');
  assert.deepEqual(writes, ['7', '6', '12', '6', '7', '6', '72', '1'], 'no input event when nothing changes');
});

test('the dial follows one pointer at a time', () => {
  const doc = barnPage();
  load(doc);
  const clock = doc.querySelector('.clock');
  const range = doc.getElementById('time-range');
  const pointer = (type, pointerId, clientX, clientY) =>
    clock.dispatchEvent(new FakeEvent(type, { pointerId, clientX, clientY, bubbles: true }));
  pointer('pointerdown', 1, 105, 20);
  pointer('pointerdown', 2, 200, 105);
  assert.deepEqual(clock.pointerCaptures, [1], 'the second pointer never captures the dial');
  pointer('pointermove', 1, 200, 105);
  assert.equal(range.value, '9', 'a quarter turn is three hours');
  pointer('pointermove', 2, 105, 20);
  assert.equal(range.value, '9', 'a second pointer cannot steer');
  pointer('pointerup', 2, 105, 20);
  pointer('pointermove', 1, 105, 200);
  assert.equal(range.value, '12', 'the first pointer still drives after the second one lifts');
  pointer('pointerup', 1, 105, 200);
  assert.equal(clock.getAttribute('aria-valuenow'), '12');
  assert.equal(clock.getAttribute('aria-valuetext'), '12 hours');
});

test('stepper buttons are named from their field before the field leaves its label', () => {
  const doc = barnPage();
  load(doc);
  const names = id => [...doc.getElementById(id).parentNode.querySelectorAll('.fv-step')].map(button => button.getAttribute('aria-label'));
  assert.deepEqual(names('time-hours'), ['Decrease Exact hours', 'Increase Exact hours']);
  assert.deepEqual(names('grant-quantity'), ['Decrease Quantity', 'Increase Quantity']);
  assert.deepEqual(names('loose'), ['Decrease value', 'Increase value']);
  assert.match(SOURCE, /const name = input\.getAttribute\('aria-label'\)[^;]*;[\s\S]*input\.replaceWith\(wrapper\)/,
    'the name is computed before replaceWith');
});

test('stepper keys: PageUp and PageDown move ten steps, Home and End go to the limits', () => {
  const doc = barnPage();
  load(doc);
  const hours = doc.getElementById('time-hours');
  const writes = { input: 0, change: 0 };
  hours.addEventListener('input', () => { writes.input += 1; });
  hours.addEventListener('change', () => { writes.change += 1; });
  const press = (field, name) => {
    const event = key('keydown', name);
    field.dispatchEvent(event);
    return event.defaultPrevented;
  };
  assert.equal(press(hours, 'PageUp'), true);
  assert.equal(hours.value, '7.0');
  assert.equal(press(hours, 'PageDown'), true);
  assert.equal(hours.value, '6.0');
  press(hours, 'End');
  assert.equal(hours.value, '8760.0');
  press(hours, 'Home');
  assert.equal(hours.value, '0.1');
  assert.deepEqual(writes, { input: 4, change: 4 }, 'every change dispatches input and change, as the buttons do');

  const quantity = doc.getElementById('grant-quantity');
  assert.equal(press(quantity, 'PageUp'), true);
  assert.equal(quantity.value, '11');
  press(quantity, 'End');
  assert.equal(quantity.value, '10000');
  press(quantity, 'Home');
  assert.equal(quantity.value, '1');
  const before = writes.input;
  assert.equal(press(quantity, 'PageDown'), true, 'handled even when clamped');
  assert.equal(quantity.value, '1', 'clamped at the minimum');
  assert.equal(writes.input, before, 'no event when nothing changed');

  const loose = doc.getElementById('loose');
  assert.equal(press(loose, 'Home'), false, 'Home is left alone without a minimum');
  assert.equal(press(loose, 'End'), false, 'End is left alone without a maximum');
  assert.equal(press(loose, 'PageUp'), true);
  assert.equal(loose.value, '13');
});

test('segmented switches: hidden selects leave the tab order, keep value and events, and are named', () => {
  const doc = barnPage();
  load(doc);
  const select = doc.getElementById('helper-status');
  assert.equal(select.dataset.fvSeg, '1');
  assert.equal(select.tabIndex, -1, 'not a tab stop');
  assert.equal(select.getAttribute('aria-hidden'), 'true');
  assert.ok(select.classList.contains('fv-seg-hidden'));
  const group = doc.querySelectorAll('.fv-seg').find(node => node.getAttribute('aria-label') === 'Quest progress');
  assert.ok(group, 'the group takes the select aria-label as its name');
  assert.equal(group.getAttribute('role'), 'group');

  const changes = [];
  select.addEventListener('change', () => changes.push(select.value));
  const [all, missing] = group.childNodes;
  missing.click();
  assert.equal(select.value, 'incomplete');
  assert.deepEqual(changes, ['incomplete']);
  assert.equal(missing.getAttribute('aria-pressed'), 'true');
  assert.equal(all.getAttribute('aria-pressed'), 'false');

  const picker = doc.getElementById('farm-picker');
  assert.equal(picker.hasAttribute('tabindex'), false, 'the farm picker is not segmented');
  assert.equal(picker.hasAttribute('aria-hidden'), false);
});

test('notch insets: the top bar, its actions, the page and the tab bar clear the safe areas, and zero insets change nothing', () => {
  const doc = barnPage();
  load(doc);
  const sheet = css(doc);
  assert.match(sheet, /--fv-safe-t: env\(safe-area-inset-top, 0px\)/);
  assert.match(sheet, /--fv-safe-l: env\(safe-area-inset-left, 0px\)/);
  assert.match(sheet, /--fv-safe-r: env\(safe-area-inset-right, 0px\)/);
  // The top bar keeps its 64px band (border-box, 10px border inside it) and grows only by the top inset.
  assert.match(sheet, /\.sidebar \{[^}]*height: calc\(var\(--fv-top\) \+ var\(--fv-safe-t\)\)/);
  assert.match(sheet, /\.sidebar \{[^}]*padding: var\(--fv-safe-t\) 12px 0 16px !important/);
  assert.match(sheet, /\.sidebar \{[^}]*margin: 0 var\(--fv-safe-r\) 0 var\(--fv-safe-l\) !important/);
  assert.match(sheet, /\.topbar \{[^}]*top: var\(--fv-safe-t\) !important; right: calc\(12px \+ var\(--fv-safe-r\)\)/);
  assert.match(sheet, /\.app-shell \{\s*max-width: none !important;\s*padding: calc\(var\(--fv-top\) \+ var\(--fv-safe-t\) \+ 10px\) calc\(12px \+ var\(--fv-safe-r\)\)/);
  assert.match(sheet, /\.nav \{[^}]*padding: 6px calc\(8px \+ var\(--fv-safe-r\)\) calc\(6px \+ var\(--fv-safe-b\)\) calc\(8px \+ var\(--fv-safe-l\)\) !important/);
  // The iPad copy's test matches this literal line, so it stays exactly as it was.
  assert.match(sheet, /html\.fv-touch\.fv-touch-barn \.sidebar \{ padding-left: 64px !important; \}/);
});

test('a select whose options arrive later is segmented, named from its label', () => {
  const doc = barnPage();
  const page = load(doc);
  const farmSize = doc.getElementById('farm-size');
  const groupNamed = () => doc.querySelectorAll('.fv-seg').find(node => node.getAttribute('aria-label') === 'New farm size');
  assert.equal(groupNamed(), undefined, 'a single placeholder option is not a segment yet');
  assert.equal(farmSize.dataset.fvSeg, undefined, 'and is not flagged, so it is checked again');

  farmSize.textContent = '';
  farmSize.append(
    el(doc, 'option', { value: '33' }, ['33 × 33']),
    el(doc, 'option', { value: '44' }, ['44 × 44']),
    el(doc, 'option', { value: '55' }, ['55 × 55']),
  );
  page.settle();
  const group = groupNamed();
  assert.ok(group, 'segmented after the options arrive');
  assert.equal(farmSize.dataset.fvSeg, '1');
  assert.deepEqual(group.childNodes.map(button => button.textContent), ['33 × 33', '44 × 44', '55 × 55']);
});

test('bare checkboxes get a 44px label; boxes already inside a label are left alone', () => {
  const doc = barnPage();
  const page = load(doc);
  const plot = doc.querySelector('input[data-plot]');
  const wrapper = plot.parentNode;
  assert.equal(wrapper.tagName, 'LABEL');
  assert.ok(wrapper.classList.contains('fv-hit'));
  assert.equal(wrapper.parentNode.tagName, 'TD', 'the wrapper stays in the table cell');
  page.settle();
  assert.equal(plot.parentNode, wrapper, 'a re-render pass does not wrap it again');

  const protect = doc.getElementById('protect-crops');
  assert.equal(protect.parentNode.classList.contains('fv-hit'), false);
  assert.ok(protect.parentNode.classList.contains('checkbox-label'));

  let toggles = 0;
  plot.addEventListener('click', () => { toggles += 1; });
  wrapper.parentNode.click();
  assert.equal(toggles, 1, 'tapping the cell still toggles its box once');
});

test('the script installs once, and touches nothing off the God Barn routes', () => {
  const doc = barnPage();
  const page = load(doc);
  page.run();
  assert.equal(page.window.__fvGodBarnTouch, true);
  assert.equal(doc.all().filter(node => node.getAttribute('id') === 'farmvillage-godbarn-touch').length, 1, 'one stylesheet');
  assert.equal(doc.documentElement.classList.contains('fv-touch-barn'), true);

  for (const pathname of ['/ruffle.html', '/', '/server-login', '/god-barnyard']) {
    const untouchable = new Proxy({}, {
      get(_, property) {
        if (property === 'currentScript') return null;
        throw new Error(`touched the document on ${pathname}`);
      },
    });
    const off = load(untouchable, pathname);
    assert.equal(off.window.__fvGodBarnTouch, undefined, pathname);
  }
});
