import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from sqlalchemy import String, Text, DateTime, JSON, Boolean, Integer, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

RUNTIME_DIR = Path.cwd()
CONVERSATIONS_DIR = "conversations"

DB_DIR = RUNTIME_DIR / CONVERSATIONS_DIR
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "business.db"

# Use aiosqlite for async sqlite
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversation"
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "message"
    
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20)) # human, ai, tool
    content: Mapped[str] = mapped_column(Text, default="")
    reasoning_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sub_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class McpServer(Base):
    __tablename__ = "mcp_server"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transport: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    command: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    args: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    env: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    headers: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    cwd: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    session_kwargs: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tools: Mapped[List["McpTool"]] = relationship(
        back_populates="server",
        cascade="all, delete-orphan",
    )


class McpTool(Base):
    __tablename__ = "mcp_tool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("mcp_server.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_schema: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    server: Mapped["McpServer"] = relationship(back_populates="tools")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@asynccontextmanager
async def get_session():
    """Provide a transactional scope around a series of operations."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except:
            await session.rollback()
            raise
