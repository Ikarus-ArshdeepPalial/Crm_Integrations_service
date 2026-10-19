import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from pydantic import BaseModel
from canonical_model import Contact
from services import BrokerService
import database
from mangum import Mangum
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CRM Connector")

AUTH_EXCLUDED_PATHS = ["/"]

# middleware for debugging only
# @app.middleware("http")
# async def log_exceptions_middleware(request: Request, call_next):
#     try:
#         return await call_next(request)
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         print(f"CRITICAL ERROR: {str(e)}")
#         return JSONResponse(
#             status_code=500,
#             content={"detail": "Internal Server Error", "error": str(e), "traceable": traceback.format_exc()}
#         )

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Checks if the request has a valid SECRET-TOKEN header.
    """
    if request.url.path in AUTH_EXCLUDED_PATHS or request.method == "OPTIONS":
        return await call_next(request)

    expected_token = os.environ.get("SECRET_TOKEN")
    if not expected_token:
        return JSONResponse(
            status_code=500, 
            content={"detail": "Server misconfiguration: SECRET_TOKEN env var not set."}
        )
    
    client_token = request.headers.get("SECRET-TOKEN")
    if client_token != expected_token:
         return JSONResponse(
            status_code=401, 
            content={"detail": "Invalid or missing SECRET-TOKEN."}
        )
        
    response = await call_next(request)
    return response

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://app.ikarusdelta.com",
    "https://beta-app.ikarusdelta.com",
    "https://beta-viewer.ikarusdelta.com",
    "https://viewer.ikarusdelta.com",
    "https://ksd5jkgg-3000.inc1.devtunnels.ms",
    "https://38vv8q64-3000.inc1.devtunnels.ms"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    """
    Simple health check to verify the app is running.
    """
    return {"status": "ok", "message": "CRM Connector is running"}

class UserSyncRequest(BaseModel):
    organization_id: str
    product_id: Optional[str] = None
    data: Contact

@app.post("/api/sync/{crm_name}")
def sync_to_crm(crm_name: str, payload: UserSyncRequest):
    """
    Syncs the provided contact data to the specified CRM using user-specific config.
    """
    try:
        payload.data.custom_fields["organization_id"] = payload.organization_id
        if payload.product_id:
            payload.data.custom_fields["product_id"] = payload.product_id

        config = database.get_user_crm_config(payload.organization_id, crm_name.lower())
        adapter = BrokerService.get_adapter(crm_name.lower(), config)
        remote_id = adapter.push_contact(payload.data)
        
        if payload.data.files:
            adapter.upload_files(remote_id, payload.data.files)

        return {
            "organization_id":payload.organization_id,
            "status": "success", 
            "crm": crm_name, 
            "remote_id": remote_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")



class UserConfigRequest(BaseModel):
    organization_id: str
    config: Dict[str, Any]

@app.post("/api/config/{crm_name}")
def create_crm_config(crm_name: str, payload: UserConfigRequest):
    """
    Creates the configuration for a specific CRM and user.
    """
    try:
        database.create_user_crm_config(payload.organization_id, crm_name.lower(), payload.config)
        return {
            "status": "success",
            "message": f"Configuration for {crm_name} created for user {payload.organization_id}"
        }
    except ValueError as e:
        if "already exists" in str(e):
             raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create config: {str(e)}")

@app.patch("/api/config/{crm_name}")
def patch_crm_config(crm_name: str, payload: UserConfigRequest):
    """
    Partially updates an EXISTING configuration 
    """
    try:
        database.patch_user_crm_config(payload.organization_id, crm_name.lower(), payload.config)
        return {
            "status": "success",
            "message": f"Configuration for {crm_name} patched for user {payload.organization_id}"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to patch config: {str(e)}")

class UserDeleteRequest(BaseModel):
    organization_id: str

@app.delete("/api/config/{crm_name}")
def delete_crm_config(crm_name: str, payload: UserDeleteRequest):
    """
    Deletes the configuration for a specific CRM.
    """
    try:
        database.delete_user_crm_config(payload.organization_id, crm_name.lower())
        return {
            "status": "success",
            "message": f"Configuration for {crm_name} deleted for user {payload.organization_id}"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete config: {str(e)}")

@app.get("/api/config/{organization_id}")
def get_user_configs(organization_id: str):
    """
    Retrieves ALL CRM configurations for a specific user.
    """
    try:
        configs = database.get_all_user_configs(organization_id)
        return {
            "organization_id": organization_id,
            "configs": configs
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch configs: {str(e)}")

class MetadataRequest(BaseModel):
    organization_id: str
    object_type: str
    secrets: Optional[Dict[str, Any]] = None

class TestSyncRequest(BaseModel):
    organization_id: Optional[str] = None
    product_id: Optional[str] = None
    data: Contact
    secrets: Dict[str, Any]
    public: Dict[str, Any]

@app.post("/api/test-sync/{crm_name}")
def test_sync_to_crm(crm_name: str, payload: TestSyncRequest):
    """
    Test endpoint to sync contact data to CRM using provided secrets and public config.
    """
    try:
        if payload.organization_id:
            payload.data.custom_fields["organization_id"] = payload.organization_id
        if payload.product_id:
            payload.data.custom_fields["product_id"] = payload.product_id

        # Build config with secrets and public data
        config = payload.secrets.copy()
        config.update(payload.public)

        # Get adapter and push contact
        adapter = BrokerService.get_adapter(crm_name.lower(), config)
        remote_id = adapter.push_contact(payload.data)
        
        # Upload files if present
        if payload.data.files:
            adapter.upload_files(remote_id, payload.data.files)

        return {
            "status": "success", 
            "crm": crm_name, 
            "remote_id": remote_id,
            "message": "Test sync successful"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test sync failed: {str(e)}")

@app.post("/api/metadata/{crm_name}")
def get_metadata(crm_name: str, payload: MetadataRequest):
    """
    Retrieves the field schema for a specific CRM object/board.
    """
    try:
        if payload.secrets:
            config = payload.secrets
        else:
            config = database.get_user_crm_config(payload.organization_id, crm_name.lower())
        adapter = BrokerService.get_adapter(crm_name.lower(), config)
        adapter.authenticate()
        
        # 4. Fetch Schema
        schema = adapter.get_model_schema(payload.object_type)
        
        return {
            "crm": crm_name,
            "object_type": payload.object_type,
            "fields": schema
        }
        
    except ValueError as e:
         raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
         import traceback
         traceback.print_exc()
         raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {str(e)}")

handler = Mangum(app)
