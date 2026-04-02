# plugins/snapshot_manager.py

import boto3
import logging
from botocore.exceptions import ClientError
# Make sure your main script is in the path or installed
from webshell import BasePlugin 

# --- Helper Functions (where you'll write the Boto3 logic) ---

def _create_snapshot(instance_id_or_name, description):
    print(f"Logic to create snapshot for '{instance_id_or_name}' with description '{description}' goes here.")
    # 1. Find instance.
    # 2. Find root volume ID.
    # 3. Call ec2.create_snapshot() with tags.
    # 4. Use waiter 'snapshot_completed'.
    # 5. Report new snapshot ID.
    pass

def _list_snapshots(max_items):
    print(f"Logic to list the last {max_items} snapshots created by this tool goes here.")
    # 1. Call ec2.describe_snapshots() with a filter for the 'CreatedBy: WebShellSnapshotTool' tag.
    # 2. Format and print the results in a table.
    pass

def _restore_by_swap(instance_id_or_name, snapshot_id):
    print(f"Restoring '{instance_id_or_name}' from '{snapshot_id}' using volume swap...")
    # Follow the detailed 'swap' workflow outlined above.
    pass

def _restore_by_rebuild(instance_id_or_name, snapshot_id):
    print(f"Restoring '{instance_id_or_name}' from '{snapshot_id}' by rebuilding the instance...")
    # Follow the detailed 'rebuild' workflow outlined above.
    pass

def _cleanup_snapshots(keep, dry_run):
    print(f"Cleaning up old snapshots, keeping the last {keep}...")
    if dry_run:
        print("DRY RUN: No snapshots will be deleted.")
    # 1. List all snapshots with the tool's tag.
    # 2. Sort them by date.
    # 3. Identify snapshots older than the 'keep' count.
    # 4. If not a dry run, call ec2.delete_snapshot() for each one.
    pass

# --- Main Command Handler Functions ---

def handle_create(*args):
    if not args:
        print("Usage: snapshot create <instance_id_or_name> [--description 'Your description']")
        return
    
    # Simple argument parsing
    instance_id = args[0]
    description = "Snapshot created by WebShell"
    if "--description" in args:
        try:
            desc_index = args.index("--description") + 1
            description = args[desc_index]
        except IndexError:
            print("Error: --description flag requires a value.")
            return
            
    _create_snapshot(instance_id, description)

def handle_list(*args):
    max_items = 20
    if "--max-items" in args:
        try:
            max_index = args.index("--max-items") + 1
            max_items = int(args[max_index])
        except (IndexError, ValueError):
            print("Error: --max-items requires a valid number.")
            return
    _list_snapshots(max_items)
    
def handle_restore(*args):
    if len(args) < 2 or "--method" not in args:
        print("Usage: snapshot restore <instance_id_or_name> <snapshot_id> --method [swap|rebuild]")
        return
        
    instance_id, snapshot_id = args[0], args[1]
    
    try:
        method_index = args.index("--method") + 1
        method = args[method_index]
    except (IndexError, ValueError):
        print("Error: --method flag requires a value (swap or rebuild).")
        return
        
    if method == "swap":
        _restore_by_swap(instance_id, snapshot_id)
    elif method == "rebuild":
        _restore_by_rebuild(instance_id, snapshot_id)
    else:
        print(f"Error: Unknown restore method '{method}'. Choose 'swap' or 'rebuild'.")

def handle_cleanup(*args):
    keep = 3
    dry_run = "--dry-run" in args
    if "--keep" in args:
        try:
            keep_index = args.index("--keep") + 1
            keep = int(args[keep_index])
        except (IndexError, ValueError):
            print("Error: --keep requires a valid number.")
            return
    _cleanup_snapshots(keep, dry_run)


class SnapshotManagerPlugin(BasePlugin):
    """A plugin for creating, restoring, and managing EC2 snapshots."""
    @property
    def name(self) -> str:
        return "snapshot_manager"

    @property
    def commands(self) -> dict:
        return {
            'snapshot': {
                '_description': 'Manage EC2 snapshots (create, restore, list, cleanup).',
                'create': handle_create,
                'list': handle_list,
                'restore': handle_restore,
                'cleanup': handle_cleanup,
            }
        }
