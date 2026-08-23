import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './supabase-config.mjs?v=20260823-3';
import { mergeCloudEntities, toCloudRows, toSharedRows } from './cloud-sync.mjs';

export const isCloudConfigured = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);
export const supabase = isCloudConfigured
  ? createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

function requireClient() {
  if (!supabase) throw new Error('尚未設定 Supabase 雲端同步。');
  return supabase;
}

function throwIfError(error) {
  if (error) throw error;
}

export async function getCloudUser() {
  const client = requireClient();
  const { data: sessionData, error: sessionError } = await client.auth.getSession();
  throwIfError(sessionError);
  return sessionData.session?.user || null;
}

export function onCloudAuthChange(callback) {
  return requireClient().auth.onAuthStateChange((_event, session) => callback(session?.user || null));
}

export async function signInWithEmail(email) {
  const normalizedEmail = String(email || '').trim();
  if (!normalizedEmail) throw new Error('請輸入電子郵件。');
  const { error } = await requireClient().auth.signInWithOtp({
    email: normalizedEmail,
    options: { emailRedirectTo: window.location.origin + window.location.pathname },
  });
  throwIfError(error);
}

export async function signInWithGoogle() {
  const { error } = await requireClient().auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + window.location.pathname },
  });
  throwIfError(error);
}

export async function signOut() {
  const { error } = await requireClient().auth.signOut();
  throwIfError(error);
}

async function readRows(tableName, filters) {
  let query = requireClient().from(tableName).select('entity_id,payload,client_updated_at,updated_at,deleted_at');
  for (const [column, value] of Object.entries(filters)) query = query.eq(column, value);
  const { data, error } = await query;
  throwIfError(error);
  return data || [];
}

async function writeRows(tableName, rows, conflictTarget) {
  if (!rows.length) return;
  const { error } = await requireClient().from(tableName).upsert(rows, { onConflict: conflictTarget });
  throwIfError(error);
}

function deletionRows(ownerColumn, ownerId, entityType, tombstones) {
  return tombstones.map(tombstone => ({
    [ownerColumn]: ownerId,
    entity_type: entityType,
    entity_id: String(tombstone.id),
    payload: {},
    client_updated_at: tombstone.deletedAt,
    deleted_at: tombstone.deletedAt,
  }));
}

export async function syncCollection(userId, entityType, localEntities, tombstones = []) {
  const remoteRows = await readRows('study_entities', { user_id: userId, entity_type: entityType });
  const merged = mergeCloudEntities(localEntities, remoteRows, entityType);
  await writeRows(
    'study_entities',
    [...toCloudRows(userId, entityType, merged.entities), ...deletionRows('user_id', userId, entityType, tombstones)],
    'user_id,entity_type,entity_id',
  );
  return merged;
}

export async function listLearningWorkspaces() {
  const { data, error } = await requireClient()
    .from('learning_workspaces')
    .select('id,name,owner_id,invite_code,created_at')
    .order('created_at', { ascending: true });
  throwIfError(error);
  return data || [];
}

export async function createLearningWorkspace(name) {
  const { data, error } = await requireClient().rpc('create_learning_workspace', { p_name: name });
  throwIfError(error);
  return Array.isArray(data) ? data[0] : data;
}

export async function joinLearningWorkspace(inviteCode) {
  const { data, error } = await requireClient().rpc('join_learning_workspace', { p_invite_code: inviteCode });
  throwIfError(error);
  return Array.isArray(data) ? data[0] : data;
}

export async function syncSharedCollection(workspaceId, entityType, localEntities, tombstones = []) {
  const remoteRows = await readRows('shared_learning_entities', { workspace_id: workspaceId, entity_type: entityType });
  const merged = mergeCloudEntities(localEntities, remoteRows, entityType);
  await writeRows(
    'shared_learning_entities',
    [...toSharedRows(workspaceId, entityType, merged.entities), ...deletionRows('workspace_id', workspaceId, entityType, tombstones)],
    'workspace_id,entity_type,entity_id',
  );
  return merged;
}
