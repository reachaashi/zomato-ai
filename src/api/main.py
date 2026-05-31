"""FastAPI application entrypoint (architecture §8.1, Phase P3)."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

from src.utils.logging_config import setup_logging, set_request_id, clear_request_id
from src.data.ingestion import load_and_index
from src.api.routes import router

# Configure structured logging with request ID filters
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load dataset and build index on startup
    logger.info("Initializing restaurant index...")
    try:
        load_and_index()
        logger.info("Restaurant index successfully initialized.")
    except Exception as e:
        logger.exception("Failed to initialize restaurant index on startup: %s", e)
    yield


app = FastAPI(
    title="Zomato AI Restaurant Recommendation API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    client_req_id = request.headers.get("X-Request-ID")
    req_id = set_request_id(client_req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        clear_request_id()


app.include_router(router)

