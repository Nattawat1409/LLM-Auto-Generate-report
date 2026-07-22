from fastapi import APIRouter

from app.db.schema import get_schema_text
from app.nodes.human_in_the_loop import VALID_TEMPLATES

router = APIRouter(tags=["metadata"])


@router.get("/schema")
async def get_schema():
    return {"schema": get_schema_text()}


@router.get("/templates")
async def get_templates():
    return {"templates": list(VALID_TEMPLATES)}
