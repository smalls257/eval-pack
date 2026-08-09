"""Parse structured JSON blocks embedded in lens/basis markdown docs. Stdlib only."""
import json
import re

_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def extract_json_block(md_text, index=0):
    """The Nth fenced ```json block, parsed. Raises ValueError if missing or invalid."""
    blocks = _FENCE.findall(md_text)
    if index >= len(blocks):
        raise ValueError("no ```json block at index {} (found {})".format(index, len(blocks)))
    try:
        return json.loads(blocks[index])
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON in block {}: {}".format(index, e)) from e


def parse_output_contract(md_text):
    """The lens output contract = the first ```json block in the lens .md."""
    return extract_json_block(md_text, 0)


def parse_basis(md_text):
    """The basis = the first ```json block in basis.md (sources/claims/rules)."""
    return extract_json_block(md_text, 0)


def find_output_contract(md_text):
    """The lens output contract = the first fenced ```json block carrying a 'gradedField' key.
    Malformed blocks are skipped; returns None when no contract block is present."""
    import json as _json
    for block in _FENCE.findall(md_text):
        try:
            data = _json.loads(block)
        except _json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "gradedField" in data:
            return data
    return None
