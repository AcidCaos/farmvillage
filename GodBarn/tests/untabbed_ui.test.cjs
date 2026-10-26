const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8')
  .replace(/try\{await refresh\(\);\}catch\(error\)\{app.innerHTML=errorBoot\(error\);\}\s*$/, '');

function harness() {
  const listeners = new Map();
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {id, innerHTML: '', children: [], style: {},
      addEventListener() {}, querySelector() { return null; }});
    return nodes.get(id);
  };
  const context = vm.createContext({
    location: {pathname: '/god-barn'}, URL, URLSearchParams,
    localStorage: {getItem() { return '[]'; }, setItem() {}},
    document: {getElementById: node, activeElement: null, body: {style: {}},
      addEventListener(type, listener) {
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(listener);
      }},
    window: {addEventListener() {}, scrollTo() {}},
    setInterval() {}, clearTimeout() {}, setTimeout() {},
  });
  vm.runInContext(source, context, {filename: 'app.js'});
  return {context, run: code => vm.runInContext(code, context), nodes, listeners};
}

const heritageItem = {name: 'ghostcow', code: 'GC', displayName: 'Ghost Cow', type: 'animal', subtype: 'animal',
  grantable: true, labelSource: 'localization', hasOriginalThumbnail: true, image: '/static/assets/items/cow.png',
  artwork: {status: 'exact', logical: 'animals/cow.png', sha256: 'a'.repeat(64)},
  archive: {price: {recorded: false, label: 'Price not recorded'}},
  untabbed: {origin: 'heritage', label: 'Heritage – no market tab', worlds: ['avalon'],
    home: {currency: 'coins', amount: 2400}, recordedForSale: false, giftRefusal: null}};
// Grantable as a flag, but the barn refuses it, so the gift form must stay hidden.
const refusedItem = {name: 'pillbox', code: 'PL', displayName: 'Pill Box', type: 'consumable', subtype: 'supply',
  grantable: true, labelSource: 'localization', hasOriginalThumbnail: false, image: '/static/assets/ui/missing-art.svg',
  artwork: {status: 'missing'}, archive: {price: {recorded: false, label: 'Price not recorded'}},
  untabbed: {origin: 'other', label: 'Other – no market tab', worlds: [], home: null, recordedForSale: true,
    giftRefusal: 'Category "consumable" is not supported for gifts yet.'}};
const summary = {total: 2, giftable: 1, refused: 1, generated: true,
  origins: {heritage: {label: 'Heritage – no market tab', total: 1, giftable: 1},
    exclusive: {label: 'Original exclusive – no market tab', total: 0, giftable: 0},
    other: {label: 'Other – no market tab', total: 1, giftable: 0}},
  refusals: [{reason: 'Category "consumable" is not supported for gifts yet.', count: 1}]};
const untabbedFixture = {items: [heritageItem, refusedItem], total: 2, page: 1, pages: 1, limit: 20,
  types: [{type: 'animal', count: 1}, {type: 'consumable', count: 1}], subtypes: [],
  coverage: {total: 2, exactArt: 1, missingArt: 1}, resultCoverage: {total: 2, exactArt: 1, missingArt: 1},
  untabbed: {origin: '', gift: 'giftable', summary}};
const archiveItem = {name: 'tractor', code: 'T1', displayName: 'Old Red Tractor', type: 'vehicle', subtype: 'tractor',
  grantable: true, labelSource: 'localization', hasOriginalThumbnail: true, image: '/static/assets/items/tractor.png',
  artwork: {status: 'exact', logical: 'vehicles/tractor.png', sha256: 'b'.repeat(64)},
  archive: {price: {recorded: false, label: 'Price not recorded'}}};
const catalogFixture = {items: [archiveItem], total: 1, page: 1, pages: 1, limit: 20, types: [], subtypes: [],
  coverage: {total: 1, exactArt: 1, missingArt: 0}, resultCoverage: {total: 1, exactArt: 1, missingArt: 0}};

