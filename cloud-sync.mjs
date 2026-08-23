function iso(value) {
  const parsed = Date.parse(value || '');
  return Number.isNaN(parsed) ? 0 : parsed;
}

function stamp(entity) {
  return entity.updatedAt || entity.updated_at || new Date(0).toISOString();
}

function comparable(entity) {
  const copy = { ...entity };
  delete copy.updatedAt;
  delete copy.updated_at;
  return JSON.stringify(copy, Object.keys(copy).sort());
}

function conflictCopy(entity, entityType) {
  const suffix = `${entityType}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    ...entity,
    id: `${entity.id}-conflict-${suffix}`,
    title: entity.title ? `${entity.title}（同步衝突副本）` : `同步衝突副本 ${entity.id}`,
    updatedAt: new Date().toISOString(),
  };
}

export function mergeCloudEntities(localEntities = [], remoteRows = [], entityType = 'entity') {
  const locals = new Map(localEntities.filter(Boolean).map(item => [String(item.id), { ...item, updatedAt: stamp(item) }]));
  const remotes = new Map(remoteRows.filter(Boolean).map(row => [String(row.entity_id), row]));
  const ids = new Set([...locals.keys(), ...remotes.keys()]);
  const entities = [];
  const tombstones = [];

  for (const id of ids) {
    const local = locals.get(id);
    const row = remotes.get(id);
    if (!row) {
      if (local) entities.push(local);
      continue;
    }

    const remoteTime = row.deleted_at || row.client_updated_at || row.updated_at;
    if (row.deleted_at) {
      if (local && iso(stamp(local)) > iso(remoteTime)) entities.push(local);
      else tombstones.push({ id, deletedAt: row.deleted_at });
      continue;
    }

    const remote = { ...(row.payload || {}), id, updatedAt: row.client_updated_at || row.updated_at || new Date(0).toISOString() };
    if (!local) {
      entities.push(remote);
      continue;
    }

    const localTime = iso(stamp(local));
    const cloudTime = iso(stamp(remote));
    if (localTime > cloudTime) {
      entities.push(local);
    } else if (cloudTime > localTime) {
      entities.push(remote);
    } else if (comparable(local) === comparable(remote)) {
      entities.push(remote);
    } else {
      // Equal timestamps with divergent content must never silently discard data.
      entities.push(remote, conflictCopy(local, entityType));
    }
  }

  return { entities, tombstones };
}

export function toSharedRows(workspaceId, entityType, entities = []) {
  return entities.map(entity => ({
    workspace_id: workspaceId,
    entity_type: entityType,
    entity_id: String(entity.id),
    payload: { ...entity, updatedAt: stamp(entity) },
    client_updated_at: stamp(entity),
    deleted_at: null,
  }));
}

export function toCloudRows(userId, entityType, entities = []) {
  return entities.map(entity => ({
    user_id: userId,
    entity_type: entityType,
    entity_id: String(entity.id),
    payload: { ...entity, updatedAt: stamp(entity) },
    client_updated_at: stamp(entity),
    deleted_at: null,
  }));
}
