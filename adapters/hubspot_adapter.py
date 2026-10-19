from typing import List, Dict, Any
import requests
from .base_adapter import BaseAdapter
from canonical_model import Contact

class HubSpotAdapter(BaseAdapter):
    """
    Adapter for HubSpot CRM (API v3).
    """
    API_BASE_URL = "https://api.hubapi.com/crm/v3/objects"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config.get("access_token")
        self.object_type = config.get("object_type")
        self.field_mapping = config.get("field_mapping", {})

    def authenticate(self) -> bool:
        if not self.access_token:
            print("HubSpot credentials incomplete. Running in MOCK mode.")
            return False
        return True


    def push_contact(self, contact: Contact, target: str = None) -> str:
        object_type = target if target else self.object_type
        if not object_type:
             raise ValueError("HubSpot Object Type not provided in Configuration.")
        
        properties = {}
        
        flat_contact = contact.dict()
        flat_contact.update(contact.custom_fields)
        
        for key, value in flat_contact.items():
            if key in ['id', 'created_at', 'updated_at', 'raw_data', 'custom_fields', 'files']:
                continue 

            if key in self.field_mapping:
                hs_field = self.field_mapping[key]
                if isinstance(value, dict):
                    value = self.format_dict_to_string(value)
                elif isinstance(value, list):
                    try:
                       value = ";".join([str(v) for v in value])
                    except:
                       value = str(value)

                properties[hs_field] = value
        
        if not properties:
            raise ValueError("No fields mapped for HubSpot push. Please check 'field_mapping'.")

        for key, val in properties.items():
            if isinstance(val, str) and "\n" in val and ":" in val:
                 pass

        if not self.access_token:
            print(f"[MOCK] Pushing to HubSpot ({object_type}): {properties}")
            return "MOCK_HS_ID_123"

        url = f"{self.API_BASE_URL}/{object_type}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json={"properties": properties}, headers=headers)
            
            if response.status_code == 409:
                error_msg = response.json().get('message', 'Contact already exists.')
                raise ValueError(f"HubSpot Conflict: {error_msg}")
            
            response.raise_for_status()
            data = response.json()
            return data['id']
            
        except requests.exceptions.HTTPError as e:
            print(f"HubSpot API Error: {e.response.text}")
            raise ValueError(f"HubSpot API Error: {e.response.text}")
        except Exception as e:
            print(f"Error creating HubSpot Object: {e}")
            raise

    def upload_files(self, remote_id: str, files: List[Any]) -> None:
        """
        Uploads files to HubSpot and attaches them to the Contact via a Note.
        """
        import base64
        import json
        
        upload_url = "https://api.hubapi.com/files/v3/files"
        note_url = "https://api.hubapi.com/crm/v3/objects/notes"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        if not self.access_token:
            print(f"[MOCK] Uploading {len(files)} files to HubSpot Contact {remote_id}")
            return

        for file_obj in files:
            try:

                file_content = base64.b64decode(file_obj.content_base64)
                
                multipart_data = [
                    ('file', (file_obj.filename, file_content, file_obj.mime_type or 'application/octet-stream')),
                    ('options', (None, json.dumps({
                        "access": "PRIVATE",
                        "overwrite": False,
                        "duplicateValidationStrategy": "NONE",
                        "duplicateValidationScope": "ENTIRE_PORTAL"
                    }))),
                    ('folderPath', (None, '/ikarus_imports'))
                ]
                
                upload_res = requests.post(upload_url, headers=headers, files=multipart_data, timeout=30)
                upload_res.raise_for_status()
                file_id = upload_res.json()['id']

                import time
                current_time_ms = str(int(time.time() * 1000))

                note_payload = {
                    "properties": {
                        "hs_timestamp": current_time_ms, 
                        "hs_note_body": f"Imported File: {file_obj.filename}",
                        "hs_attachment_ids": file_id
                    },
                    "associations": [
                        {
                            "to": {"id": remote_id},
                            "types": [
                                {
                                    "associationCategory": "HUBSPOT_DEFINED",
                                    "associationTypeId": 202 
                                }
                            ]
                        }
                    ]
                }
                
                note_headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                }
                
                note_res = requests.post(note_url, json=note_payload, headers=note_headers, timeout=10)
                
                
                if note_res.status_code != 201 and note_res.status_code != 200:
                    print(f"HubSpot Note Creation Failed: {note_res.text}")

                note_res.raise_for_status()
                pass
                
                try:
                    file_url = upload_res.json().get('url')
                    if file_url:
                        update_url = f"{self.API_BASE_URL}/{self.object_type}/{remote_id}"
                        update_payload = {
                            "properties": {
                                "files": file_url
                            }
                        }
                        requests.patch(update_url, json=update_payload, headers=note_headers)
                        pass
                except Exception as update_e:
                    print(f"Could not update 'files' column: {update_e}")

            except Exception as e:
                print(f"Failed to upload/attach {file_obj.filename} to HubSpot: {e}")

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Fetches the fields for a specific HubSpot Object using the CRM Properties API.
        """
        object_type = target if target else self.object_type
        if not object_type:
            raise ValueError("HubSpot Object Type not provided.")

        if not self.access_token:
            print(f"[MOCK] Fetching schema for HubSpot Object: {object_type}")
            return [
                 {"label": "First Name", "value": "firstname", "type": "string"},
                 {"label": "Last Name", "value": "lastname", "type": "string"},
                 {"label": "Email", "value": "email", "type": "string"},
                 {"label": "Phone", "value": "phone", "type": "string"},
                 {"label": "Website", "value": "website", "type": "string"}
             ]

        url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            fields = []
            for prop in data.get("results", []):
                fields.append({
                    "label": prop['label'],
                    "value": prop['name'],
                    "type": prop['type']
                })
            
            return sorted(fields, key=lambda x: x['label'])

        except requests.exceptions.HTTPError as e:
            print(f"HubSpot API Error fetching schema: {e.response.text}")
            raise ValueError(f"HubSpot API Error: {e.response.text}")
        except Exception as e:
            print(f"Error fetching HubSpot schema: {e}")
            raise
