import assert from 'node:assert/strict';
import { mergeCloudEntities, toCloudRows, toSharedRows } from '../cloud-sync.mjs';

const local = [
  { id: 'a', title: '本機舊版', content: 'old', updatedAt: '2026-08-01T00:00:00.000Z' },
  { id: 'b', title: '本機新增', content: 'new', updatedAt: '2026-08-22T00:00:00.000Z' },
];
const remote = [
  { entity_id: 'a', payload: { id: 'a', title: '雲端新版', content: 'newer', updatedAt: '2026-08-20T00:00:00.000Z' }, client_updated_at: '2026-08-20T00:00:00.000Z', deleted_at: null },
  { entity_id: 'gone', payload: {}, client_updated_at: '2026-08-21T00:00:00.000Z', deleted_at: '2026-08-21T00:00:00.000Z' },
];

const merged = mergeCloudEntities(local, remote, 'custom_text');
assert.equal(merged.entities.find(x => x.id === 'a').title, '雲端新版');
assert.equal(merged.entities.find(x => x.id === 'b').title, '本機新增');
assert.equal(merged.tombstones.length, 1);

const conflict = mergeCloudEntities(
  [{ id: 'same', title: '本機', content: 'A', updatedAt: '2026-08-22T00:00:00.000Z' }],
  [{ entity_id: 'same', payload: { id: 'same', title: '雲端', content: 'B', updatedAt: '2026-08-22T00:00:00.000Z' }, client_updated_at: '2026-08-22T00:00:00.000Z', deleted_at: null }],
  'custom_text',
);
assert.equal(conflict.entities.length, 2);
assert.ok(conflict.entities.some(x => x.id.startsWith('same-conflict-')));

const rows = toCloudRows('user-1', 'custom_text', merged.entities);
assert.equal(rows.length, 2);
assert.equal(rows[0].user_id, 'user-1');
assert.equal(rows[0].entity_type, 'custom_text');
assert.ok(rows[0].client_updated_at);

const sharedRows = toSharedRows('workspace-1', 'custom_text', merged.entities);
assert.equal(sharedRows.length, 2);
assert.equal(sharedRows[0].workspace_id, 'workspace-1');
assert.equal(sharedRows[0].entity_type, 'custom_text');
assert.equal(sharedRows[0].user_id, undefined);

console.log('cloud sync merge tests: PASS');
