from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import time

app = FastAPI(title="PLERA Live Backend", version="0.1.0")

# -------------------------------------------------------------------
# CORS so Wix / plera.online / vervenveda.online can talk to backend.
# You can set PLERA_CORS_ORIGINS in your host later.
# Example env var:
#   PLERA_CORS_ORIGINS="https://www.vervenveda.com,https://www.plera.online"
# -------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv("PLERA_CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Models — shaped to match your PLERA Live front-end state
# -------------------------------------------------------------------


class User(BaseModel):
    id: str
    name: str
    email: str
    password: str
    bio: Optional[str] = None
    avatar: Optional[str] = None
    # Use default_factory instead of [] so each user gets its own list
    groups: List[str] = Field(default_factory=list)
    notifications: bool = False
    savedPostIds: List[int] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class Post(BaseModel):
    id: int
    userId: str
    authorName: Optional[str] = None
    content: Optional[str] = None
    image: Optional[str] = None
    createdAt: int = Field(default_factory=lambda: int(time.time() * 1000))
    likes: int = 0
    reactions: Dict[str, int] = Field(default_factory=dict)
    groupId: Optional[str] = None


class Event(BaseModel):
    id: int
    title: str
    time: str
    location: str
    capacity: int = 40
    goingIds: List[str] = Field(default_factory=list)
    createdBy: Optional[str] = None


class DmMessage(BaseModel):
    # "from" is a reserved word in Python, so we alias it
    from_: str = Field(..., alias="from")
    text: str
    ts: int


class DmThread(BaseModel):
    contactId: str
    messages: List[DmMessage] = Field(default_factory=list)
    unread: Dict[str, int] = Field(default_factory=dict)


class Dms(BaseModel):
    threads: Dict[str, DmThread] = Field(default_factory=dict)


class State(BaseModel):
    users: List[User] = Field(default_factory=list)
    posts: List[Post] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    dms: Dms = Field(default_factory=Dms)
    tickerLines: List[str] = Field(default_factory=list)


# -------------------------------------------------------------------
# In-memory "DB". In production you’d use Postgres, etc.
# -------------------------------------------------------------------

db = State(
    tickerLines=[
        "PLERA Live · local-first social feed",
        "Remember to take a stretch + water break",
        "Today is a good day to create something small",
    ]
)


def merge_state(incoming: State) -> None:
    """
    Merge a client state into the shared db (simple / naive).
    Good enough for early micro-backend; you can harden later.
    """
    global db

    # Users: upsert by id
    users_by_id = {u.id: u for u in db.users}
    for u in incoming.users:
        users_by_id[u.id] = u
    db.users = list(users_by_id.values())

    # Posts: upsert by id
    posts_by_id = {p.id: p for p in db.posts}
    for p in incoming.posts:
        posts_by_id[p.id] = p
    db.posts = sorted(
        posts_by_id.values(),
        key=lambda p: p.createdAt,
        reverse=True,
    )

    # Events: upsert by id
    events_by_id = {e.id: e for e in db.events}
    for e in incoming.events:
        events_by_id[e.id] = e
    db.events = list(events_by_id.values())

    # DMs: merge threads, append missing messages
    for tid, thread in incoming.dms.threads.items():
        if tid not in db.dms.threads:
            db.dms.threads[tid] = thread
            continue

        existing = db.dms.threads[tid]

        # Index by timestamp + from + text to avoid dupes
        key_existing = {(m.ts, m.from_, m.text) for m in existing.messages}
        for m in thread.messages:
            key = (m.ts, m.from_, m.text)
            if key not in key_existing:
                existing.messages.append(m)

        # Unread: keep max per user
        for uid, count in thread.unread.items():
            prev = existing.unread.get(uid, 0)
            existing.unread[uid] = max(prev, count)

    # Ticker: union + preserve order from db then incoming
    seen = set()
    merged = []
    for line in db.tickerLines + incoming.tickerLines:
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        merged.append(line)
    db.tickerLines = merged


# -------------------------------------------------------------------
# Basic health + state endpoints
# -------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/state", response_model=State)
def get_state():
    """Return the shared PLERA Live state."""
    return db


@app.post("/state", response_model=State)
def post_state(incoming: State):
    """
    Merge a client state into the shared db and return the merged result.
    Your front-end will call this via syncToBackend().
    """
    merge_state(incoming)
    return db


# -------------------------------------------------------------------
# Granular endpoints (optional, good for later evolution)
# -------------------------------------------------------------------


@app.post("/posts", response_model=Post)
def create_or_update_post(post: Post):
    posts_by_id = {p.id: p for p in db.posts}
    posts_by_id[post.id] = post
    db.posts = sorted(
        posts_by_id.values(),
        key=lambda p: p.createdAt,
        reverse=True,
    )
    return post


@app.post("/events", response_model=Event)
def create_or_update_event(ev: Event):
    events_by_id = {e.id: e for e in db.events}
    events_by_id[ev.id] = ev
    db.events = list(events_by_id.values())
    return ev


@app.post("/dms")
def sync_dms(incoming: Dms):
    merge_state(State(dms=incoming))
    return {"ok": True}


# -------------------------------------------------------------------
# Admin summary (for tiny PLERA dashboard)
# -------------------------------------------------------------------

ADMIN_KEY = os.getenv("PLERA_ADMIN_KEY", "change-me")


class AdminSummary(BaseModel):
    total_users: int
    total_posts: int
    total_events: int
    total_dm_threads: int
    total_dm_messages: int
    most_active_users: List[Dict[str, Any]]
    posts_by_group: Dict[str, int]


@app.get("/admin/summary", response_model=AdminSummary)
def admin_summary(admin_key: str = Query(..., description="PLERA admin key")):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Basic counts
    total_users = len(db.users)
    total_posts = len(db.posts)
    total_events = len(db.events)
    total_dm_threads = len(db.dms.threads)
    total_dm_messages = sum(len(t.messages) for t in db.dms.threads.values())

    # Simple "most active": count posts per user
    posts_by_user: Dict[str, int] = {}
    for p in db.posts:
        posts_by_user[p.userId] = posts_by_user.get(p.userId, 0) + 1

    # Map userId -> name and sort
    user_name_by_id = {u.id: u.name for u in db.users}
    most_active_users = [
        {
            "userId": uid,
            "name": user_name_by_id.get(uid, "Unknown"),
            "postCount": count,
        }
        for uid, count in sorted(
            posts_by_user.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:5]
    ]

    # Posts per group
    posts_by_group: Dict[str, int] = {}
    for p in db.posts:
        gid = p.groupId or "ungrouped"
        posts_by_group[gid] = posts_by_group.get(gid, 0) + 1

    return AdminSummary(
        total_users=total_users,
        total_posts=total_posts,
        total_events=total_events,
        total_dm_threads=total_dm_threads,
        total_dm_messages=total_dm_messages,
        most_active_users=most_active_users,
        posts_by_group=posts_by_group,
    )
