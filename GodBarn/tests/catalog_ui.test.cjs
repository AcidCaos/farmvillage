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

const exact = {name: 'tree_cherry_pink', code: 'T42', displayName: 'Pink Cherry', type: 'tree',
  subtype: 'fruit', labelSource: 'localization', grantable: true,
  image: '/static/assets/items/pink.png',
  artwork: {status: 'exact', logical: 'trees/pink_cherry_icon.png', role: 'icon', sha256: 'a'.repeat(64)}};
const missing = {name: 'untranslated_internal_id', code: 'D99', displayName: 'Untranslated Internal Id',
  type: 'decoration', subtype: 'rare', labelSource: 'internal-name', grantable: false,
  image: '/static/assets/ui/cow.png', hasOriginalThumbnail: true,
  artwork: {status: 'missing', reason: 'Exact archive reference was not found.'}};
const fixture = {items: [exact, missing], total: 2, page: 1, pages: 1,
  types: Array.from({length: 27}, (_, index) => ({type: 'category_' + index, count: index + 1})),
  subtypes: [{subtype: 'fruit', count: 1}, {subtype: 'rare', count: 1}],
  coverage: {total: 111206, exactArt: 40000, missingArt: 71206, localizedNames: 50000},
  resultCoverage: {total: 2, exactArt: 1, missingArt: 1}};

