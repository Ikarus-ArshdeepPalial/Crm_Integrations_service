from typing import List, Dict, Any
import requests
from .base_adapter import BaseAdapter
from canonical_model import Contact

class PipedriveAdapter(BaseAdapter):
    """
    Adapter for Pipedrive CRM (REST API v1).
    Auth: API Token via Query Parameter.
    """
    API_BASE_URL = "https://api.pipedrive.com/v1"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_token = config.get("api_token")
        self.object_type = config.get("object_type")
        self.field_mapping = config.get("field_mapping", {})

        if self.object_type == "deals" and "title" not in self.field_mapping:
            self.field_mapping["title"] = "title"
        
        if "files" not in self.field_mapping:
            self.field_mapping["files"] = "files"

    def authenticate(self) -> bool:
        if not self.api_token:
            print("[Mock] Pipedrive credentials incomplete.")
            return False
        return True


    def push_contact(self, contact: Contact, target: str = None) -> str:
        endpoint = target if target else self.object_type
        if not endpoint:
             raise ValueError("Pipedrive Object Type (e.g. 'persons') not provided in keys.")
        
        if not self.api_token:
            print(f"[MOCK] Pushing to Pipedrive ({endpoint}).")
            return "MOCK_PD_ID_456"

        payload = {}
        
        # Flatten contact data
        flat_contact = contact.dict()
        flat_contact.update(contact.custom_fields)
        
        # Strict mapping required
        for key, value in flat_contact.items():
             if key == 'files':
                 continue

             if key in self.field_mapping:
                 pd_field = self.field_mapping[key]
                 if isinstance(value, dict):
                     value = self.format_dict_to_string(value)
                 payload[pd_field] = value
        
        if "title" not in payload:
            payload["title"] = "Title"

        if not payload:
            raise ValueError("No fields mapped for Pipedrive.")

        url = f"{self.API_BASE_URL}/{endpoint}"
        params = {"api_token": self.api_token}
        
        try:
            response = requests.post(url, params=params, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data.get('data', {}).get('id', 'UNKNOWN'))
            
        except requests.exceptions.HTTPError as e:
            print(f"Pipedrive API Error: {e.response.text}")
            raise
        except Exception as e:
            print(f"Error creating Pipedrive Record: {e}")
            raise

    def upload_files(self, remote_id: str, files: List[Any]) -> None:
        """
        Uploads files to Pipedrive (POST /files) and links them to the Person/Deal.
        """
        import base64
        
        url = f"{self.API_BASE_URL}/files"
        params = {"api_token": self.api_token}

        if not self.api_token:
            print(f"[MOCK] Uploading {len(files)} files to Pipedrive ID {remote_id}")
            return

        link_key = 'person_id'
        if 'deal' in (self.object_type or "").lower():
            link_key = 'deal_id'

        for file_obj in files:
            try:

                file_content = base64.b64decode(file_obj.content_base64)
                files_payload = {
                    'file': (file_obj.filename, file_content, file_obj.mime_type or 'application/octet-stream')
                }
                
                data_payload = {
                    link_key: remote_id
                }
                
                response = requests.post(
                    url, 
                    params=params, 
                    files=files_payload, 
                    data=data_payload,
                    timeout=30
                )
                
                response.raise_for_status()
                data = response.json()
                
                file_id = data.get('data', {}).get('id')
                pass

            except Exception as e:
                print(f"Failed to upload {file_obj.filename} to Pipedrive: {e}")

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Fetches the fields for a specific Pipedrive Object (persons, deals, organizations).
        """
        endpoint_key = target if target else self.object_type
        if not endpoint_key:
             raise ValueError("Pipedrive Object Type not provided.")
        
        # Pipedrive API endpoints are like /personFields, /dealFields
        # We need to map 'persons' -> 'personFields'
        # Simple heuristic: remove 's' and add 'Fields'
        if endpoint_key.endswith('s'):
            field_endpoint = f"{endpoint_key[:-1]}Fields"
        else:
            field_endpoint = f"{endpoint_key}Fields"

        if not self.api_token:
            print(f"[MOCK] Fetching schema for Pipedrive Endpoint: {field_endpoint}")
            return [
                 {"label": "Name", "value": "name", "type": "varchar"},
                 {"label": "Email", "value": "email", "type": "varchar"},
                 {"label": "Phone", "value": "phone", "type": "varchar"},
                 {"label": "Organization", "value": "org_id", "type": "int"}
             ]

        url = f"{self.API_BASE_URL}/{field_endpoint}"
        params = {"api_token": self.api_token}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('success'):
                 raise ValueError(f"Pipedrive API Failed: {data.get('error')}")

            fields = []
            for field in data.get("data", []):
                fields.append({
                    "label": field['name'],
                    "value": field['key'],
                    "type": field['field_type']
                })
            
            return sorted(fields, key=lambda x: x['label'])

        except requests.exceptions.HTTPError as e:
            print(f"Pipedrive API Error fetching schema: {e.response.text}")
            raise ValueError(f"Pipedrive API Error: {e.response.text}")
        except Exception as e:
            print(f"Error fetching Pipedrive schema: {e}")
            raise
