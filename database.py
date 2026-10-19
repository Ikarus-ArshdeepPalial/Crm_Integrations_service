import os
import boto3
from typing import Dict, Any
from botocore.exceptions import ClientError
from encryption import encrypt_secrets , decrypt_secrets

def get_db_table():
    """
    Returns the DynamoDB table resource.
    """
    dynamodb = boto3.resource("dynamodb")
    table_name = os.environ.get("DYNAMODB_TABLE", "crm-connector-configs")
    return dynamodb.Table(table_name)

def get_user_crm_config(organization_id: str, crm_name: str) -> Dict[str, Any]:
    """
    Fetches the CRM configuration for a specific user and CRM from DynamoDB.
    """
    table = get_db_table()
    response = table.get_item(Key={"organization_id": organization_id})
    item = response.get("Item")
    
    if not item:
        raise ValueError(f"User {organization_id} not found.")

    configs = item.get("configs", {})
    crm_config = configs.get(crm_name)
    
    if not crm_config:
        raise ValueError(f"Configuration for {crm_name} not found for user {organization_id}.")

    crm_config = decrypt_secrets(crm_config)

    if "secret" in crm_config or "public" in crm_config or "secrets" in crm_config:
        flat_config = {}
        flat_config.update(crm_config.get("public", {}))
        flat_config.update(crm_config.get("secret", {}))
        flat_config.update(crm_config.get("secrets", {}))
        for k, v in crm_config.items():
            if k not in ["secret", "public", "secrets"]:
                flat_config[k] = v
        return flat_config
        
    return crm_config

def create_user_crm_config(organization_id: str, crm_name: str, config_data: Dict[str, Any]) -> None:
    """
    Creates (or overwrites) the CRM configuration for a specific user and CRM.
    DynamoDB 'update_item' acts as an upsert.
    """
    table = get_db_table()
    encrypted_config = encrypt_secrets(config_data)

    try:
        table.update_item(
            Key={"organization_id": organization_id},
            UpdateExpression="SET configs.#crm = :val",
            ConditionExpression="attribute_not_exists(configs.#crm)",
            ExpressionAttributeNames={"#crm": crm_name},
            ExpressionAttributeValues={":val": encrypted_config}
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
             raise ValueError(f"Configuration for {crm_name} already exists for user.")
        
        # If 'configs' map doesn't exist, DynamoDB throws ValidationException
        if e.response['Error']['Code'] == 'ValidationException':
            initial_map = {crm_name: encrypted_config}
            table.update_item(
                Key={"organization_id": organization_id},
                UpdateExpression="SET configs = :val",
                ExpressionAttributeValues={":val": initial_map}
            )
        else:
            raise e

def update_user_crm_config(organization_id: str, crm_name: str, config_data: Dict[str, Any]) -> None:
    """
    Updates an EXISTING CRM configuration. Raises error if user/config does not exist.
    """
    table = get_db_table()
    encrypted_config = encrypt_secrets(config_data)
    
    try:
        table.update_item(
            Key={"organization_id": organization_id},
            UpdateExpression="SET configs.#crm = :val",
            ConditionExpression="attribute_exists(configs)",
            ExpressionAttributeNames={"#crm": crm_name},
            ExpressionAttributeValues={":val": encrypted_config}
        )
    except boto3.client("dynamodb").exceptions.ConditionalCheckFailedException:
         raise ValueError(f"User not found. Cannot update configuration.")

def patch_user_crm_config(organization_id: str, crm_name: str, config_data: Dict[str, Any]) -> None:
    """
    Partially updates an EXISTING CRM configuration.
    Only updates the top-level keys provided in config_data (e.g., 'public', 'secrets').
    """
    table = get_db_table()
    encrypted_data = encrypt_secrets(config_data)
    
    update_parts = []
    expr_attr_names = {"#crm": crm_name}
    expr_attr_values = {}
    
    for key, value in encrypted_data.items():
        key_placeholder = f"#{key}"
        val_placeholder = f":{key}"
        
        update_parts.append(f"configs.#crm.{key_placeholder} = {val_placeholder}")
        expr_attr_names[key_placeholder] = key
        expr_attr_values[val_placeholder] = value
        
    if not update_parts:
        return
        
    update_expression = "SET " + ", ".join(update_parts)
    
    try:
        table.update_item(
            Key={"organization_id": organization_id},
            UpdateExpression=update_expression,
            ConditionExpression="attribute_exists(configs.#crm)",
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
             raise ValueError(f"Configuration for {crm_name} not found for user. Cannot patch.")
        raise e

def delete_user_crm_config(organization_id: str, crm_name: str) -> None:
    """
    Deletes the configuration for a specific CRM and user.
    """
    table = get_db_table()
    
    table.update_item(
        Key={"organization_id": organization_id},
        UpdateExpression="REMOVE configs.#crm",
        ExpressionAttributeNames={"#crm": crm_name}
    )

def get_all_user_configs(organization_id: str) -> Dict[str, Any]:
    """
    Returns the entire configuration dictionary for a user (all CRMs).
    """
    table = get_db_table()
    response = table.get_item(Key={"organization_id": organization_id})
    item = response.get("Item")
    
    if not item:
        raise ValueError(f"User {organization_id} not found.")
        
    configs = item.get("configs", {})

    public_configs = {}
    for crm, data in configs.items():
        if isinstance(data, dict):
            public_configs[crm] = {
                k: v for k, v in data.items() 
                if k not in ["secret", "secrets"]
            }
        else:
            public_configs[crm] = data
            
    return public_configs
