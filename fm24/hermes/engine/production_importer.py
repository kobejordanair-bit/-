"""Generic Import V1 production entrypoint: reads only the ACTIVE registry baseline."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from stabilized_importer import import_document_v1, ImportFailure, parse, resolve
from openpyxl import load_workbook
from identity_refresh import refresh_identity_map
from derived_rebuild import rebuild_derived
from generic_importer import validate as generic_validate
from barcelona_honours_sync_v1 import sync_workbook

DEFAULT_REGISTRY=Path('/opt/data/FM24_World_Current.json')
V1_FORMAT = 'FORMAT=FM_WORLD_IMPORT_V1'
V11_FORMAT = 'FORMAT=FM_WORLD_IMPORT_V1_1'
REJECTED_DOTTED_V11 = 'FORMAT=FM_WORLD_IMPORT_V1.1'


def active_canonical(registry_path: Path = DEFAULT_REGISTRY) -> Path:
    registry_path=Path(registry_path)
    if not registry_path.is_file():
        raise ImportFailure(f'ACTIVE_REGISTRY_MISSING:{registry_path}')
    data=json.loads(registry_path.read_text(encoding='utf-8'))
    required=('canonical_workbook','version','sha256','schema_version','status','updated_at')
    if any(not data.get(k) for k in required) or data['status']!='ACTIVE':
        raise ImportFailure('ACTIVE_REGISTRY_INVALID')
    path=Path(data['canonical_workbook'])
    if not path.is_file():
        raise ImportFailure(f'ACTIVE_CANONICAL_MISSING:{path}')
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != data['sha256']:
        raise ImportFailure('ACTIVE_CANONICAL_SHA256_MISMATCH')
    return path


def import_into_active(output: Path, text: str, metadata: dict, registry_path: Path = DEFAULT_REGISTRY):
    """Run Generic Import → Identity → Derived → conditional Honours → validation.

    Honours runs only for Barcelona membership changes (C-0030); CWC is never
    inferred by this pipeline.
    """
    baseline=active_canonical(registry_path)
    document=parse(text)
    resolved,_=resolve(document, load_workbook(baseline,read_only=True))
    if any(club_id=='C-0188' for _,_,club_id,_ in resolved):
        raise ImportFailure('DEPRECATED_CLUB_ID_DO_NOT_USE:C-0188')
    result=import_document_v1(baseline, Path(output), text, metadata)
    identity=refresh_identity_map(output,reconcile_row_provenance=True)
    derived=rebuild_derived(output)
    # Derived/honours is a mandatory, idempotent post-write phase. It may also
    # complete pre-existing derivable gaps without altering source facts.
    barcelona_affected=any(club_id=='C-0030' for _,_,club_id,_ in resolved)
    honours=sync_workbook(output)
    generic=generic_validate(output)
    if not all(generic.values()):
        raise ImportFailure('POST_IMPORT_GLOBAL_VALIDATION_FAILED')
    result['pipeline']={'identity_refresh':identity,'derived_sync_v1':derived,
                        'barcelona_honours_sync_v1':honours,
                        'global_validation':generic,'barcelona_honours_triggered':barcelona_affected}
    return result


def import_full_player_into_active(
    output: Path,
    text: str,
    metadata: dict,
    registry_path: Path = DEFAULT_REGISTRY,
    *,
    operation_mode: str | None = None,
    input_workbook: Path | None = None,
):
    """Exact production dispatch; ATTRIBUTE_BACKFILL is caller-selected only.

    The document format remains V1.1.  The operation mode is never inferred from
    TXT content, and the normal Full Player V1.1 route remains its own policy.
    """
    first = text.splitlines()[0].strip() if text.splitlines() else ''
    if first == V1_FORMAT:
        if operation_mode is not None or input_workbook is not None:
            raise ImportFailure('OPERATION_MODE_UNSUPPORTED_FOR_FORMAT')
        return import_into_active(Path(output), text, metadata, registry_path)
    if first == V11_FORMAT:
        if operation_mode == 'ATTRIBUTE_BACKFILL':
            from attribute_backfill_v11 import import_attribute_backfill_v11
            return import_attribute_backfill_v11(
                Path(output), text, metadata, Path(registry_path),
                input_workbook=Path(input_workbook) if input_workbook is not None else None,
                operation_mode=operation_mode,
            )
        if operation_mode is not None or input_workbook is not None:
            raise ImportFailure('OPERATION_MODE_UNSUPPORTED_OR_REQUIRED')
        # Local import avoids a V1/V1.1 dispatcher cycle.
        from full_player_import_v11 import import_full_v11
        return import_full_v11(Path(output), text, metadata, Path(registry_path))
    if first == REJECTED_DOTTED_V11:
        raise ImportFailure('FORMAT_VERSION_REQUIRED_OR_UNSUPPORTED')
    raise ImportFailure('FORMAT_VERSION_REQUIRED_OR_UNSUPPORTED')
