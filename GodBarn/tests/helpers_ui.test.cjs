const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8')
  .replace(/try\{await refresh\(\);\}catch\(error\)\{app.innerHTML=errorBoot\(error\);\}\s*$/, '');

function harness() {
  const listeners = new Map(), nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {id, innerHTML: '', children: [], style: {},
      classList: {add() {}, remove() {}}, focus() {}, querySelector() { return null; }, addEventListener() {}});
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
  const run = code => vm.runInContext(code, context);
  run("state={farm:{id:'farm-a',revision:'r1',name:'Practice',save:{},summary:{}},farms:[]};");
  const click = dataset => listeners.get('click')[0]({target: {closest(selector) {
    return selector === 'button,a[data-action]' ? {dataset} : null;
  }}});
  const change = target => listeners.get('change')[0]({target});
  return {context, run, nodes, click, change};
}

const collection = {id: 'treasures', name: 'treasures', displayName: 'Farm Treasures',
  kind: 'collection', missing: 4, total: 6, itemCount: 3, completed: false, supported: true,
  items: [
    {name: 'button', displayName: 'A Blue Button', count: 1, required: 3, missing: 2, completed: false},
    {name: 'feather', displayName: 'Feather', count: 0, required: 2, missing: 2, completed: false},
    {name: 'needle', displayName: 'Needle', count: 5, required: 1, missing: 0, completed: true},
  ]};
const quest = {id: 'spring', name: 'spring', displayName: 'A Fresh Start', kind: 'quest',
  description: 'A little work in the garden.', completed: false, supported: true, tasks: [
    {id: 0, index: 0, displayName: 'Harvest strawberries', count: 4, required: 10,
      remaining: 6, completed: false, supported: true},
    {id: 1, index: 1, displayName: 'Help a neighbour', count: 0, required: 1,
      remaining: 1, completed: false, supported: false, reason: 'Saved progress cannot be controlled.'},
    {id: 2, index: 2, displayName: 'Buy a tree', count: 1, required: 1,
      remaining: 0, completed: true, supported: true},
  ]};
const page = items => ({items, available: true, totals: {incomplete: 1, complete: 0},
  total: items.length, page: 1, pages: 1});

test('collections show rarity requirements, missing pieces, and held progress without counting surplus', () => {
  const h = harness();
  h.context.fixture = collection;
  const markup = h.run('collectionHelperCard(fixture)');
  assert.match(markup, /4 missing/);
  assert.match(markup, /2 \/ 6 pieces held · 1 of 3 items complete/);
  assert.match(markup, /2 missing · 1 \/ 3 held/);
  assert.match(markup, /Held · 5 in your collection/);
  assert.match(markup, /data-fill-collection="treasures"/);
  assert.match(markup, /Preview filling 4 missing/);
  h.context.fixture = {...collection, completed: true, missing: 0};
  assert.doesNotMatch(h.run('collectionHelperCard(fixture)'), /data-fill-collection/);
  h.context.fixture = {...collection, completed: true, stored: true};
  const stored = h.run('collectionHelperCard(fixture)');
  assert.match(stored, /Already traded in/);
  assert.doesNotMatch(stored, /Every collectible is here|data-fill-collection/);
});

test('quest task controls describe needs and leave unsupported and completed tasks read only', () => {
  const h = harness();
  h.context.fixture = quest;
  const markup = h.run('questHelperCard(fixture)');
  assert.match(markup, /4 \/ 10/);
  assert.match(markup, /6 still needed/);
  assert.match(markup, /data-finish-quest="spring" data-quest-task="0"/);
  assert.doesNotMatch(markup, /data-quest-task="[12]"/);
  assert.match(markup, /Complete this task in the game/);
  assert.match(markup, /Requirement met/);
  h.context.fixture = {...quest, completed: true};
  assert.match(h.run('questHelperCard(fixture)'), /Return to the game to claim this quest and its rewards/);
  h.context.fixture = {...quest, tasks: [], supported: false};
  assert.match(h.run('questHelperCard(fixture)'), /Details unavailable/);
});

