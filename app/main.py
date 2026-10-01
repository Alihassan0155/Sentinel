from fastapi import FastAPI

from app.database import Base, engine
from app.models import WatchSource
from app.api.watches import router as watches_router
from app.api.changes import router as changes_router
from app.api.profile import router as profile_router
from app.services.scheduler import start_scheduler

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Sentinel",
    description="Autonomous Personal Intelligence Agent",
    version="0.1.0",
)

app.include_router(watches_router)
app.include_router(changes_router)
app.include_router(profile_router)
start_scheduler()

@app.get("/")
def root():
    return {
        "name": "Sentinel",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}