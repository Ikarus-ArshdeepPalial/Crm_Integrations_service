from typing import List, Dict, Any
import requests
from .base_adapter import BaseAdapter
from canonical_model import Contact

class DynamicsAdapter(BaseAdapter):
    """
    Adapter for Microsoft Dynamics 365
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.tenant_id = config.get("tenant_id")
        self.resource_url = config.get("resource_url")
        self.object_type = config.get("object_type")
        self.field_mapping = config.get("field_mapping", {})
        self._access_token = None

    def _get_access_token(self) -> str:
        """
        Exchanges Client Credentials for a Bearer Token.
        """
        if self._access_token:
            return self._access_token
            
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": f"{self.resource_url}/.default"
        }
        
        resp = requests.post(token_url, data=data)
        resp.raise_for_status()
        self._access_token = resp.json().get("access_token")
        return self._access_token

    def authenticate(self) -> bool:
        if not (self.client_id and self.client_secret and self.tenant_id and self.resource_url):
            print("Dynamics credentials incomplete.")
            return False
        try:
            self._get_access_token()
            return True
        except Exception as e:
            print(f"Dynamics Auth Failed: {e}")
            return False


    def push_contact(self, contact: Contact, target: str = None) -> str:
        entity_set_name = target if target else self.object_type
        if not entity_set_name:
             raise ValueError("Dynamics Entity Set Name (e.g. 'contacts') not provided.")
        
        if not (self.client_id and self.client_secret):
             print(f"[MOCK] Pushing to Dynamics ({entity_set_name})")
             return "MOCK_DYN_GUID_123"

        payload = {}
        flat_contact = contact.dict()
        flat_contact.update(contact.custom_fields)
        
        for key, value in flat_contact.items():
            if key in self.field_mapping:
                dyn_field = self.field_mapping[key]
                if isinstance(value, dict):
                    value = self.format_dict_to_string(value)
                payload[dyn_field] = value
                
        if not payload:
            raise ValueError("No fields mapped for Dynamics 365.")

        try:
            token = self._get_access_token()
            url = f"{self.resource_url.rstrip('/')}/api/data/v9.2/{entity_set_name}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if 'OData-EntityId' in response.headers:
                 return response.headers['OData-EntityId']
            
            return str(data.get(f"{entity_set_name[:-1]}id", "CREATED"))

        except requests.exceptions.HTTPError as e:
            print(f"Dynamics API Error: {e.response.text}")
            raise
        except Exception as e:
            print(f"Error creating Dynamics Record: {e}")
            raise

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Fetches the fields for a specific Dynamics 365 Entity using the Metadata API.
        """
        entity_name = target if target else self.object_type
        if not entity_name:
             raise ValueError("Dynamics Entity Name not provided.")

        if not (self.client_id and self.client_secret):
             print(f"[MOCK] Fetching schema for Dynamics Entity: {entity_name}")
             return [
                 {"label": "First Name", "value": "firstname", "type": "String"},
                 {"label": "Last Name", "value": "lastname", "type": "String"},
                 {"label": "Job Title", "value": "jobtitle", "type": "String"},
                 {"label": "Email", "value": "emailaddress1", "type": "String"}
             ]

        try:
            token = self._get_access_token()
            
            # Dynamics Metadata API to get attributes
            # We filter for attributes that have a DisplayName (label)
            url = f"{self.resource_url.rstrip('/')}/api/data/v9.2/EntityDefinitions(LogicalName='{entity_name}')/Attributes"
            params = {
               "$select": "LogicalName,DisplayName,AttributeType",
               "$filter": "DisplayName ne null"
            }
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            fields = []
            for attr in data.get('value', []):
                
                # Extract localized label
                display_name = attr.get('DisplayName', {}).get('UserLocalizedLabel', {}).get('Label')
                if not display_name:
                    continue
                    
                fields.append({
                    "label": display_name,
                    "value": attr['LogicalName'],
                    "type": attr['AttributeType']
                })
            
            return sorted(fields, key=lambda x: x['label'])

        except requests.exceptions.HTTPError as e:
            print(f"Dynamics API Error fetching schema: {e.response.text}")
            raise ValueError(f"Dynamics API Error: {e.response.text}")
        except Exception as e:
            print(f"Error fetching Dynamics schema: {e}")
            raise
