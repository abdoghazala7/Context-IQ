from fastapi import FastAPI
from routes.base import base_router
from routes.upload import Upload_router

app = FastAPI()

app.include_router(base_router)
app.include_router(Upload_router)