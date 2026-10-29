import test from 'node:test';
import assert from 'node:assert/strict';
import { layoutProbeReadouts } from '../frontend/probe-layout.js';
function verify(points, width = 1000, height = 700) {
  const labels = layoutProbeReadouts(points, width, height);
  assert.equal(labels.length, points.length);
  for (const [i,a] of labels.entries()) {
    assert.ok(a.x >= 0 && a.y >= 0 && a.x+a.width <= width && a.y+a.height <= height);
    for (const b of labels.slice(i+1)) assert.ok(a.x+a.width <= b.x || b.x+b.width <= a.x || a.y+a.height <= b.y || b.y+b.height <= a.y);
    for (const p of points) assert.ok(p.x < a.x || p.x > a.x+a.width || p.y < a.y || p.y > a.y+a.height);
  }
  return labels;
}
test('close probes fan out without overlapping labels or covering markers',()=>{
  verify([{id:1,x:450,y:300},{id:2,x:465,y:301},{id:3,x:470,y:310},{id:4,x:460,y:320}]);
});
test('32 probes in one cluster have separate labels',()=>{
  verify(Array.from({length:32},(_,id)=>({id,x:450+id%4,y:300+id%3})),1600,1000);
});
test('corners stay within canvas and layout is deterministic',()=>{
  const p=[{id:1,x:5,y:5},{id:2,x:995,y:5},{id:3,x:995,y:695},{id:4,x:5,y:695}];
  assert.deepEqual(verify(p),verify(p));
});
test('offscreen probes do not occupy canvas space',()=>{
  assert.deepEqual(layoutProbeReadouts([{id:1,x:-20,y:50}],1000,700),[]);
});
