from typing import List, Dict, Any
import requests
from .base_adapter import BaseAdapter
from canonical_model import Contact, FileAttachment

class MondayAdapter(BaseAdapter):
    """
    Adapter for Monday.com (GraphQL API).
    """
    API_URL = "https://api.monday.com/v2"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_token = config.get("api_token")
        self.board_id = config.get("board_id")
        self.field_mapping = config.get("field_mapping", {})

    def authenticate(self) -> bool:
        if not self.api_token or not self.board_id:
            print("Monday.com credentials incomplete. Running in MOCK mode.")
            return False
        return True


    def push_contact(self, contact: Contact, target: str = None) -> str:
        import json        
        target_board_id = target if target else self.board_id
        if not target_board_id:
             raise ValueError("Monday Board ID not provided in URL or Config.")

        column_values = {}
        flat_contact = contact.dict()
        flat_contact.update(contact.custom_fields)
        name_field_key = None
        for key, monday_col in self.field_mapping.items():
            if monday_col == "name":
                name_field_key = key
                break
        
        # If we found a key mapped to "Name", use its value
        item_name = None
        if name_field_key and name_field_key in flat_contact:
            item_name = flat_contact[name_field_key]
        
        if not item_name:
             raise ValueError("Monday Item Name ('name') not mapped in configuration.")
        
        # Map everything else
        for key, value in flat_contact.items():
            if key == name_field_key: 
                continue
            
            if key in ['id', 'created_at', 'updated_at', 'raw_data', 'custom_fields', 'files']:
                continue

            if key in self.field_mapping:
                monday_col_id = self.field_mapping[key]
                                
                if isinstance(value, dict):
                    value = self.format_dict_to_string(value)
                
                column_values[monday_col_id] = value

        if not self.api_token:
            print(f"[MOCK] Pushing to Monday Board {target_board_id}: {item_name}, Cols: {column_values}")
            return "MOCK_MON_ITEM_123"

        # GraphQL Mutation
        query = """
        mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
            create_item (board_id: $board_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """
        
        variables = {
            "board_id": int(target_board_id),
            "item_name": item_name,
            "column_values": json.dumps(column_values)
        }
        
        headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                self.API_URL, 
                json={'query': query, 'variables': variables}, 
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise Exception(f"Monday API Errors: {data['errors']}")
                
            return data['data']['create_item']['id']
            
        except Exception as e:
            print(f"Error creating Monday Item: {e}")
            raise

    def upload_files(self, remote_id: str, files: List[Any]) -> None:
        """
        Uploads files to a Monday.com item.
        Requires 'file_column_id' in field_mapping or a default column.
        """
        import base64
        
        file_column_id = self.field_mapping.get("files", "files") 
        if file_column_id == "files" and "files" not in self.field_mapping:
             print("[WARNING] defaulting to 'files' column ID. If your column has a different ID, please map 'files' in DB.") 

        url = "https://api.monday.com/v2/file"
        headers = {
            "Authorization": self.api_token
        }

        if not self.api_token:
            print(f"[MOCK] Uploading file {files[0].filename} to Monday Item {remote_id} on Column {file_column_id}")
            return

        for file_obj in files:
            try:
                
                # Decode Base64
                file_content = base64.b64decode(file_obj.content_base64)
                
                # Monday expects item_id as Int
                try:
                    item_id_int = int(remote_id)
                except ValueError:
                    print(f"Error: Monday Item ID {remote_id} is not an integer.")
                    continue
                
                import json
                                
                mutation = f'mutation add_file($file: File!) {{ add_file_to_column (item_id: {item_id_int}, column_id: "{file_column_id}", file: $file) {{ id }} }}'
                map_json = json.dumps({"image": "variables.file"})

                multipart_operations = [
                    ('query', (None, mutation)),
                    ('map', (None, map_json)),
                    ('image', (file_obj.filename, file_content, file_obj.mime_type or 'application/octet-stream'))
                ]

                auth_headers = {"Authorization": self.api_token}
                
                response = requests.post(
                    url, 
                    headers=auth_headers,
                    files=multipart_operations,
                    timeout=30
                )
                

                
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    print(f"Error uploading file {file_obj.filename} to Monday: {data['errors']}")
                else:
                    pass

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Failed to upload {file_obj.filename}: {e}")

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        """
        Fetches the columns (schema) for a specific Monday.com Board (by ID).
        """
        board_id = target if target else self.board_id
        if not board_id:
             raise ValueError("Monday Board ID not provided.")

        if not self.api_token:
             print(f"[MOCK] Fetching schema for Monday Board: {board_id}")
             return [
                 {"label": "Item Name", "value": "name", "type": "name"},
                 {"label": "Status", "value": "status", "type": "status"},
                 {"label": "Date", "value": "date", "type": "date"},
                 {"label": "Text Column", "value": "text", "type": "text"}
             ]

        query = """
        query ($ids: [ID!]) {
            boards (ids: $ids) {
                columns {
                    id
                    title
                    type
                }
            }
        }
        """
        
        variables = {"ids": [int(board_id)]}
        headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                self.API_URL, 
                json={'query': query, 'variables': variables}, 
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise ValueError(f"Monday API Errors: {data['errors']}")
            
            boards = data.get('data', {}).get('boards', [])
            if not boards:
                raise ValueError(f"Monday Board {board_id} not found.")
                
            columns = boards[0].get('columns', [])
            
            fields = []
            for col in columns:
                fields.append({
                    "label": col['title'],
                    "value": col['id'],
                    "type": col['type']
                })
            
            return sorted(fields, key=lambda x: x['label'])

        except Exception as e:
            print(f"Error fetching Monday schema: {e}")
            raise
