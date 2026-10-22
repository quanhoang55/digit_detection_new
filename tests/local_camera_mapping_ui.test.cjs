const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('./frontend_fixture.cjs').html().match(/<script>([\s\S]*?)<\/script>/)[1];

test('local camera indexes cannot overwrite Gemini browser device selections', () => {
  const saved = new Map([['rollQrScale.cameraMap.v1:gateway-04', '{"station-04":"browser-usb-id"}']]);
  const context = vm.createContext({
    CAMERA_MAP_PREFIX: 'rollQrScale.cameraMap.v1:',
    appStatus: {weight_engine: 'local-yolo', gateway_id: 'gateway-04'},
    localStorage: {getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value)},
  });
  for (const name of ['mappingKey', 'readMappings', 'writeMappings']) {
    vm.runInContext(script.split('\n').find(line => line.startsWith('function ' + name + '(')), context);
  }
  assert.equal(context.mappingKey(), 'rollQrScale.localCameraMap.v1:gateway-04');
  context.appStatus = null;
  assert.equal(context.mappingKey(), 'rollQrScale.localCameraMap.v1:gateway-01');
  context.appStatus = {weight_engine: 'local-yolo', gateway_id: 'gateway-04'};
  context.writeMappings({'station-04': '0'});
  assert.equal(saved.get('rollQrScale.cameraMap.v1:gateway-04'), '{"station-04":"browser-usb-id"}');
  context.appStatus.weight_engine = 'gemini';
  assert.equal(context.readMappings()['station-04'], 'browser-usb-id');
  context.appStatus.weight_engine = 'local-yolo';
  assert.equal(context.readMappings()['station-04'], '0');
});
