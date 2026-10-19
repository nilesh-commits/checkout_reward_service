"""FastAPI application entrypoint.

On startup we create tables (metadata.create_all) and seed products. We use
create_all + an idempotent seed instead of Alembic to stay inside the timebox;
the trade-off and migration path are documented in DECISIONS.md.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import Base, SessionLocal, engine
from .errors import DomainError
from .routers import admin, carts, checkout, orders, products
from .seed import seed_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_products(session)
    yield
    await engine.dispose()


app = FastAPI(title="Checkout & Rewards Service", version="1.0.0", lifespan=lifespan)

# Permissive CORS so the React dev server can call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


app.include_router(products.router)
app.include_router(carts.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(admin.router)
