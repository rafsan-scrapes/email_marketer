"""Template, Sequence, and Draft API routes for manual outreach."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Campaign,
    ContactGroup,
    ContactGroupLead,
    Draft,
    Lead,
    Sequence,
    Template,
    CampaignLead,
)
from app.schemas import (
    DraftResponse,
    DraftBatchResponse,
    EnrollContactsRequest,
    DraftStatusUpdate,
    SequenceCreate,
    SequenceUpdate,
    SequenceResponse,
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
)
from app.auth import get_current_user

log = logging.getLogger("quickly.routes.templates")

router = APIRouter(prefix="/api/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    channel: Optional[str] = Query(None, pattern="^(email|linkedin_dm)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all templates owned by the current user."""
    stmt = select(Template).where(Template.owner_id == user.id).order_by(Template.created_at.desc())
    if channel:
        stmt = stmt.where(Template.channel == channel)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new template."""
    # Validate subject for email channel
    if data.channel == "email" and not data.subject:
        raise HTTPException(400, "Subject is required for email templates")
    if data.channel == "linkedin_dm" and data.subject:
        raise HTTPException(400, "Subject not allowed for LinkedIn DM templates")
    
    template = Template(
        owner_id=user.id,
        name=data.name,
        channel=data.channel,
        subject=data.subject,
        body=data.body,
        is_html=data.is_html,
        description=data.description,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get a specific template."""
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.owner_id == user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    return template


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update a template."""
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.owner_id == user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    
    if data.name is not None:
        template.name = data.name
    if data.channel is not None:
        template.channel = data.channel
    if data.subject is not None:
        if data.channel == "linkedin_dm" or (template.channel == "linkedin_dm" and data.subject):
            raise HTTPException(400, "Subject not allowed for LinkedIn DM templates")
        template.subject = data.subject
    if data.body is not None:
        template.body = data.body
    if data.is_html is not None:
        template.is_html = data.is_html
    if data.description is not None:
        template.description = data.description
    
    template.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(template)
    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a template."""
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.owner_id == user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    
    await db.delete(template)
    await db.flush()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Template Preview
# ---------------------------------------------------------------------------

class TemplatePreviewRequest(BaseModel):
    template_id: int
    lead_id: int


class TemplatePreviewResponse(BaseModel):
    subject: Optional[str] = None
    body: str
    missing_fields: list[str] = []
    unknown_placeholders: list[str] = []