test('archive requests start with every record and every category available', async () => {
  const h = harness();
  h.context.fixture = fixture;
  await h.run(`page='archive';api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  const params = new URL(h.context.requested, 'http://local').searchParams;
  assert.equal(params.get('grantable'), '0');
  assert.equal(params.has('collection'), false);
  assert.equal(params.get('artwork'), 'all');
  const markup = h.nodes.get('page-content').innerHTML;
  assert.match(markup, /Every category \(27\)/);
  assert.match(markup, /value="category_26"/);
  assert.match(markup, /value="rare"/);
  assert.match(markup, /111,206/);
  assert.match(markup, /1 with artwork · 1 without artwork/);
  assert.match(markup, /data-collection="" aria-pressed="true"/);
});

test('discovery controls and an explicit shelf reach the API together', async () => {
  const h = harness();
  h.context.fixture = fixture;
  await h.run(`page='archive';catalogType='decoration';catalogSubtype='rare';catalogArtwork='missing';
    catalogSort='code';catalogCollection='winter-2010';catalogPage=3;grantableOnly=true;
    api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  const params = new URL(h.context.requested, 'http://local').searchParams;
  for (const [key, value] of Object.entries({type: 'decoration', subtype: 'rare', artwork: 'missing',
    sort: 'code', collection: 'winter-2010', page: '3', grantable: '1'})) {
    assert.equal(params.get(key), value);
  }
  assert.equal(h.run('catalogPage'), 1, 'server page clamping must update navigation state');
});

test('reset clears every discovery constraint, including hidden date and shelf filters', async () => {
  const h = harness();
  h.context.fixture = fixture;
  await h.run(`page='archive';catalogQuery='cherry';catalogType='seed';catalogSubtype='rare';
    catalogArtwork='exact';catalogSort='name-desc';catalogCollection='winter-2010';catalogPage=5;
    grantableOnly=true;favoritesOnly=true;seasonalFilter='in';calendarDate='2026-12-25';
    historyYear='2010';historyAcquisition='Market';resetCatalogFilters();
    api=async path=>{globalThis.requested=path;return fixture;};loadCatalog();`);
  const params = new URL(h.context.requested, 'http://local').searchParams;
  assert.equal(params.get('q'), '');
  assert.equal(params.get('type'), '');
  assert.equal(params.get('subtype'), '');
  assert.equal(params.get('artwork'), 'all');
  assert.equal(params.get('sort'), 'recommended');
  assert.equal(params.get('grantable'), '0');
  for (const key of ['collection', 'seasonal', 'calendarDate', 'year', 'acquisition', 'names']) {
    assert.equal(params.has(key), false, key);
  }
});

test('missing art cannot use a stale category illustration or original-art flag', () => {
  const h = harness();
  h.context.record = missing;
  const markup = h.run('catalogImage(record)');
  assert.match(markup, /\/god-barn\/static\/assets\/ui\/missing-art.svg/);
  assert.doesNotMatch(markup, /cow.png/);
  assert.match(h.run('artworkStatus(record)'), /Image unavailable/);
  assert.match(h.run('labelStatus(record)'), /Name unavailable/);
  assert.equal(h.run('displayName(record)'), 'Unnamed decoration');
  assert.equal(h.run("labelSourceName({labelSource:'historical-source'})"), 'Historical name');
});

test('zero-result facets retain the selected category and subtype visibly', () => {
  const h = harness();
  const markup = h.run(`catalog={types:[],subtypes:[]};catalogType='animal';catalogSubtype='dragon';catalogFilters()`);
  assert.match(markup, /value="animal" selected>Animals · 0/);
  assert.match(markup, /value="dragon" selected>Dragon · 0/);
});

test('cards preserve escaped identifiers for actions while showing only player-facing names', () => {
  const h = harness();
  h.context.fixture = {...fixture, items: [{...exact, name: 'tree<original>', code: 'A"&42'}]};
  const markup = h.run('catalog=fixture;catalogCards()');
  assert.match(markup, /tree&lt;original&gt;/);
  assert.doesNotMatch(markup, /A&quot;&amp;42|item-identity|item-code/);
  assert.match(markup, /\/god-barn\/static\/assets\/items\/pink.png/);
  assert.doesNotMatch(markup, /data-artwork-status|Original picture/);
  assert.match(markup, /aria-label="View Pink Cherry"/);
  assert.doesNotMatch(markup, /<original>/);
});

test('picture information stays optional and excludes asset paths and hashes', () => {
  const h = harness();
  h.context.record = exact;
  const markup = h.run('artworkProvenance(record)');
  assert.match(markup, /^<details/);
  assert.match(markup, /About this picture/);
  assert.doesNotMatch(markup, /trees\/pink_cherry_icon.png|Asset role|SHA-256/);
  assert.doesNotMatch(markup, new RegExp('a'.repeat(64)));
});

test('failed image loads become an honest neutral state and retry only once', () => {
  const h = harness();
  const status = {textContent: '', classList: {add() {}}};
  const container = {classList: {add() {}}, querySelector() { return status; }};
  const image = {tagName: 'IMG', dataset: {}, src: exact.image, alt: '',
    hasAttribute(name) { return name === 'data-catalog-image'; }, closest() { return container; }};
  h.listeners.get('error')[0]({target: image});
  assert.equal(image.src, '/god-barn/static/assets/ui/missing-art.svg');
  assert.equal(status.textContent, 'Image failed to load');
  assert.match(image.alt, /could not be loaded/);
  image.src = 'unchanged-on-second-error';
  h.listeners.get('error')[0]({target: image});
  assert.equal(image.src, 'unchanged-on-second-error');
});

test('recorded coin and Farm Cash prices use original currency art, including totals and zero offers', () => {
  const h = harness();
  h.context.record = {archive: {price: {recorded: true, offers: [
    {amount: 475, currency: 'coins'}, {amount: 7, currency: 'cash'}]}}};
  const markup = h.run('priceMarkup(record,3)');
  assert.match(markup, /coin.png" alt="Farm Coins"/);
  assert.match(markup, /cash.png" alt="Farm Cash"/);
  assert.match(markup, /1,425/);
  assert.match(markup, /21/);
  assert.doesNotMatch(markup, /\$|\bFC\b/);
  h.context.record = {archive: {price: {recorded: true, amount: 0, currency: 'coins'}}};
  assert.match(h.run('priceMarkup(record)'), />0<\/span>/);
});

test('unknown prices stay unknown and special currencies do not borrow a Farm Coins icon', () => {
  const h = harness();
  assert.equal(h.run("priceMarkup({archive:{price:{recorded:false}}})"), '<p class="archive-price price-unknown">Price not recorded</p>');
  const markup = h.run("priceMarkup({archive:{price:{recorded:true,amount:50,currency:'villageCoins'}}})");
  assert.match(markup, /Village Coins/);
  assert.doesNotMatch(markup, /coin.png|cash.png|Farm Coins/);
});

test('item modal leads with the original picture, useful stats and gifting controls with history collapsed', () => {
  const h = harness();
  h.context.record = {...exact, coinYield: 47, growTime: 1, requiredLevel: 4,
    archive: {price: {recorded: true, amount: 475, currency: 'coins'}}};
  h.run('showItem(record)');
  const markup = h.nodes.get('overlay').innerHTML;
  assert.match(markup, /item-showcase-art/);
  assert.match(markup, /item-stat-tiles/);
  assert.match(markup, /Harvest every/);
  assert.match(markup, /id="grant-form"/);
  assert.match(markup, /<details class="item-history">/);
  assert.doesNotMatch(markup, /Original item ID|Item code|Display label|Asset role|SHA-256|Local image/);
  assert.match(h.run("itemStatTiles({...record,type:'seed'})"), /Grows in/);
  h.context.fixture = fixture;
  assert.match(h.run('catalog=fixture;catalogCoverage()'), /^<details/);
  assert.doesNotMatch(h.run('catalogCoverage()'), /<details[^>]* open/);
});

test('catalog cards are not buttons: the title is the one real control and the favourite star stays separate', () => {
  const h = harness();
  h.context.fixture = fixture;
  const markup = h.run('catalog=fixture;catalogCards()');
  assert.doesNotMatch(markup, /<article[^>]*role="button"/);
  assert.doesNotMatch(markup, /<article[^>]*tabindex=/);
  assert.match(markup, /<article class="item-card " data-item="tree_cherry_pink" data-artwork-container>/);
  assert.match(markup, /<button type="button" class="item-open" data-item="tree_cherry_pink" aria-label="View Pink Cherry">Pink Cherry<\/button>/);
  assert.match(markup, /<button class="fav[^"]*" data-favorite="tree_cherry_pink"/);
  assert.doesNotMatch(markup, /class="item-open"[^>]*>(?:(?!<\/button>)[\s\S])*<button/);
});

test('the card title and the card body open the same item, while the star only changes the favourite', async () => {
  const h = harness();
  h.context.fixture = fixture;
  h.run('catalog=fixture;');
  const dispatch = target => h.listeners.get('click')[0]({target, preventDefault() {}, stopPropagation() {}});
  const card = {dataset: {item: 'tree_cherry_pink'}};
  const title = {dataset: {item: 'tree_cherry_pink'},
    closest: selector => (selector === 'button,a[data-action]' || selector === '[data-item]' ? title : null)};
  const body = {dataset: {}, closest: selector => (selector === '[data-item]' ? card : null)};
  const star = {dataset: {favorite: 'tree_cherry_pink'}, closest: selector => (selector === 'button,a[data-action]' ? star : null)};
  await dispatch(title);
  assert.match(h.nodes.get('overlay').innerHTML, /item-showcase-art/);
  assert.equal(h.run('app.inert'), true);
  h.run('closeModal()');
  await dispatch(body);
  assert.match(h.nodes.get('overlay').innerHTML, /item-showcase-art/);
  h.run('closeModal()');
  await dispatch(star);
  assert.equal(h.nodes.get('overlay').innerHTML, '');
  assert.equal(h.run("favorites.has('tree_cherry_pink')"), true);
});

test('an open sheet makes the page behind it inert and returns focus to the opener after it closes', () => {
  const h = harness();
  h.run('globalThis.focusedWhileInert=null;document.activeElement={focus(){globalThis.focusedWhileInert=app.inert;}};');
  h.run("showModal('<p>Sheet</p>')");
  assert.equal(h.nodes.get('app').inert, true);
  assert.match(h.nodes.get('overlay').innerHTML, /Sheet/);
  h.run('closeModal()');
  assert.equal(h.nodes.get('app').inert, false);
  assert.equal(h.nodes.get('overlay').innerHTML, '');
  assert.equal(h.run('focusedWhileInert'), false, 'focus must return only after the page is interactive again');
});
