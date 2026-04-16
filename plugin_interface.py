from abc import ABC, abstractmethod

class BasePlugin(ABC):
    """
    This is the interface contract that all plugins must follow.
    Both the shell and the individual plugins will import this class.
    """
    def __init__(self, **kwargs):
        # This gives the plugin a reference back to the shell that loaded it
        self._shell = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the plugin."""
        pass

    def default(self, statement: str):
        """
        Optional method for a plugin to act as a fallback handler for
        unrecognized commands. The base implementation does nothing.
        """
        pass