@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    data: TemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Preview a template rendered against a specific lead."""
    from app.sender import render_body, get_lead_data, RenderContext
    
    # Verify template ownership
    result = await db.execute(
        select(Template).where(Template.id == data.template_id, Template.owner_id == user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    
    # Get lead
    lead_result = await db.execute(select(Lead).where(Lead.id == data.lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    
    lead_data = get_lead_data(lead)
    ctx = RenderContext()
    
    # Render subject (if email)
    subject = None
    missing = []
    unknown = []
    
    if template.channel == "email" and template.subject:
        subject = render_body(template.subject, lead_data, context=ctx)
        # Check for unresolved placeholders
        import re
        for match in re.finditer(r'\{\{([^}]+)\}\}', template.subject):
            placeholder = match.group(1).strip()
            if placeholder not in lead_data:
                missing.append(placeholder)
    
    # Render body
    rendered_body = render_body(template.body, lead_data, context=ctx)
    for match in re.finditer(r'\{\{([^}]+)\}\}', template.body):
        placeholder = match.group(1).strip()
        if placeholder not in lead_data:
            missing.append(placeholder)
    
    return TemplatePreviewResponse(
        subject=subject,
        body=rendered_body,
        missing_fields=list(set(missing)),
        unknown_placeholders=unknown,
    )


# ---------------------------------------------------------------------------
# Sequence CRUD (extended with channel)
# ---------------------------------------------------------------------------

# Note: Sequence CRUD already exists in campaigns router. 
# This router adds channel-aware extensions if needed.


# ---------------------------------------------------------------------------
# Draft Generation (Enrollment)
# ---------------------------------------------------------------------------

def _extract_placeholders(text: str) -> list[str]:
    """Extract all {{placeholder}} from text."""
    import re
    return [m.group(1).strip() for m in re.finditer(r'\{\{([^}]+)\}\}', text)]


def _check_missing_placeholders(template: Template, lead: Lead) -> tuple[list[str], list[str]]:
    """Check which placeholders are missing or unknown for a lead."""
    lead_data = {}
    if lead.email:
        lead_data["email"] = lead.email
    if lead.name:
        lead_data["name"] = lead.name
    if lead.first_name:
        lead_data["first_name"] = lead.first_name
    if lead.last_name:
        lead_data["last_name"] = lead.last_name
    if lead.company:
        lead_data["company"] = lead.company
    if lead.title:
        lead_data["title"] = lead.title
    if lead.website:
        lead_data["website"] = lead.website
    if lead.linkedin_url:
        lead_data["linkedin_url"] = lead.linkedin_url
    if lead.custom_data and isinstance(lead.custom_data, dict):
        lead_data.update(lead.custom_data)
    
    # Always available placeholders
    lead_data["unsubscribe_link"] = "UNSUBSCRIBE_LINK_PLACEHOLDER"
    
    all_text = (template.subject or "") + "\n" + template.body
    placeholders = _extract_placeholders(all_text)
    
    missing = []
    for ph in placeholders:
        if ph not in lead_data:
            missing.append(ph)
    
    return missing, []


@router.post("/enroll", response_model=DraftBatchResponse)
async def enroll_contacts(
    data: EnrollContactsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Enroll contacts into a sequence, generating personalized drafts.
    
    This creates Draft records for each contact and sequence step without
    sending anything. Drafts are stored with their rendered content.
    """
    from app.sender import render_body, get_lead_data, RenderContext
    
    # Verify project ownership
    project_result = await db.execute(
        select(Campaign).where(Campaign.id == data.project_id, Campaign.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found or access denied")
    
    # Verify sequence belongs to project
    seq_result = await db.execute(
        select(Sequence).where(Sequence.id == data.sequence_id, Sequence.campaign_id == data.project_id)
    )
    sequence = seq_result.scalar_one_or_none()
    if not sequence:
        raise HTTPException(404, "Sequence not found in this project")
    
    # Get leads to enroll
    lead_ids = data.lead_ids
    if data.group_id:
        group_result = await db.execute(
            select(ContactGroup).where(
                ContactGroup.id == data.group_id,
                ContactGroup.campaign_id == data.project_id
            )
        )
        group = group_result.scalar_one_or_none()
        if not group:
            raise HTTPException(404, "Contact group not found in this project")
        
        member_result = await db.execute(
            select(ContactGroupLead.lead_id).where(ContactGroupLead.group_id == data.group_id)
        )
        lead_ids = [r[0] for r in member_result.all()]
    
    if not lead_ids:
        return DraftBatchResponse(drafts_created=0, drafts=[], skipped=[])
    
    # Get leads
    leads_result = await db.execute(select(Lead).where(Lead.id.in_(lead_ids)))
    leads = leads_result.scalars().all()
    
    # Get all sequences in this campaign ordered by position
    all_seq_result = await db.execute(
        select(Sequence).where(Sequence.campaign_id == data.project_id).order_by(Sequence.position)
    )
    all_sequences = all_seq_result.scalars().all()
    
    # Find the index of the starting sequence
    start_idx = next((i for i, s in enumerate(all_sequences) if s.id == data.sequence_id), 0)
    relevant_sequences = all_sequences[start_idx:]
    
    if not relevant_sequences:
        return DraftBatchResponse(drafts_created=0, drafts=[], skipped=[])
    
    # Parse start time
    start_at = data.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    else:
        start_at = start_at.astimezone(timezone.utc)
    
    drafts_created = 0
    created_drafts = []
    skipped = []
    
    for lead in leads:
        # Check eligibility for each sequence step
        current_due = start_at
        
        for step_idx, seq in enumerate(relevant_sequences):
            # Check channel eligibility
            if seq.channel == "email" and not (lead.email and lead.email.strip()):
                skipped.append({
                    "lead_id": lead.id,
                    "step": seq.position,
                    "reason": "Email step requires a valid email address"
                })
                continue
            if seq.channel == "linkedin_dm" and not (lead.linkedin_url and lead.linkedin_url.strip()):
                skipped.append({
                    "lead_id": lead.id,
                    "step": seq.position,
                    "reason": "LinkedIn DM step requires a LinkedIn URL"
                })
                continue
            
            # Check for missing placeholders
            missing_fields, unknown = _check_missing_placeholders(
                Template(name="sequence", channel=seq.channel, subject=seq.subject or "", body=seq.body, is_html=seq.is_html or False),
                lead
            )
            
            if missing_fields:
                skipped.append({
                    "lead_id": lead.id,
                    "step": seq.position,
                    "reason": f"Missing required fields: {', '.join(missing_fields)}"
                })
                continue
            
            # Render personalized content
            lead_data = get_lead_data(lead)
            ctx = RenderContext()
            
            subject = None
            if seq.channel == "email" and seq.subject:
                subject = render_body(seq.subject, lead_data, context=ctx)
            
            body = render_body(seq.body, lead_data, context=ctx)
            
            # Calculate due time for this step
            if step_idx == 0:
                due_at = current_due
            else:
                # Add wait_days_after_previous days
                from datetime import timedelta
                current_due = current_due + timedelta(days=relevant_sequences[step_idx - 1].wait_days_after_previous)
                due_at = current_due
            
            # Create draft
            draft = Draft(
                campaign_id=data.project_id,
                sequence_id=seq.id,
                lead_id=lead.id,
                channel=seq.channel,
                subject=subject,
                body=body,
                status="pending" if step_idx == 0 else "pending",
                due_at=due_at,
            )
            db.add(draft)
            drafts_created += 1
            created_drafts.append(draft)
        
        # Update current_due for next lead (not needed, each lead starts at same time)
    
    await db.flush()
    
    # Refresh to get IDs
    for draft in created_drafts:
        await db.refresh(draft)
    
    return DraftBatchResponse(
        drafts_created=drafts_created,
        drafts=[DraftResponse.model_validate(d) for d in created_drafts],
        skipped=skipped,
    )


# ---------------------------------------------------------------------------
# Draft Management
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/drafts", response_model=list[DraftResponse])
async def list_drafts(
    project_id: int,
    status: Optional[str] = Query(None),
    sequence_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List drafts for a project with optional filters."""
    # Verify project ownership
    project_result = await db.execute(
        select(Campaign).where(Campaign.id == project_id, Campaign.owner_id == user.id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(404, "Project not found or access denied")
    
    stmt = select(Draft).where(Draft.campaign_id == project_id)
    
    if status:
        stmt = stmt.where(Draft.status == status)
    if sequence_id:
        stmt = stmt.where(Draft.sequence_id == sequence_id)
    if lead_id:
        stmt = stmt.where(Draft.lead_id == lead_id)
    
    stmt = stmt.order_by(Draft.due_at.nulls_last(), Draft.created_at)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get a specific draft."""
    result = await db.execute(
        select(Draft)
        .join(Campaign, Draft.campaign_id == Campaign.id)
        .where(Draft.id == draft_id, Campaign.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")
    return draft


@router.patch("/drafts/{draft_id}", response_model=DraftResponse)
async def update_draft_status(
    draft_id: int,
    data: DraftStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update draft status (e.g., mark as sent, skipped, blocked)."""
    result = await db.execute(
        select(Draft)
        .join(Campaign, Draft.campaign_id == Campaign.id)
        .where(Draft.id == draft_id, Campaign.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")
    
    if data.status == "sent" and not data.sent_at:
        raise HTTPException(400, "sent_at is required when status is 'sent'")
    
    draft.status = data.status
    if data.sent_at:
        draft.sent_at = data.sent_at
    draft.updated_at = datetime.now(timezone.utc)
    
    await db.flush()
    await db.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/mark-sent", response_model=DraftResponse)
async def mark_draft_sent(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Mark a draft as sent, and if it's a sequence step, make the next step due.
    
    This is the manual "mark as sent" action that calculates the next step's
    due time based on the actual sent time + the step's configured delay.
    """
    from datetime import timedelta
    
    result = await db.execute(
        select(Draft)
        .join(Campaign, Draft.campaign_id == Campaign.id)
        .where(Draft.id == draft_id, Campaign.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")
    
    if draft.status == "sent":
        return draft  # Idempotent
    
    now = datetime.now(timezone.utc)
    draft.status = "sent"
    draft.sent_at = now
    draft.updated_at = now
    
    # Find the next sequence step in the same campaign
    # First get the current sequence's position
    current_seq_result = await db.execute(
        select(Sequence.position).where(Sequence.id == draft.sequence_id)
    )
    current_position = current_seq_result.scalar_one_or_none()
    
    if current_position is not None:
        next_seq_result = await db.execute(
            select(Sequence)
            .where(
                Sequence.campaign_id == draft.campaign_id,
                Sequence.position > current_position
            )
            .order_by(Sequence.position)
            .limit(1)
        )
        next_sequence = next_seq_result.scalar_one_or_none()
    else:
        next_sequence = None
    
    if next_sequence:
        # Find or create the draft for the next step for this lead
        next_draft_result = await db.execute(
            select(Draft).where(
                Draft.campaign_id == draft.campaign_id,
                Draft.sequence_id == next_sequence.id,
                Draft.lead_id == draft.lead_id,
            )
        )
        next_draft = next_draft_result.scalar_one_or_none()
        
        if next_draft:
            # Calculate due time: sent_at + wait_days_after_previous
            due_at = now + timedelta(days=next_sequence.wait_days_after_previous)
            next_draft.status = "due"
            next_draft.due_at = due_at
            next_draft.updated_at = now
        else:
            # Create the next draft (should exist if enrollment was done properly)
            pass
    
    await db.flush()
    await db.refresh(draft)
    return draft