"""Plugin interface contract for TacoShell."""
from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """Abstract base class that all plugins must inherit from."""
    
    def __init__(self, **kwargs):
        """Initialize the plugin."""
        self._shell = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique identifier for this plugin."""
        pass
    
    def default(self, statement: str) -> None:
        """
        Optional: Override to handle unrecognized commands.
        This is called when a command is not found in the shell.
        """
        pass
    
    def set_shell(self, shell) -> None:
        """Give the plugin a reference back to the shell."""
        self._shell = shell
