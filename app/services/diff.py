import difflib
from typing import Any


def detect_changes(
    old_text: str,
    new_text: str,
    max_changes: int = 20,
) -> dict[str, Any]:

    if old_text == new_text:
        return {
            "changed": False,
            "added": [],
            "removed": [],
            "replaced": [],
            "added_count": 0,
            "removed_count": 0,
        }

    old_blocks = old_text.splitlines()
    new_blocks = new_text.splitlines()

    matcher = difflib.SequenceMatcher(
        None,
        old_blocks,
        new_blocks,
        autojunk=False,
    )

    added: list[str] = []
    removed: list[str] = []
    replaced: list[dict[str, list[str]]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == "equal":
            continue

        if tag == "delete":
            removed.extend(old_blocks[i1:i2])

        elif tag == "insert":
            added.extend(new_blocks[j1:j2])

        elif tag == "replace":
            replaced.append(
                {
                    "old": old_blocks[i1:i2],
                    "new": new_blocks[j1:j2],
                }
            )

    return {
        "changed": True,
        "added": added[:max_changes],
        "removed": removed[:max_changes],
        "replaced": replaced[:max_changes],
        "added_count": len(added),
        "removed_count": len(removed),
    }