test('Not in Market requests the untabbed endpoint with giftable rows by default', async () => {
  const h = harness();
  h.context.fixture = untabbedFixture;
  await h.run(`page='untabbed';api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  const url = new URL(h.context.requested, 'http://local');
  assert.equal(url.pathname, '/api/untabbed');
  assert.equal(url.searchParams.get('origin'), '');
  assert.equal(url.searchParams.get('gift'), 'giftable');
  assert.equal(url.searchParams.has('seasonal'), false);
  assert.equal(url.searchParams.has('grantable'), true);
  assert.equal(url.searchParams.get('grantable'), '0');
});

test('the untabbed page labels subgroups with counts, reasons, sale and price context', async () => {
  const h = harness();
  h.context.fixture = untabbedFixture;
  await h.run(`page='untabbed';api=async path=>fixture;loadCatalog();`);
  const markup = h.nodes.get('page-content').innerHTML;
  assert.match(markup, /Items the Market never shows/);
  assert.match(markup, /Heritage – no market tab <span>\(1\)<\/span>/);
  assert.match(markup, /Other – no market tab <span>\(1\)<\/span>/);
  assert.match(markup, /1 giftable here · 1 not giftable/);
  assert.match(markup, /Locked to Avalon/);
  assert.match(markup, /Home farm price/);
  assert.match(markup, /Recorded for sale/);
  assert.match(markup, /Category &quot;consumable&quot; is not supported for gifts yet\./);
  assert.match(markup, /Add to gifts \+/);
  assert.match(markup, /View details →/);
});

test('origin chips and the refusal toggle reach the endpoint and keep the page state', async () => {
  const h = harness();
  h.context.fixture = untabbedFixture;
  await h.run(`page='untabbed';api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  const dispatch = target => h.listeners.get('click')[0]({target, preventDefault() {}, stopPropagation() {}});
  const chip = {dataset: {untabbedOrigin: 'heritage'},
    closest: selector => (selector === 'button,a[data-action]' ? chip : null)};
  await dispatch(chip);
  let url = new URL(h.context.requested, 'http://local');
  assert.equal(url.searchParams.get('origin'), 'heritage');
  assert.equal(url.searchParams.get('gift'), 'giftable');
  assert.equal(h.run('untabbedOrigin'), 'heritage');
  const toggle = {id: 'untabbed-refused', checked: true};
  for (const listener of h.listeners.get('change')) await listener({target: toggle});
  url = new URL(h.context.requested, 'http://local');
  assert.equal(url.searchParams.get('gift'), 'all');
  assert.equal(url.searchParams.get('origin'), 'heritage');
  assert.equal(h.run('untabbedShowRefused'), true);
  h.run('resetCatalogFilters()');
  assert.equal(h.run('untabbedOrigin'), '');
  assert.equal(h.run('untabbedShowRefused'), false);
});

test('an item the barn cannot gift shows its reason and no gift form, even when flagged grantable', () => {
  const h = harness();
  h.context.refusedItem = refusedItem;
  h.run('showItem(refusedItem)');
  const overlayMarkup = h.nodes.get('overlay').innerHTML;
  assert.doesNotMatch(overlayMarkup, /id="grant-form"/);
  assert.match(overlayMarkup, /Category &quot;consumable&quot; is not supported for gifts yet\./);
});

test('a heritage item keeps its gift form and shows its Home price in the dialog', () => {
  const h = harness();
  h.context.heritageItem = heritageItem;
  h.run('showItem(heritageItem)');
  const overlayMarkup = h.nodes.get('overlay').innerHTML;
  assert.match(overlayMarkup, /id="grant-form"/);
  assert.match(overlayMarkup, /Home farm price/);
  assert.match(overlayMarkup, /Heritage – no market tab/);
});

test('ordinary archive pages keep their endpoint, filters and gift label', async () => {
  const h = harness();
  h.context.fixture = catalogFixture;
  await h.run(`page='catalog';api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  assert.match(h.context.requested, /^\/api\/catalog\?/);
  const params = new URL(h.context.requested, 'http://local').searchParams;
  assert.equal(params.has('origin'), false);
  assert.equal(params.has('gift'), false);
  const markup = h.nodes.get('page-content').innerHTML;
  assert.match(markup, /Add to gifts \+/);
  assert.doesNotMatch(markup, /untabbed-tags/);
});
