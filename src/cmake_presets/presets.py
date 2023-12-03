import json
import logging
import os
from typing import Any, Dict, List, Set, Tuple, Union

# Trick to get all internal classes to load
__all__ = [
    "MSVCToolkit",
    "GCCToolkit",
    "OneAPIToolkit",
    "BatScriptToolkit",
    "ShellScriptToolkit",
    "add_preset",
    "generate_presets_file",
]

from .gcc import GCCToolkit
from .msvc import MSVCToolkit
from .oneapi import OneAPIToolkit
from .toolkit import BatScriptToolkit, ShellScriptToolkit, Toolkit, ToolkitError
from .util import merge_presets

log = logging.getLogger(__name__)


def add_preset(
    data: dict, preset: dict, merge: bool = False, replace: bool = False
) -> None:
    if "configurePresets" not in data:
        data["configurePresets"] = [preset]
        return
    for idx, p in enumerate(data["configurePresets"]):
        if "name" in p and p["name"] == preset["name"]:
            if merge:
                merge_presets(p, preset)
            elif replace:
                data["configurePresets"][idx] = preset
            return
    data["configurePresets"].append(preset)


def generate_presets_file(
    filename: str,
    toolkits: List[Toolkit],
    base_data: Union[Dict[str, Any], None] = None,
    static_presets: Union[List[Dict[str, Any]], None] = None,
    ignore_read_error: bool = False,
    detailed_kit_info: bool = False,
    skip_bad: bool = False,
) -> Tuple[Set[str], Set[str], Set[str]]:
    if not base_data:
        base_data = {"version": 7, "configurePresets": []}

    if not filename:
        raise RuntimeError("ERROR: Filename is empty")

    data: Dict[str, Any] = {}
    update = False
    if os.path.isfile(filename):
        update = True
        with open(filename) as f:
            try:
                data = json.load(f)
            except Exception as e:
                if ignore_read_error:
                    log.info("Failed to read existing file: %s", filename)
                else:
                    raise Exception(f"Failed to read file: {filename}\n{str(e)}") from e
    if not data:
        data = base_data

    if static_presets:
        for preset in static_presets:
            add_preset(data, preset, merge=True)

    pr_added = set()
    pr_skipped = set()
    pr_errors = set()
    for kit in toolkits:
        if kit.is_instance_supported():
            log.debug("generate: Current toolkit %s", kit.name)
            try:
                if kit.scan_select() == 0:
                    raise ToolkitError("No matches found")
                log.info("Generating preset %s from selected kit:", kit.name)
                kit.print(detailed=detailed_kit_info)
                add_preset(data, kit.get_json(), replace=True)
                pr_added.add(kit.name)
            except ToolkitError as e:
                if skip_bad:
                    pr_errors.add(kit.name)
                    log.warning(
                        'Skipping toolkit "%s" due to error:\n%s', kit.name, str(e)
                    )
                else:
                    raise e
        else:
            # Make sure at least empty configuration is in place. No modification of existing
            log.debug("Skipping unsupported toolkit: %s", kit.name)
            add_preset(data, kit.get_base_json())
            pr_skipped.add(kit.name)

    with open(filename, "w") as f:
        f.write(json.dumps(data, indent=4))

    if update:
        log.info("Updated existing preset file: %s", filename)
    else:
        log.info("Wrote new preset file: %s", filename)
    return (pr_added, pr_skipped, pr_errors)
