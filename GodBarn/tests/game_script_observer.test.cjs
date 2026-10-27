/* Run against the production _game_script supplied on stdin by test_game_script_js.py. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(0, 'utf8');
const origin = 'http://192.168.50.80:5501';
const gateway = `${origin}/flashservices/gateway.php`;
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness(fetchImpl, script = source) {
    const calls = [], focusEvents = [], created = [], timers = [], globalEvents = new Map();
    const element = tag => ({
        tag, children: [], style: {}, attributes: {},
        setAttribute(key, value) { this.attributes[key] = value; },
        append(...children) { this.children.push(...children); },
        focus() { focusEvents.push(this); },
    });
    const body = element('body');
    const find = (node, id) => node.id === id ? node : node.children.map(child => find(child, id)).find(Boolean);
    const document = {
        body,
        getElementById(id) { return find(body, id) || null; },
        createElement(tag) { const result = element(tag); created.push(result); return result; },
    };
    class FakeXHR extends EventTarget {
        constructor() { super(); this.headers = new Headers(); this.status = 200; this.responseText = ''; this.synchronous = true; }
        open(method, url, ...args) { this.openCall = [method, url, ...args]; return 'open-result'; }
        setRequestHeader(key, value) { this.headers.set(key, value); }
        getResponseHeader(key) { return key.toLowerCase() === 'content-type' ? this.contentType || 'application/x-amf' : null; }
        send(body) {
            this.sendCalls = (this.sendCalls || 0) + 1;
            this.sentBody = body;
            if (this.synchronous) this.dispatchEvent(new Event('loadend'));
            return 'send-result';
        }
    }
    const context = vm.createContext({
        URL, Request, Headers, Response, document, XMLHttpRequest: FakeXHR,
        location: new URL(origin + '/ruffle.html'),
        addEventListener(name, listener) { globalEvents.set(name, listener); },
        setTimeout(callback, delay) { assert.equal(delay, 0); timers.push(callback); return timers.length; },
        fetch(input, init) {
            calls.push({ input, init, receiver: this });
            return fetchImpl(input, init);
        },
    });
    context.window = context;
    vm.runInContext(script, context, { timeout: 1000 });
    const runTimers = () => { for (const callback of timers.splice(0)) callback(); };
    return { context, calls, focusEvents, created, document, FakeXHR, globalEvents, runTimers };
}

test('gateway fetch preserves Request, headers, response identity and unread AMF bytes with one network call', async () => {
    const bytes = new Uint8Array([0, 3, 0, 0, 0, 1, 0, 4]);
    const response = new Response(bytes, { status: 200, headers: { 'Content-Type': 'application/x-amf' } });
    let clones = 0;
    response.clone = () => { clones++; throw new Error('Successful AMF response must not be cloned.'); };
    const native = Promise.resolve(response);
    const h = harness(() => native);
    const request = new Request(gateway, { method: 'POST', body: new Uint8Array([1, 2, 3]),
        headers: { 'Content-Type': 'application/x-amf', 'X-Custom': 'keep' } });
    const pending = h.context.fetch(request);
    assert.equal(pending, native);
    const returned = await pending;
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].input, request);
    assert.equal(h.calls[0].init.headers.get('content-type'), 'application/x-amf');
    assert.equal(h.calls[0].init.headers.get('x-custom'), 'keep');
    assert.equal(h.calls[0].init.headers.get('x-god-barn-epoch'), 'observer-test-epoch');
    assert.equal(request.headers.has('x-god-barn-epoch'), false);
    assert.equal(returned, response);
    assert.equal(returned.bodyUsed, false);
    assert.equal(clones, 0);
    assert.deepEqual(new Uint8Array(await returned.arrayBuffer()), bytes);
    assert.equal(h.created.length, 0);
    assert.equal(h.focusEvents.length, 0);
});

test('explicit fetch init overrides keep normal request semantics and receive only the epoch addition', async () => {
    const response = new Response('ok');
    const h = harness(() => Promise.resolve(response));
    const request = new Request(gateway, { method: 'POST', body: 'amf', headers: { 'X-Original': 'ignored-by-init' } });
    const init = { headers: { 'Content-Type': 'application/x-amf', 'X-Override': 'yes' }, cache: 'no-store' };
    await h.context.fetch(request, init);
    assert.equal(h.calls[0].input, request);
    assert.equal(h.calls[0].init.cache, 'no-store');
    assert.equal(h.calls[0].init.headers.get('x-override'), 'yes');
    assert.equal(h.calls[0].init.headers.has('x-original'), false);
    assert.deepEqual(init, { headers: { 'Content-Type': 'application/x-amf', 'X-Override': 'yes' }, cache: 'no-store' });
});

test('assets and another origin bypass the observer and preserve the original Promise exactly', async () => {
    for (const input of ['/ruffle/core.wasm', 'https://other.example/flashservices/gateway.php']) {
        const native = Promise.resolve(new Response('asset'));
        const h = harness(() => native);
        const init = { cache: 'force-cache' };
        assert.equal(h.context.fetch(input, init), native);
        assert.equal(h.calls[0].input, input);
        assert.equal(h.calls[0].init, init);
        assert.equal(h.calls.length, 1);
        assert.equal(h.created.length, 0);
    }
});

test('fetch error inspection reads a clone, preserves the response and shows one actionable panel', async () => {
    const response = new Response(JSON.stringify({ code: 'farm_parked' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
    });
    let requestNumber = 0;
    const h = harness(() => Promise.resolve(requestNumber++ === 0 ? response : new Response(JSON.stringify({ code: 'farm_parked' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
    })));
    assert.equal(await h.context.fetch(gateway), response);
    await flush();
    assert.equal(h.document.body.children.length, 0, 'Error DOM must wait for a separate task.');
    h.runTimers();
    const panel = h.document.getElementById('farmvillage-save-interrupted');
    assert.ok(panel);
    assert.equal(panel.attributes.role, 'alertdialog');
    assert.equal(h.focusEvents.length, 1);
    assert.equal(h.focusEvents[0].href, '/god-barn/');
    assert.equal(response.bodyUsed, false);
    assert.equal((await response.json()).code, 'farm_parked');
    await h.context.fetch(gateway);
    await flush();
    h.runTimers();
    assert.equal(h.document.body.children.length, 1);
    assert.equal(h.calls.length, 2); // One call for each explicit caller request; no replay.
});

test('network rejection stays the same rejection and does not retry the action', async () => {
    const failure = new TypeError('synthetic disconnected network');
    const h = harness(() => Promise.reject(failure));
    await assert.rejects(h.context.fetch(gateway), error => error === failure);
    assert.equal(h.calls.length, 1);
    assert.equal(h.document.body.children.length, 0);
    h.runTimers();
    assert.equal(h.document.body.children.length, 1);
    assert.equal(h.focusEvents[0].href, '/');
});

test('leaving suppresses aborted-request UI, then a restored page shows stale-document failures', async () => {
    const staleResponse = new Response(JSON.stringify({ code: 'stale_game_page' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
    });
    const stalePending = Promise.resolve(staleResponse);
    let requests = 0;
    const h = harness(() => requests++ === 0
        ? Promise.reject(new Error('navigation aborted'))
        : stalePending);
    h.globalEvents.get('pagehide')();
    await assert.rejects(h.context.fetch(gateway));
    h.runTimers();
    assert.equal(h.document.body.children.length, 0);
    assert.equal(h.focusEvents.length, 0);

    // Safari can restore the same document, including its observer closure.
    h.globalEvents.get('pageshow')?.({ persisted: true });
    const pending = h.context.fetch(gateway);
    assert.equal(pending, stalePending);
    assert.equal(await pending, staleResponse);
    await flush();
    h.runTimers();
    assert.ok(h.document.getElementById('farmvillage-save-interrupted'));
    assert.equal(h.focusEvents.length, 1);
    assert.equal(h.focusEvents[0].href, '/');
    assert.equal(h.calls.length, 2, 'Restoring must not replay or send a gateway request.');
    assert.equal(h.calls[1].init.headers.get('x-god-barn-epoch'), 'observer-test-epoch');
    assert.equal(staleResponse.bodyUsed, false);
});

test('successful synchronous XHR keeps native return values/body and does not touch DOM or focus', () => {
    const h = harness(() => { throw new Error('XHR must not replay through fetch.'); });
    const xhr = new h.FakeXHR();
    assert.equal(xhr.open('POST', gateway, false), 'open-result');
    const body = new Uint8Array([0, 3, 1]);
    assert.equal(xhr.send(body), 'send-result');
    assert.equal(xhr.sentBody, body);
    assert.equal(xhr.sendCalls, 1);
    assert.equal(xhr.headers.get('x-god-barn-epoch'), 'observer-test-epoch');
    assert.deepEqual(xhr.openCall, ['POST', gateway, false]);
    assert.equal(h.created.length, 0);
    assert.equal(h.focusEvents.length, 0);
});

test('failed synchronous XHR defers all error DOM and focus until after send returns', () => {
    const h = harness(() => Promise.resolve(new Response('unused')));
    const xhr = new h.FakeXHR();
    xhr.status = 409;
    xhr.contentType = 'application/json';
    xhr.responseText = JSON.stringify({ code: 'stale_game_page' });
    xhr.open('POST', gateway, false);
    xhr.send('amf');
    assert.equal(h.created.length, 0);
    assert.equal(h.focusEvents.length, 0);
    h.runTimers();
    assert.equal(h.focusEvents.length, 1);
    assert.equal(h.focusEvents[0].href, '/');
    assert.equal(xhr.sendCalls, 1);
    assert.equal(h.calls.length, 0);
});

test('successful observer preserves the native Promise and consumer ordering versus header-only transport', async () => {
    const observerBranch = 'pending.then(inspect,()=>{failed(0);});';
    const baseline = source.replace(observerBranch, '');
    assert.notEqual(baseline, source, 'The comparison must remove exactly the response observer.');
    for (const script of [baseline, source]) {
        const response = new Response('ok');
        const native = Promise.resolve(response);
        const h = harness(() => native, script);
        const order = [];
        const promise = h.context.fetch(gateway);
        assert.equal(promise, native);
        promise.then(value => { assert.equal(value, response); order.push('consumer'); });
        queueMicrotask(() => order.push('checkpoint'));
        await flush();
        assert.deepEqual(order, ['consumer', 'checkpoint']);
        assert.equal(h.calls.length, 1);
        assert.equal(h.created.length, 0);
        assert.equal(h.focusEvents.length, 0);
    }
});
