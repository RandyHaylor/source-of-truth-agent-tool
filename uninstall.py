#!/usr/bin/env python3
"""
Cross-platform uninstaller for source-of-truth-agent-tool.

Reverses what install.py did:
  1. Removes ~/.claude/skills/source-of-truth-agent-tool/ entirely (skill
     manifest, wrapper scripts, copied package).
  2. Removes the on-PATH `source-of-truth` (or `.bat`) stub.
  3. Removes any UserPromptSubmit or PostToolUse hook entry from
     ~/.claude/settings.json whose command references the install dir.
  4. Backs up settings.json before changing it.

Does NOT delete ~/.source-of-truth/ (raw input logs, requirements trees,
project settings, global-settings.json). Remove that directory manually
if you want to wipe state.
"""
import datetime
import json
import os
import platform
import shutil


SKILL_INSTALL_DIR_NAME = "source-of-truth-agent-tool"


def home_claude_dir():
    return os.path.expanduser("~/.claude")


def install_dir_path():
    return os.path.join(home_claude_dir(), "skills", SKILL_INSTALL_DIR_NAME)


def path_stub_target_directory_for_current_platform():
    if platform.system() == "Windows":
        return os.path.join(
            os.path.expanduser("~"),
            "AppData", "Local", "Microsoft", "WindowsApps",
        )
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def path_stub_filename_for_current_platform():
    return "source-of-truth.bat" if platform.system() == "Windows" else "source-of-truth"


def settings_json_path():
    return os.path.join(home_claude_dir(), "settings.json")


def load_settings_json_if_exists(path):
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        content = f.read().strip()
    return json.loads(content) if content else {}


def backup_file(path):
    if not os.path.isfile(path):
        return None
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"{path}.bak.{timestamp}"
    shutil.copyfile(path, backup_path)
    return backup_path


def write_settings_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def remove_our_hook_entries(settings_data, hook_event_name):
    """Returns count of removed entries. Mutates settings_data."""
    hooks_root = settings_data.get("hooks")
    if not isinstance(hooks_root, dict):
        return 0
    event_list = hooks_root.get(hook_event_name)
    if not isinstance(event_list, list):
        return 0
    removed_count = 0
    surviving_matcher_entries = []
    for matcher_entry in event_list:
        inner_hooks = matcher_entry.get("hooks", [])
        filtered_inner_hooks = []
        for hook_item in inner_hooks:
            if SKILL_INSTALL_DIR_NAME in hook_item.get("command", ""):
                removed_count += 1
                continue
            filtered_inner_hooks.append(hook_item)
        if filtered_inner_hooks:
            matcher_entry["hooks"] = filtered_inner_hooks
            surviving_matcher_entries.append(matcher_entry)
    if surviving_matcher_entries:
        hooks_root[hook_event_name] = surviving_matcher_entries
    else:
        hooks_root.pop(hook_event_name, None)
        if not hooks_root:
            settings_data.pop("hooks", None)
    return removed_count


def main():
    install_dir = install_dir_path()
    settings_path = settings_json_path()

    print(f"Install dir: {install_dir}")
    print(f"Settings:    {settings_path}\n")

    print("Step 1: remove install dir")
    if os.path.isdir(install_dir):
        shutil.rmtree(install_dir)
        print(f"  removed: {install_dir}")
    else:
        print(f"  not present -- nothing to remove at {install_dir}")
    print()

    print("Step 2: remove on-PATH `source-of-truth` stub")
    path_stub_path = os.path.join(
        path_stub_target_directory_for_current_platform(),
        path_stub_filename_for_current_platform(),
    )
    if os.path.isfile(path_stub_path):
        os.remove(path_stub_path)
        print(f"  removed: {path_stub_path}")
    else:
        print(f"  not present -- nothing to remove at {path_stub_path}")
    print()

    print("Step 3: scrub hook entries from settings.json")
    settings_data = load_settings_json_if_exists(settings_path)
    if settings_data is None:
        print("  settings.json does not exist — nothing to edit")
    else:
        removed_user = remove_our_hook_entries(settings_data, "UserPromptSubmit")
        removed_post = remove_our_hook_entries(settings_data, "PostToolUse")
        if removed_user + removed_post == 0:
            print("  no matching hook entries found — nothing to remove")
        else:
            backup_path = backup_file(settings_path)
            if backup_path:
                print(f"  backed up old settings.json to {backup_path}")
            write_settings_json(settings_path, settings_data)
            print(
                f"  removed {removed_user} UserPromptSubmit + "
                f"{removed_post} PostToolUse entries"
            )

    print("\nUninstall complete.")
    print("Note: ~/.source-of-truth/ left in place. Delete manually to wipe state.")


if __name__ == "__main__":
    main()
