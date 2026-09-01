from fastapi import FastAPI

from app.web.routes.overview import router as overview_router

app = FastAPI(title="OneView Learning Analytics")

app.include_router(overview_router)
