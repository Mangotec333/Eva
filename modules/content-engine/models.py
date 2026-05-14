from pydantic import BaseModel
from typing import Optional, List

class DraftCreate(BaseModel):
    platform: str = "linkedin"
    content_type: str = "thought_leader"
    source_type: str = "manual"
    source_summary: Optional[str] = ""
    draft_text: str
    hook: Optional[str] = ""
    hashtags: Optional[List[str]] = []
    estimated_reach: Optional[str] = "medium"
    scheduled_for: Optional[str] = None

class DraftUpdate(BaseModel):
    draft_text: Optional[str] = None
    hook: Optional[str] = None
    hashtags: Optional[List[str]] = None

class RejectRequest(BaseModel):
    reason: str

class BatchApproveRequest(BaseModel):
    draft_ids: List[str]

class GenerateRequest(BaseModel):
    activity_summary: str
    source_type: str = "activity_stream"
    platforms: List[str] = ["linkedin"]
    count: int = 3

class VoiceUpdate(BaseModel):
    tone: Optional[str] = None
    example_hooks: Optional[List[str]] = None
    example_posts: Optional[List[str]] = None
    avoid: Optional[List[str]] = None