test('helper labels, descriptions, identifiers, and server errors are escaped', () => {
  const h = harness();
  h.context.fixture = {...collection, id: 'set" onfocus="bad', displayName: '<script>bad</script>',
    reason: '<img src=x>', items: [{displayName: '<svg>', required: 1, count: 0, missing: 1}]};
  const markup = h.run('collectionHelperCard(fixture)');
  assert.match(markup, /&lt;script&gt;bad&lt;\/script&gt;/);
  assert.match(markup, /set&quot; onfocus=&quot;bad/);
  assert.match(markup, /&lt;svg&gt;/);
  assert.doesNotMatch(markup, /<script>|<svg>|<img src=x>/);
  const error = h.run("helperData.quest={error:'<iframe>lost</iframe>',loading:false};helpersPage('quest')");
  assert.match(error, /role="alert"/);
  assert.match(error, /&lt;iframe&gt;lost&lt;\/iframe&gt;/);
  assert.match(error, /data-action="helper-retry"/);
});

test('collection and quest buttons create only the selected preview operation', async () => {
  const h = harness();
  h.context.collectionFixture = collection;
  h.context.questFixture = quest;
  h.run('helperData.collection={items:[collectionFixture]};helperData.quest={items:[questFixture]};preview=async operation=>{globalThis.operation=operation;};');
  await h.click({fillCollection: 'treasures'});
  assert.equal(JSON.stringify(h.context.operation), JSON.stringify({type: 'collection', name: 'treasures', action: 'fill'}));
  await h.click({finishQuest: 'spring', questTask: '0'});
  assert.equal(JSON.stringify(h.context.operation), JSON.stringify({type: 'quest', name: 'spring', task: 0}));
  h.run('globalThis.operation=null;');
  await h.click({finishQuest: 'spring', questTask: '1'});
  await h.click({finishQuest: 'spring', questTask: '2'});
  assert.equal(h.context.operation, null);
});

test('helpers send independent search, status and page filters and honor server page clamping', async () => {
  const h = harness();
  h.context.fixture = page([collection]);
  await h.run("helperFilters.collection={query:'blue button',status:'incomplete',page:3};api=async path=>{globalThis.requested=path;return fixture;};loadHelpers('collection',false);");
  const params = new URL(h.context.requested, 'http://local').searchParams;
  for (const [key, value] of Object.entries({kind: 'collection', q: 'blue button', status: 'incomplete', page: '3', limit: '12'})) {
    assert.equal(params.get(key), value);
  }
  assert.equal(h.run('helperFilters.collection.page'), 1);
  assert.equal(h.run('helperFilters.quest.query'), '');
});

test('late responses cannot replace a new farm, revision, or newer search result', async () => {
  for (const change of ["state.farm.id='farm-b'", "state.farm.revision='r2'", 'invalidateFarmTools()']) {
    const h = harness();
    h.context.fixture = page([collection]);
    const pending = h.run("api=()=>new Promise(resolve=>globalThis.resolve=resolve);loadHelpers('collection',false)");
    h.run(change);
    h.context.resolve(h.context.fixture);
    await pending;
    assert.notEqual(h.run('helperData.collection?.items?.[0]?.id'), 'treasures');
  }
  const h = harness();
  h.context.older = page([collection]);
  h.context.newer = page([{...collection, id: 'new-search'}]);
  const first = h.run("globalThis.pending=[];api=()=>new Promise(resolve=>pending.push(resolve));loadHelpers('collection',false)");
  const second = h.run("helperFilters.collection.query='new';loadHelpers('collection',false)");
  h.run('pending[1](newer)');
  await second;
  h.run('pending[0](older)');
  await first;
  assert.equal(h.run('helperData.collection.items[0].id'), 'new-search');
});

test('a failed read can retry, and an empty farm is distinct from a filtered result', async () => {
  const h = harness();
  await h.run("api=async()=>{throw new Error('Definitions not ready');};loadHelpers('quest',false)");
  assert.match(h.run("helpersPage('quest')"), /Definitions not ready/);
  h.context.fixture = page([]);
  await h.run("api=async()=>fixture;loadHelpers('quest',false)");
  assert.match(h.run("helpersPage('quest')"), /No active quests on record/);
  assert.doesNotMatch(h.run("helpersPage('quest')"), /Definitions not ready/);
  assert.match(h.run("helperFilters.quest.query='missing';helpersPage('quest')"), /No matching quests/);
  assert.match(h.run("helpersPage('quest')"), /data-action="helper-reset"/);
  const malformed = h.run("helperData.quest={items:[],available:true,reason:'Saved questState is malformed.'};helpersPage('quest')");
  assert.match(malformed, /Saved quests need attention/);
  assert.match(malformed, /Saved questState is malformed/);
  assert.doesNotMatch(malformed, /No active quests on record|No matching quests/);
  assert.doesNotMatch(h.run("helpersPage('collection')"), /Trade it in/);
});

