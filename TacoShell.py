"""TacoShell - an extensible, plugin-based interactive shell framework."""
import argparse
import cmd2
import sys
from typing import Optional

from plugin_manager import PluginManager


class TacoShell(cmd2.Cmd):
    """An extensible, plugin-based interactive shell powered by cmd2."""
    
    def __init__(self, plugin_args: Optional[argparse.Namespace] = None):
        super().__init__(allow_cli_args=False)
        self.prompt = ">> "
        self.intro = "Taco Shell Framework. Type 'help' for commands or 'plugin_load <name>' to load a plugin."
        
        # Hide unnecessary cmd2 commands
        self.hidden_commands.extend(['run_script', 'run_pyscript', '_relative_run_script'])
        
        # Initialize the plugin manager
        self.plugin_manager = PluginManager(self)
        
        # Load initial plugin if specified at startup
        if plugin_args and plugin_args.plugin_name:
            self.plugin_manager.load(plugin_args.plugin_name, plugin_args.plugin_args)
    
    # --- Plugin Management Commands ---
    
    plugin_parser = cmd2.Cmd2ArgumentParser(description='Manage plugins')
    plugin_subparsers = plugin_parser.add_subparsers(title='subcommands', help='plugin subcommands')
    
    # plugin load subcommand
    load_parser = plugin_subparsers.add_parser('load', help='Load a plugin')
    load_parser.add_argument('plugin_name', help='Name of the plugin to load')
    load_parser.add_argument('plugin_args', nargs='*', help='Optional arguments for the plugin')
    load_parser.set_defaults(func='_handle_plugin_load')
    
    # plugin unload subcommand
    unload_parser = plugin_subparsers.add_parser('unload', help='Unload a plugin')
    unload_parser.add_argument('plugin_name', help='Name of the plugin to unload')
    unload_parser.set_defaults(func='_handle_plugin_unload')
    
    # plugin list subcommand
    list_parser = plugin_subparsers.add_parser('list', help='List plugins')
    list_parser.set_defaults(func='_handle_plugin_list')
    
    @cmd2.with_argparser(plugin_parser)
    def do_plugin(self, args: argparse.Namespace) -> None:
        """Manage plugins. Use 'plugin help' for subcommands."""
        if not hasattr(args, 'func'):
            self.poutput(args.format_help())
            return
        
        handler_name = args.func
        if handler_name == '_handle_plugin_load':
            self._handle_plugin_load(args)
        elif handler_name == '_handle_plugin_unload':
            self._handle_plugin_unload(args)
        elif handler_name == '_handle_plugin_list':
            self._handle_plugin_list(args)
    
    def _handle_plugin_load(self, args: argparse.Namespace) -> None:
        """Handle 'plugin load' subcommand."""
        plugin_args = args.plugin_args if hasattr(args, 'plugin_args') else []
        self.plugin_manager.load(args.plugin_name, plugin_args)
    
    def _handle_plugin_unload(self, args: argparse.Namespace) -> None:
        """Handle 'plugin unload' subcommand."""
        self.plugin_manager.unload(args.plugin_name)
    
    def _handle_plugin_list(self, args: argparse.Namespace) -> None:
        """Handle 'plugin list' subcommand."""
        self.plugin_manager.list_plugins()
    
    def default(self, statement: cmd2.Statement) -> Optional[bool]:
        """Default handler for unrecognized commands."""
        self.poutput(f"Error: Command '{statement.command}' not found.")
        return False


def cli():
    """Entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Taco Shell - An extensible, plugin-based interactive shell."
    )
    parser.add_argument(
        'plugin_name',
        nargs='?',
        help='Optional: Plugin to load on startup'
    )
    parser.add_argument(
        'plugin_args',
        nargs=argparse.REMAINDER,
        help='Optional arguments for the plugin'
    )
    
    args, _ = parser.parse_known_args()
    shell = TacoShell(plugin_args=args)
    sys.exit(shell.cmdloop())


if __name__ == "__main__":
    cli()
