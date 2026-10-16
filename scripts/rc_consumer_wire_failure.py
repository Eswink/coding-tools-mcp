"""Optional bounded current wire-error representation; never authority."""
import sys
from types import ModuleType


def _publication_failure(error):
    """Return only an actual loaded canonical wire failure, or no match.

    Validate current fields/output, not effect history or ownership. This
    helper does not import publication, poll controls, format errors or retry.
    """
    try:
        publication = sys.modules.get('rc_publication_github')
        failure = (publication.__dict__.get('WireFailure')
                   if type(publication) is ModuleType else None)
        if type(failure) is not type or type(error) is not failure:
            return None
    except BaseException:
        return None
    try:
        core = publication.__dict__.get('core')
        if type(core) is not ModuleType:
            return failure('adapter_error', 'unknown')
        code = error.code
        code_valid = type(code) is str and code in core.CODES
        code = code if code_valid else 'adapter_error'
        effect = error.effect
        effect_valid = type(effect) is str and effect in ('none', 'unknown', 'confirmed')
        ident, asset = error.release_id, error.asset
        receipts_valid = (ident is None and asset is None)
        if effect_valid and effect == 'confirmed':
            receipts_valid = ident is None or (type(ident) is int and 0 < ident < 2**63)
            if asset is not None:
                receipts_valid = (receipts_valid and type(asset) is core.RemoteAsset
                                  and type(asset.asset) is core.Asset)
                if receipts_valid:
                    try:
                        core.RemoteAsset.__post_init__(asset)
                        core.Asset.__post_init__(asset.asset)
                    except BaseException:
                        receipts_valid = False
        if not effect_valid or not receipts_valid or (not code_valid and effect == 'none'):
            effect, ident, asset = 'unknown', None, None
        args = error.args
        args_valid = (type(args) is tuple and len(args) == 1 and type(args[0]) is str
                      and args[0] == code)
        absent = object()
        notes = getattr(error, '__notes__', absent)
        notes_valid = notes is absent or (type(notes) is list and len(notes) == 0)
        chain_valid = (error.__cause__ is None and
                       (error.__context__ is None or error.__suppress_context__ is True))
        if code_valid and effect_valid and receipts_valid and args_valid and notes_valid and chain_valid:
            return error
        return failure(code, effect, ident, asset)
    except BaseException:
        return failure('adapter_error', 'unknown')
