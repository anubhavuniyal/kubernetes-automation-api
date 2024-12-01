from fastapi import FastAPI
from views import app
from fastapi.responses import RedirectResponse


api = FastAPI(title="Kubernetes Management API", version="1.0")
api.include_router(app)
