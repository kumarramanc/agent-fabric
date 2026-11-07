"""Small helper functions for exploring the support agent's data."""

import json as json_lib
import os as os_lib


def json_entry_viewer(file_path):
    """Browse a JSON list of records in the terminal without changing the file."""
    with open(file_path, encoding="utf-8") as file:
        entries = json_lib.load(file)

    if not isinstance(entries, list):
        print("The file must contain a list of entries.")
        return

    total_entries = len(entries)

    if total_entries == 0:
        print("There are no entries to display.")
        return

    # Python counts from 0, so index 0 means the first entry.
    index = 0
    command = ""

    # Keep displaying entries until the user types q.
    while command != "q":
        entry_number = index + 1
        current_entry = entries[index]

        print()
        print("Entry", entry_number, "of", total_entries)
        print(json_lib.dumps(current_entry, indent=2))

        try:
            command = input("Type n for next, p for previous, or q to quit: ")
        except (EOFError, KeyboardInterrupt):
            print("\nViewer closed.")
            return

        command = command.strip()
        command = command.lower()

        if command == "n":
            # Move forward only if another entry exists.
            if index < total_entries - 1:
                index = index + 1
            else:
                print("You are already at the last entry.")

        elif command == "p":
            # Move backward only if we are past the first entry.
            if index > 0:
                index = index - 1
            else:
                print("You are already at the first entry.")

        elif command == "q":
            print("Viewer closed.")

        else:
            print("Please enter n, p, or q.")


def txt_file_viewer(dir_path):
    """Browse text files in a folder and its subfolders without changing them."""
    if not os_lib.path.isdir(dir_path):
        print("Policy folder not found:", dir_path)
        return

    # Walk through the policy folder and each version subfolder.
    # Keep relative paths so we can distinguish v1, v2, and v3 files.
    file_names = []

    for folder_path, subfolders, names in os_lib.walk(dir_path):
        subfolders.sort()
        for name in sorted(names):
            if name.lower().endswith(".txt"):
                file_path = os_lib.path.join(folder_path, name)
                relative_path = os_lib.path.relpath(file_path, dir_path)
                file_names.append(relative_path)

    total_files = len(file_names)

    if total_files == 0:
        print("No policy .txt files found in:", dir_path)
        return

    index = 0
    command = ""

    while command != "q":
        file_number = index + 1
        file_name = file_names[index]
        file_path = os_lib.path.join(dir_path, file_name)

        with open(file_path, encoding="utf-8") as file:
            policy_text = file.read()

        print()
        print("Policy", file_number, "of", total_files)
        print("File:", file_name)
        print(policy_text)

        try:
            command = input("Type n for next, p for previous, or q to quit: ")
        except (EOFError, KeyboardInterrupt):
            print("\nViewer closed.")
            return

        command = command.strip()
        command = command.lower()

        if command == "n":
            if index < total_files - 1:
                index = index + 1
            else:
                print("You are already at the last policy.")

        elif command == "p":
            if index > 0:
                index = index - 1
            else:
                print("You are already at the first policy.")

        elif command == "q":
            print("Viewer closed.")

        else:
            print("Please enter n, p, or q.")
