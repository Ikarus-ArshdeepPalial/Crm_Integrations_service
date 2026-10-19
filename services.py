import os
import json
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from adapters.base_adapter import BaseAdapter
from adapters.salesforce_adapter import SalesforceAdapter
from adapters.monday_adapter import MondayAdapter
from adapters.hubspot_adapter import HubSpotAdapter
from adapters.pipedrive_adapter import PipedriveAdapter
from adapters.dynamics_adapter import DynamicsAdapter
from adapters.ikarusdelta_adapter import IkarusDeltaAdapter
from typing import Type



class BrokerService:

    ADAPTER_MAP: dict[str, Type[BaseAdapter]] = {
        'salesforce': SalesforceAdapter,
        'monday': MondayAdapter,
        'hubspot': HubSpotAdapter,
        'pipedrive': PipedriveAdapter,
        'dynamics': DynamicsAdapter,
        'ikarusdelta': IkarusDeltaAdapter,
    }

    @classmethod
    def get_adapter(cls, crm_type: str, config: dict) -> BaseAdapter:
        """
        Instantiates the adapter with the provided configuration.
        """
        adapter_class = cls.ADAPTER_MAP.get(crm_type)
        if not adapter_class:
            raise ValueError(f"No adapter implementation for {crm_type}")
        
        adapter = adapter_class(config)
        adapter.authenticate()
        return adapter