test('preview waits for the shared review sheet and ignores a changed farm', async () => {
  const h = harness();
  h.context.fixture = {token: 'preview-token', summary: 'Fill Farm Treasures', changes: [{path: '/collections/treasures', before: 0, after: 1}]};
  await h.run("api=async()=>fixture;preview({type:'collection',name:'treasures',action:'fill'})");
  assert.match(h.nodes.get('overlay').innerHTML, /Before the magic happens/);
  assert.match(h.nodes.get('overlay').innerHTML, /A snapshot is saved before applying/);
  assert.match(h.nodes.get('overlay').innerHTML, /data-action="apply-preview"/);
  h.run('closeModal()');
  const pending = h.run("api=()=>new Promise(resolve=>globalThis.resolve=resolve);preview({type:'quest',name:'spring',task:0})");
  h.run("state.farm.id='farm-b'");
  h.context.resolve(h.context.fixture);
  await pending;
  assert.equal(h.nodes.get('overlay').innerHTML, '');
  assert.equal(h.run('lastPreview'), null);
});

test('farm selection is blocked while an apply is pending and recovers after it finishes', async () => {
  const h = harness();
  h.context.saved = {farm: {id: 'farm-a', revision: 'r2', name: 'Practice', save: {}, summary: {}}, farms: []};
  const apply = h.run("lastPreview={token:'apply-token'};globalThis.requests=[];api=(path,data)=>{requests.push(path);return new Promise(resolve=>globalThis.resolveApply=resolve);};applyPreview()");
  const picker = {id: 'farm-picker', value: 'farm-b', disabled: false};
  await h.change(picker);
  assert.equal(picker.value, 'farm-a');
  assert.equal(h.run('state.farm.id'), 'farm-a');
  assert.equal(h.run('requests.length'), 1);
  assert.match(h.nodes.get('toast').textContent, /Please wait/);
  h.run('resolveApply(saved)');
  await apply;
  assert.equal(h.run('busy'), false);
  h.context.selected = {farm: {id: 'farm-b', revision: 'b1', name: 'Second farm', save: {}, summary: {}}, farms: []};
  h.run('api=async path=>{requests.push(path);return selected;};');
  picker.value = 'farm-b';
  await h.change(picker);
  assert.equal(h.run('state.farm.id'), 'farm-b');
  assert.equal(picker.value, 'farm-b');
  assert.equal(h.run('requests[1]'), '/api/select');
  assert.equal(h.run('busy'), false);
});

test('farm selection stages crop data before rendering and blocks helper reads during the transition', async () => {
  const h = harness();
  h.context.selected = {farm: {id: 'farm-b', revision: 'b1', name: 'Second farm', save: {}, summary: {}}, farms: []};
  h.context.picker = {id: 'farm-picker', value: 'farm-b', disabled: false};
  h.run("cropItems=new Map([['old',{name:'old'}]]);globalThis.renders=[];render=()=>renders.push([state.farm.id,[...cropItems.keys()]]);api=async()=>selected;cropItemsForFarm=()=>new Promise(resolve=>globalThis.resolveCrops=resolve);");
  const selection = h.run('selectFarm(picker)');
  await Promise.resolve();
  assert.equal(h.run('state.farm.id'), 'farm-a');
  assert.equal(h.run('picker.value'), 'farm-a');
  assert.equal(h.run('busy'), true);
  assert.equal(h.run('renders.length'), 0);
  await h.run("loadHelpers('collection',false)");
  assert.equal(h.run('helperData.collection'), null);
  h.run("resolveCrops(new Map([['new',{name:'new'}]]))");
  await selection;
  assert.equal(h.run('state.farm.id'), 'farm-b');
  assert.equal(h.run('JSON.stringify(renders)'), JSON.stringify([['farm-b', ['new']]]));
  assert.equal(h.run('picker.disabled'), false);
  assert.equal(h.run('farmSelectionPending'), false);
});

