from fastapi import FastAPI
from routes.base import Base_router
from routes.upload import Data_router

app = FastAPI()

app.include_router(Base_router)
app.include_router(Data_router)