import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  assessDemo,
  demoStatus,
  demoTramDelay,
  demoChanges,
  DEMO_REASONS,
} from '../src/explorer/health-demo.ts';
const at = (h: number, m = 0) => (h * 60 + m) * 60000;
test('area states change at half-open event boundaries and remain independently assessable', () => {
  assert.equal(assessDemo('cbd', at(8, 15) - 1).status, 'clear');
  assert.equal(assessDemo('cbd', at(8, 15)).status, 'affected');
  assert.equal(assessDemo('southbank', at(9, 15)).status, 'severe');
  assert.equal(assessDemo('cbd', at(9, 15)).status, 'affected');
  assert.equal(assessDemo('southbank', at(9, 25)).status, 'affected');
  assert.equal(assessDemo('southbank', at(9, 35)).status, 'clear');
  assert.equal(assessDemo('cbd', at(9, 40)).status, 'unknown');
  assert.equal(assessDemo('southbank', at(9, 40)).status, 'clear');
  assert.equal(assessDemo('cbd', at(10, 5)).status, 'clear');
});
test('missing coverage never hides a confirmed adverse impact', () => {
  assert.equal(demoStatus([DEMO_REASONS[0]], ['weather']), 'affected');
  assert.equal(demoStatus([DEMO_REASONS[2]], ['weather']), 'severe');
  assert.equal(demoStatus([], ['transport']), 'unknown');
  assert.equal(demoStatus([], []), 'clear');
});
test('seek and replay share deterministic authored states, independent of traffic or DAM counts', () => {
  const clocks = [at(8), at(8, 25), at(9, 15), at(9, 36), at(9, 50)];
  const first = clocks.map((clock) => assessDemo('cbd', clock));
  for (const clock of [...clocks].reverse()) assessDemo('cbd', clock);
  assert.deepEqual(
    clocks.map((clock) => assessDemo('cbd', clock)),
    first,
  );
  for (const clock of [NaN, -1, 86400001])
    assert.throws(() => assessDemo('cbd', clock));
});
test('tram highlights are authored transport zones, scoped to the right area and time', () => {
  const local = DEMO_REASONS[0],
    severe = DEMO_REASONS[2];
  assert.equal(
    demoTramDelay(at(8, 25), ...local.location, 'cbd')?.severity,
    'affected',
  );
  assert.equal(
    demoTramDelay(at(9, 15), ...severe.location, 'southbank')?.severity,
    'severe',
  );
  assert.equal(demoTramDelay(at(9, 15), ...severe.location, 'cbd'), undefined);
  assert.equal(
    demoTramDelay(at(9, 25), ...severe.location, 'southbank'),
    undefined,
  );
  assert.equal(demoTramDelay(at(8), ...local.location, 'cbd'), undefined);
  assert.equal(demoTramDelay(at(9, 15), 145, -38, 'cbd'), undefined);
});
test('scripted change navigation includes recoveries and missing-source transitions', () => {
  assert.deepEqual(demoChanges('southbank', at(9, 15)), {
    previous: at(9, 10),
    next: at(9, 25),
  });
  assert.deepEqual(demoChanges('cbd', at(9, 50)), {
    previous: at(9, 40),
    next: at(10, 5),
  });
  assert.equal(demoChanges('southbank', at(12)).next, null);
});