test('failed selection restores the picker and releases its lock', async () => {
  const h = harness();
  const picker = {id: 'farm-picker', value: 'farm-b', disabled: false};
  h.run("api=async()=>{throw new Error('Farm could not be opened');}");
  await h.change(picker);
  assert.equal(picker.value, 'farm-a');
  assert.equal(picker.disabled, false);
  assert.equal(h.run('state.farm.id'), 'farm-a');
  assert.equal(h.run('busy'), false);
  assert.match(h.nodes.get('toast').textContent, /Farm could not be opened/);
});

test('a crop lookup failure keeps a successful farm selection consistent and clears prior artwork', async () => {
  const h = harness();
  const picker = {id: 'farm-picker', value: 'farm-b', disabled: false};
  h.context.selected = {farm: {id: 'farm-b', revision: 'b1', name: 'Second farm', save: {}, summary: {}}, farms: []};
  h.run("cropItems=new Map([['old',{name:'old'}]]);api=async()=>selected;cropItemsForFarm=async()=>{throw new Error('Crop records unavailable');};");
  await h.change(picker);
  assert.equal(h.run('state.farm.id'), 'farm-b');
  assert.equal(h.run('cropItems.size'), 0);
  assert.equal(picker.value, 'farm-b');
  assert.equal(picker.disabled, false);
  assert.equal(h.run('busy'), false);
  assert.match(h.nodes.get('toast').textContent, /Crop records unavailable/);
});

test('helper search keeps focus even when selection APIs are absent or unsupported', () => {
  const h = harness();
  h.run("page='collections';document.activeElement={id:'helper-search',selectionStart:2};");
  h.run('renderHelpers()');
  const search = h.nodes.get('helper-search');
  search.setSelectionRange = () => { throw new Error('Selection is unsupported'); };
  assert.doesNotThrow(() => h.run('renderHelpers()'));
});

test('summary counts separate supported missing sets from read-only definitions', () => {
  const h = harness();
  const markup = h.run("helperData.collection={items:[],totals:{incomplete:81,complete:2,unsupported:48,supportedIncomplete:35},available:true};helpersPage('collection')");
  assert.match(markup, /35<\/b> sets need pieces/);
  assert.match(markup, /48<\/b> read only/);
  assert.match(markup, /2<\/b> sets complete/);
  assert.doesNotMatch(markup, /81<\/b> sets need pieces/);
});

test('collection pieces and quest portraits use their recovered pictures without catalog artwork flags', () => {
  const h = harness();
  h.context.collectionArt = {...collection, image: '/static/assets/helper-art/treasures.png',
    items: collection.items.map(item => ({...item, image: '/static/assets/helper-art/' + item.name + '.png'}))};
  h.context.questArt = {...quest, image: '/static/assets/helper-art/farmer.png',
    tasks: quest.tasks.map(task => ({...task, image: '/static/assets/items/strawberry.png'}))};
  const setMarkup = h.run('collectionHelperCard(collectionArt)');
  assert.match(setMarkup, /\/god-barn\/static\/assets\/helper-art\/treasures.png/);
  assert.match(setMarkup, /\/god-barn\/static\/assets\/helper-art\/button.png/);
  assert.doesNotMatch(setMarkup, /collections.png|helper-identity/);
  const questMarkup = h.run('questHelperCard(questArt)');
  assert.match(questMarkup, /\/god-barn\/static\/assets\/helper-art\/farmer.png/);
  assert.match(questMarkup, /\/god-barn\/static\/assets\/items\/strawberry.png/);
  assert.doesNotMatch(questMarkup, /helper-identity/);
});

test('one Collectibles tab switches between collections, mastery and ribbons with independent searches', async () => {
  const h = harness();
  assert.equal(h.run("nav.filter(row=>row[2]==='Collectibles').length"), 1);
  assert.equal(h.run("nav.some(row=>row[2]==='Collections'||row[2]==='Stars & ribbons')"), false);
  h.run('globalThis.loads=[];loadHelpers=async kind=>loads.push(kind);loadProgression=async()=>loads.push(progressionKind);');
  await h.run("selectCollectibleView('mastery')");
  assert.equal(h.run('page'), 'collectibles');
  assert.equal(h.run('isProgressionPage()'), true);
  h.run("progressionQuery='strawberries'");
  await h.run("selectCollectibleView('ribbon')");
  assert.equal(h.run('progressionQuery'), '');
  await h.run("selectCollectibleView('mastery')");
  assert.equal(h.run('progressionQuery'), 'strawberries');
  await h.run("selectCollectibleView('collection')");
  assert.equal(h.run('helperKind()'), 'collection');
  assert.equal(h.run('isProgressionPage()'), false);
  assert.equal(h.run('JSON.stringify(loads)'), JSON.stringify(['mastery', 'ribbon', 'mastery', 'collection']));
});

