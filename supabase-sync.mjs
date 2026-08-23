import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './supabase-config.mjs';
import { mergeCloudEntities, toCloudRows } from './cloud-sync.mjs';

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
  if (!sessionData.session?.user) return null;
  return sessionData.session.user;
}

export function onCloudAuthChange(callback) {
  const client = requireClient();
  return client.auth.onAuthStateChange((_event, session) => callback(session?.user || null));
}

export async function signInWithEmail(email) {
  const normalizedEmail = String(email || '').trim();
  if (!normalizedEmail) throw new Error('請輸入電子郵件。');
  const client = requireClient();
  const { error } = await client.auth.signInWithOtp({
    email: normalizedEmail,
    options: { emailRedirectTo: window.location.origin + window.location.pathname },
  });
  throwIfError(error);
}

export async function signInWithGoogle() {
  const client = requireClient();
  const { error } = await client.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + window.location.pathname },
  });
  throwIfError(error);
}

export async function signOut() {
  const { error } = await requireClient().auth.signOut();
  throwIfError(error);
}

export async function syncCollection(userId, entityType, localEntities, tombstones = []) {
  const client = requireClient();
  const { data: remoteRows, error: readError } = await client
    .from('study_entities')
    .select('entity_id,payload,client_updated_at,updated_at,deleted_at')
    .eq('user_id', userId)
    .eq('entity_type', entityType);
  throwIfError(readError);

  const merged = mergeCloudEntities(localEntities, remoteRows || [], entityType);
  const activeRows = toCloudRows(userId, entityType, merged.entities);
  const deletionRows = tombstones.map(tombstone => ({
    user_id: userId,
    entity_type: entityType,
    entity_id: String(tombstone.id),
    payload: {},
    client_updated_at: tombstone.deletedAt,
    deleted_at: tombstone.deletedAt,
  }));
  const rows = [...activeRows, ...deletionRows];
  if (rows.length) {
    const { error: writeError } = await client
      .from('study_entities')
      .upsert(rows, { onConflict: 'user_id,entity_type,entity_id' });
    throwIfError(writeError);
  }
  return merged;
}
