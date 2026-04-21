from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.store.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 设置模板目录
templates = Jinja2Templates(directory="templates")


# HTML页面路由
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# 注册路由
from app.api.conversations import router as conversations_router
from app.api.mcp import router as mcp_router
from app.api.skills import router as skills_router

app.include_router(conversations_router)
app.include_router(mcp_router)
app.include_router(skills_router)