test('progression shows recovered item and colored ribbon art with reward icons while hiding internal labels', () => {
  const h = harness();
  h.context.track = {kind: 'ribbon', code: 'internal-achievement', displayName: 'Best Friends', image: '/static/assets/progression/friends.png',
    count: 4, remaining: 6, earnedTier: 1, maxTier: 2, supported: true,
    tiers: [{label: 'Yellow', count: 1, earned: true, image: '/static/assets/progression/friends-yellow.png'},
      {label: 'White', count: 10, earned: false, image: '/static/assets/progression/friends-white.png'}],
    nextTier: {label: 'White', count: 10, coins: 50, xp: 5, gift: 'internal-gift-code', giftImage: '/static/assets/items/reward.png'}};
  const markup = h.run('progressionCard(track)');
  assert.match(markup, /friends-yellow.png/);
  assert.match(markup, /friends-white.png/);
  assert.match(markup, /coin.png" alt="Farm Coins"/);
  assert.match(markup, /\/god-barn\/static\/assets\/items\/reward.png/);
  const text = markup.replace(/<[^>]*>/g, '');
  assert.doesNotMatch(text, /internal-achievement|internal-gift-code/);
  h.context.track = {kind: 'mastery', type: 'tree', labelSource: 'internal-name', displayName: 'bunchrosetree',
    count: 0, tiers: [], artwork: {status: 'missing'}, image: '/static/assets/ui/tree.png'};
  const missing = h.run('progressionCard(track)');
  assert.match(missing, /Unnamed tree/);
  assert.doesNotMatch(missing, /bunchrosetree|src="[^\"]*tree.png/);
});

test('preview rows use readable task and currency labels without raw JSON paths or item identifiers', () => {
  const h = harness();
  h.context.fixture = {changes: [
    {path: '/userInfo/player/gold', before: 10, after: 50},
    {path: '/userInfo/player/cash', before: 1, after: 7},
    {path: '/collectionCounters/secret-code', before: 0, after: 1},
    {path: '/questState/active/secret-quest/progress/0', before: 0, after: 1},
    {path: '/world/objectsArray/0/itemName', before: 'secret-seed', after: 'secret-new-seed'},
  ]};
  const markup = h.run('previewChanges(fixture)');
  assert.match(markup, /Farm Coins/);
  assert.match(markup, /Farm Cash/);
  assert.match(markup, /Collectibles held/);
  assert.match(markup, /Quest task progress/);
  assert.match(markup, /coin.png/);
  assert.match(markup, /cash.png/);
  assert.doesNotMatch(markup, /secret-|userInfo|collectionCounters|questState|objectsArray/);
});

test('crop tiles and achievement tiles state their status in text, not only in tooltips', () => {
  const h = harness();
  h.run("plots=()=>[{id:1,itemName:'pink',state:'grown'},{id:2,itemName:'',state:'empty'}];cropRecord=p=>({displayName:p.itemName?'Pink Cherry':'Open soil',labelSource:'localization',type:'tree'});itemImage=()=>'/static/assets/items/pink.png';stats=()=>'';summary=()=>({worldSize:{x:1}});save=()=>({world:{sizeX:1,sizeY:1}});");
  const overview = h.run('overview()');
  assert.match(overview, /<div class="mini-plot ready" title="Pink Cherry · grown"><img src="\/static\/assets\/items\/pink.png" alt=""><span class="sr-only">Pink Cherry, grown<\/span><\/div>/);
  assert.match(overview, /<div class="mini-plot " title="Open soil · empty"><span class="sr-only">Open soil, empty<\/span><\/div>/);
  h.context.row = {kind: 'ribbon', earnedTier: 1, maxTier: 2, tiers: [
    {label: 'Yellow', earned: true}, {label: 'White', earned: false}]};
  const tiers = h.run('progressionTiers(row)');
  assert.match(tiers, /class="achievement-tier earned" title="Yellow · earned"/);
  assert.match(tiers, /<i aria-hidden="true">✓<\/i><span class="sr-only">, earned<\/span>/);
  assert.match(tiers, /class="achievement-tier " title="White"/);
  assert.doesNotMatch(tiers, /aria-label="Earned"/);
});
