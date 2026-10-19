from typing import List, Dict, Any
from simple_salesforce import Salesforce
from .base_adapter import BaseAdapter
from canonical_model import Contact

class SalesforceAdapter(BaseAdapter):
    """
    Adapter for Salesforce CRM.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.username = config.get("username")
        self.password = config.get("password")
        self.security_token = config.get("security_token", "")
        self.session_id = config.get("session_id")
        self.instance_url = config.get("instance_url")
        # OAuth Credentials
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        
        self.object_name = config.get("object_name")
        self.domain = config.get("domain", "login")
        self.client = None

    def authenticate(self) -> bool:
        try:
            # this if is only for devlopement , else part for production
            if self.username and self.password and self.client_id and self.client_secret:
                import requests                
                login_domain = self.domain if self.domain else "login"
                if "test" in (self.instance_url or ""):
                    login_domain = "test"
                
                token_url = f"https://{login_domain}.salesforce.com/services/oauth2/token"
                
                payload = {
                    'grant_type': 'password',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'username': self.username,
                    'password': f"{self.password}{self.security_token}"
                }
                
                response = requests.post(token_url, data=payload)
                if response.status_code != 200:
                    raise Exception(f"OAuth Error: {response.text}")
                
                data = response.json()
                self.client = Salesforce(
                    instance_url=data['instance_url'],
                    session_id=data['access_token']
                )
            else:
                print("[Mock] Salesforce credentials incomplete.")
                return False
                
            return True
        except Exception as e:
            print(f"Salesforce Auth Failed: {e}")
            raise


    def push_contact(self, contact: Contact, target: str = None) -> str:
        sobject_name = target if target else self.object_name
        if not sobject_name:
             raise ValueError("Salesforce Object Name not provided in URL or Config.")
        
        sf_contact = {}
        
        # Flatten contact data
        flat_contact = contact.dict()
        flat_contact.update(contact.custom_fields)

        field_mapping = self.config.get('field_mapping', {})
        lastname_key = None
        for key, crm_field in field_mapping.items():
            if crm_field == "LastName":
                lastname_key = key
                break
        
        if lastname_key and lastname_key in flat_contact:
             sf_contact['LastName'] = flat_contact[lastname_key]
        elif sobject_name in ['Contact', 'Lead']:
            if contact.last_name:
                sf_contact['LastName'] = contact.last_name
            else:
                 sf_contact['LastName'] = "Unknown"

        if contact.first_name:
            sf_contact['FirstName'] = contact.first_name

        # Map everything else
        for key, value in flat_contact.items():
            if key == lastname_key: 
                continue 
            
            if key in ['id', 'created_at', 'updated_at', 'raw_data', 'custom_fields', 'first_name', 'last_name', 'files']:
                continue

            if key in field_mapping:
                crm_field = field_mapping[key]
                if isinstance(value, dict):
                    value = self.format_dict_to_string(value)
                sf_contact[crm_field] = value
                
        if not self.client:
            print(f"[MOCK] Pushing to Salesforce: {sf_contact}")
            return "MOCK_SF_ID_123"

        try:
            sobject = getattr(self.client, sobject_name)
            result = sobject.create(sf_contact)
            return result['id']
        except Exception as e:
            print(f"Error creating Salesforce Contact: {e}")
            raise

    def upload_files(self, remote_id: str, files: List[Any]) -> None:
        """
        Uploads files to Salesforce (ContentVersion) and links them (ContentDocumentLink) to the Contact.
        """
        if not self.client:
           print(f"[MOCK] Uploading {len(files)} files to Salesforce ID {remote_id}")
           return

        for file_obj in files:
            try:
                cv_payload = {
                    'Title': file_obj.filename,
                    'PathOnClient': file_obj.filename,
                    'VersionData': file_obj.content_base64,
                    'IsMajorVersion': True
                }
                
                cv = self.client.ContentVersion.create(cv_payload)
                cv_id = cv['id']
                cv_query = self.client.query(f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{cv_id}'")
                content_document_id = cv_query['records'][0]['ContentDocumentId']
                
                cdl_payload = {
                    'ContentDocumentId': content_document_id,
                    'LinkedEntityId': remote_id,
                    'ShareType': 'V',
                    'Visibility': 'AllUsers'
                }
                
                self.client.ContentDocumentLink.create(cdl_payload)
                pass

            except Exception as e:
                print(f"Failed to upload {file_obj.filename} to Salesforce: {e}")

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Fetches the fields for a specific Salesforce Object using the Describe API.
        """
        object_name = target if target else self.object_name
        if not object_name:
            raise ValueError("Salesforce Object Name not provided.")

        if not self.client:
             # Mock response for testing without credentials
             print(f"[MOCK] Fetching schema for Salesforce Object: {object_name}")
             return [
                 {"label": "First Name", "value": "FirstName", "type": "string"},
                 {"label": "Last Name", "value": "LastName", "type": "string"},
                 {"label": "Email", "value": "Email", "type": "email"},
                 {"label": "Business Phone", "value": "Phone", "type": "phone"},
                 {"label": "Mailing City", "value": "MailingCity", "type": "string"}
             ]

        try:
            # simple-salesforce describe call
            # getattr(self.client, object_name) gives us the resource, then .describe()
            sobject = getattr(self.client, object_name)
            description = sobject.describe()
            
            fields = []
            for field in description.get("fields", []):
                # Filter out fields that are likely not useful for mapping (system fields)
                # You can adjust this filter as needed.
                if not field['createable'] and not field['updateable']:
                    continue
                
                fields.append({
                    "label": field['label'],
                    "value": field['name'],
                    "type": field['type']
                })
            
            return sorted(fields, key=lambda x: x['label'])

        except Exception as e:
            print(f"Error fetching Salesforce schema: {e}")
            raise

