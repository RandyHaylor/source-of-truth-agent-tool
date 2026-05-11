#!/usr/bin/env python3
"""
Cross-platform uninstaller for source-of-truth-agent-tool.

Non-destructive: this script ONLY removes the hook registrations and the
on-PATH `source-of-truth` stub. It deliberately does NOT delete the skill
folder itself (~/.claude/skills/source-of-truth-agent-tool/) because the
folder may be an in-place install (e.g. a git clone living at the install
path) where wiping the directory would also destroy the source repo.

What this script does:
  1. Removes the on-PATH `source-of-truth` (or `.bat`) stub.
  2. Removes any UserPromptSubmit or PostToolUse hook entry from
     ~/.claude/settings.json whose command references the skill name.
  3. Backs up settings.json before changing it.

What this script does NOT do (intentional):
  - Delete the install dir at ~/.claude/skills/source-of-truth-agent-tool/.
    Remove it manually if you want a full uninstall.
  - Delete ~/.source-of-truth/ (raw input logs, requirements trees,
    project settings, global-settings.json).
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

    print(f"Install dir: {install_dir} (NOT removed by this script)")
    print(f"Settings:    {settings_path}\n")

    print("Step 1: remove on-PATH `source-of-truth` stub")
    path_stub_path = os.path.join(
        path_stub_target_directory_for_current_platform(),
        path_stub_filename_for_current_platform(),
    )
    if os.path.isfile(path_stub_path):
        try:
            os.remove(path_stub_path)
            print(f"  removed: {path_stub_path}")
        except OSError as e:
            print(f"  WARNING: could not remove PATH stub at {path_stub_path}: {e}")
    else:
        print(f"  not present -- nothing to remove at {path_stub_path}")
    print()

    print("Step 2: scrub hook entries from settings.json")
    settings_data = load_settings_json_if_exists(settings_path)
    if settings_data is None:
        print("  settings.json does not exist -- nothing to edit")
    else:
        removed_user = remove_our_hook_entries(settings_data, "UserPromptSubmit")
        removed_post = remove_our_hook_entries(settings_data, "PostToolUse")
        if removed_user + removed_post == 0:
            print("  no matching hook entries found -- nothing to remove")
        else:
            backup_path = backup_file(settings_path)
            if backup_path:
                print(f"  backed up old settings.json to {backup_path}")
            write_settings_json(settings_path, settings_data)
            print(
                f"  removed {removed_user} UserPromptSubmit + "
                f"{removed_post} PostToolUse entries"
            )

    print()
    print("=" * 60)
    print("UNINSTALL COMPLETE")
    print("=" * 60)
    print("What was done:")
    print(f"  - Removed on-PATH `source-of-truth` stub (if it existed).")
    print(f"  - Scrubbed source-of-truth hook entries from settings.json.")
    print(f"  - settings.json backup saved if it was modified.")
    print()
    print(
        "hooks uninstalled, to complete uninstallation, manually remove the "
        "source-of-truth-agent-tool folder from the skills folder"
    )
    print(f"  skills folder: {os.path.dirname(install_dir)}")
    print()
    print("What's next:")
    print("  1. Delete the install folder above if you want a full uninstall.")
    print("  2. ~/.source-of-truth/ (project data, raw input logs, settings)")
    print("     is left in place. Delete manually to wipe state.")
    print("  3. Restart any running Claude Code sessions for the hook removal")
    print("     to take effect (settings.json is read at session startup).")


if __name__ == "__main__":
    main()
