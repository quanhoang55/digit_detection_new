const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('./frontend_fixture.cjs').html().match(/<script>([\s\S]*?)<\/script>/)[1];
const openCamera = script.split('\n').find(line => line.startsWith('async function openBackendStationCamera('));

function setup() {
  const timers = [], requests = [], messages = [], draws = [];
  const session = {
    deviceId: '0', streamGeneration: 0, cameraSelect: {}, video: {play: async () => {}},
    stop() { this.streamGeneration++; this.backendMode = false; },
    setState(state) { this.state = state; },
  };
  const paint = {drawImage: (...args) => draws.push(args), clearRect() {}};
  const frame = id => ({bitmap: {width: 960, height: 540, close() {}}, frameId: id});
  let respond = async () => frame(1);
  const context = vm.createContext({
    current: () => session, stations: [session], blocksCameraChange: () => false,
    api: async (path) => { requests.push(path); return path === '/api/live/camera' ? {} : {image: 'full-resolution-evidence'}; },
    fetchBackendPreviewFrame: async (after = 0) => {requests.push('/api/live/frame?after=' + after); return respond();},
    Image: class { constructor() { this.naturalWidth = 960; this.naturalHeight = 540; } async decode() {} },
    document: {createElement: () => ({getContext: () => paint, captureStream: () => ({})})},
    setTimeout: (callback, ms) => {timers.push({callback, ms}); return timers.length;},
    appStatus: {}, showVideo() {}, captureStatus: {}, Date,
    status: (_node, message) => messages.push(message), renderLiveRecognition() {}, renderLiveDetectionBoxes() {},
  });
  vm.runInContext(openCamera, context);
  vm.runInContext(script.split('\n').find(line => line.startsWith('async function captureBackendImage(')), context);
  return {context, session, timers, requests, messages, draws, frame, respond: fn => {respond = fn;}};
}

test('preview polls fresh frames independently of recognition at a bounded rate', async () => {
  const ui = setup();
  await ui.context.openBackendStationCamera(ui.session);
  assert.equal(ui.session.state, 'live');
  assert.equal(ui.session.backendCanvas.width, 960);
  assert.deepEqual(ui.requests, ['/api/live/camera', '/api/live/frame?after=0']);
  const timer = ui.timers.shift();
  assert.equal(timer.ms, 50);
  ui.respond(async () => ui.frame(2));
  await timer.callback();
  assert.equal(ui.draws.length, 2);
  assert.equal(ui.requests.at(-1), '/api/live/frame?after=1');
  assert.equal(ui.timers.length, 1);
  assert.equal(ui.timers[0].ms, 50);
});

test('a temporary preview failure keeps polling and recovers without reopening camera', async () => {
  const ui = setup();
  await ui.context.openBackendStationCamera(ui.session);
  ui.respond(async () => {throw Error('No fresh frame');});
  await ui.timers.shift().callback();
  assert.equal(ui.session.backendSnapshotFailed, true);
  assert.equal(ui.session.backendMode, true);
  assert.equal(ui.timers[0].ms, 500);
  ui.respond(async () => ui.frame(2));
  await ui.timers.shift().callback();
  assert.equal(ui.session.backendSnapshotFailed, false);
  assert.equal(ui.draws.length, 2);
  assert.equal(ui.requests.filter(path => path === '/api/live/camera').length, 1);
});

test('a late preview response cannot repaint or reschedule after camera changes', async () => {
  const ui = setup();
  await ui.context.openBackendStationCamera(ui.session);
  let finish;
  ui.respond(() => new Promise(resolve => {finish = resolve;}));
  const pending = ui.timers.shift().callback();
  ui.session.stop();
  const previousDraws = ui.draws.length;
  finish(ui.frame(2));
  await pending;
  assert.equal(ui.draws.length, previousDraws);
  assert.equal(ui.timers.length, 0);
});

test('evidence capture fetches original image separately from the display preview', async () => {
  const ui = setup();
  await ui.context.openBackendStationCamera(ui.session);
  assert.equal(await ui.context.captureBackendImage(ui.session), 'full-resolution-evidence');
  assert.equal(ui.requests.at(-1), '/api/live/snapshot?capture=1');
  assert.equal(ui.draws.length, 1);
});

test('evidence capture rejects a response from the previous camera', async () => {
  const ui = setup();
  await ui.context.openBackendStationCamera(ui.session);
  let finish;
  ui.context.api = path => new Promise(resolve => {ui.requests.push(path); finish = resolve;});
  const pending = ui.context.captureBackendImage(ui.session);
  ui.session.stop();
  finish({image: 'old-camera-image'});
  await assert.rejects(pending, /Đã đổi camera/);
});

test('recognition from a previous camera cannot populate the new preview', async () => {
  const session = {backendMode: true, stream: {}, streamGeneration: 1, video: {videoWidth: 960}};
  const results = [];
  let poll, finish;
  const context = vm.createContext({
    liveRecognitionPoll: 0, liveRecognitionBusy: false, current: () => session,
    setInterval: callback => {poll = callback; return 1;}, clearInterval() {},
    document: {hidden: false}, appStatus: {digit_inference_confidence: .35},
    api: () => new Promise(resolve => {finish = resolve;}),
    renderLiveRecognition: (_session, result) => results.push(result), renderLiveDetectionBoxes() {},
  });
  vm.runInContext(script.split('\n').find(line => line.startsWith('function startLiveRecognitionPolling(')), context);
  context.startLiveRecognitionPolling();
  const pending = poll();
  session.streamGeneration++;
  finish({recognition: {raw_digits: '630', numeric_value: 6.3, confidence: .9, qr: {data: 'OLD-QR'}}});
  await pending;
  assert.deepEqual(results, []);
  assert.equal(context.liveRecognitionBusy, false);
});
