from abc import ABC, abstractmethod
from typing import List, Dict, Any
from canonical_model import Contact

class BaseAdapter(ABC):
    """
    Abstract base class for all CRM adapters.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with configuration dictionary (from CRMConfiguration.auth_config).
        """
        self.config = config

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticates with the CRM.
        """
        pass


    def format_dict_to_string(self, data: Dict[str, Any]) -> str:
        """
        Converts a dictionary to a formatted string table.
        """
        lines = []
        for key, value in data.items():
            formatted_key = key.replace('_', ' ').title()
            lines.append(f"{formatted_key}: {value}")
        return "\n".join(lines)


    @abstractmethod
    def push_contact(self, contact: Contact, target: str = None) -> str:
        """
        Pushes a unified Contact to the CRM.
        """
        pass

    @abstractmethod
    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Retrieves the schema/fields of a target entity/object.
        """
        pass

    def upload_files(self, remote_id: str, files: List[Any]) -> None:
        """
        Uploads files to the CRM entity.
        """
        if files:
            print(f"[{self.__class__.__name__}] File upload not implemented or not supported.")
