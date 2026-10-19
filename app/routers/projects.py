"""Project and Contact Group API routes."""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import base64
import csv
import io

from app.database import get_db
from app.auth import get_current_user
from app.models import Campaign, ContactGroup, ContactGroupLead, Lead, Inbox, CampaignLead, CampaignInbox
from app.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ContactGroupCreate,
    ContactGroupUpdate,
    ContactGroupResponse,
    LeadCreateExtended,
    LeadUpdateExtended,
    LeadResponseExtended,
    CSVImportPreviewRequest,
    CSVImportPreviewResponse,
    CSVImportPreviewRow,
    CSVImportExecuteRequest,
    CSVImportExecuteResponse,
    ContactGroupLeadAdd,
    ContactGroupLeadResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Dependency: verify project ownership ──────────────────────────────────────
async def get_user_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> Campaign:
    """Get a project (campaign) owned by the current user."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == project_id, Campaign.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found or access denied")
    return project


async def get_user_contact_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> ContactGroup:
    """Get a contact group owned by the current user (via project ownership)."""
    result = await db.execute(
        select(ContactGroup)
        .join(Campaign, ContactGroup.campaign_id == Campaign.id)
        .where(ContactGroup.id == group_id, Campaign.owner_id == user.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Contact group not found or access denied")
    return group


# ── Project CRUD ──────────────────────────────────────────────────────────────

@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new project."""
    project = Campaign(
        name=data.name,
        owner_id=user.id,
        paused=False,
        archived=False,
    )
    db.add(project)
    await db.flush()

    # Assign inboxes if provided
    if data.inbox_ids:
        for pos, inbox_id in enumerate(data.inbox_ids):
            inbox = await db.get(Inbox, inbox_id)
            if inbox:
                db.add(CampaignInbox(campaign_id=project.id, inbox_id=inbox_id, position=pos))

    await db.flush()
    await db.commit()
    return project


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all projects owned by the current user."""
    stmt = select(Campaign).where(Campaign.owner_id == user.id)
    if not include_archived:
        stmt = stmt.where(Campaign.archived == False)
    stmt = stmt.order_by(Campaign.created_at.desc())

    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Get counts for each project
    project_ids = [p.id for p in projects]
    group_counts = {}
    lead_counts = {}
    inbox_maps = {}

    if project_ids:
        # Contact group counts
        gc_result = await db.execute(
            select(ContactGroup.campaign_id, func.count(ContactGroup.id))
            .where(ContactGroup.campaign_id.in_(project_ids))
            .group_by(ContactGroup.campaign_id)
        )
        group_counts = {row[0]: row[1] for row in gc_result.all()}

        # Lead counts (via contact groups)
        lc_result = await db.execute(
            select(ContactGroup.campaign_id, func.count(ContactGroupLead.id))
            .join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
            .where(ContactGroup.campaign_id.in_(project_ids))
            .group_by(ContactGroup.campaign_id)
        )
        lead_counts = {row[0]: row[1] for row in lc_result.all()}

        # Inbox IDs per project
        ic_result = await db.execute(
            select(CampaignInbox.campaign_id, CampaignInbox.inbox_id)
            .where(CampaignInbox.campaign_id.in_(project_ids))
            .order_by(CampaignInbox.position)
        )
        for cid, iid in ic_result.all():
            inbox_maps.setdefault(cid, []).append(iid)

    return [
        ProjectResponse(
            id=p.id,
            public_id=p.public_id,
            name=p.name,
            owner_id=p.owner_id,
            paused=p.paused,
            archived=p.archived,
            created_at=p.created_at,
            inbox_ids=inbox_maps.get(p.id, []),
            contact_group_count=group_counts.get(p.id, 0),
            lead_count=lead_counts.get(p.id, 0),
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project: Campaign = Depends(get_user_project),
    db: AsyncSession = Depends(get_db),
):
    """Get a single project with details."""
    # Get counts
    gc_result = await db.execute(
        select(func.count(ContactGroup.id)).where(ContactGroup.campaign_id == project.id)
    )
    group_count = gc_result.scalar() or 0

    lc_result = await db.execute(
        select(func.count(ContactGroupLead.id))
        .join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
        .where(ContactGroup.campaign_id == project.id)
    )
    lead_count = lc_result.scalar() or 0

    ic_result = await db.execute(
        select(CampaignInbox.inbox_id)
        .where(CampaignInbox.campaign_id == project.id)
        .order_by(CampaignInbox.position)
    )
    inbox_ids = [row[0] for row in ic_result.all()]

    return ProjectResponse(
        id=project.id,
        public_id=project.public_id,
        name=project.name,
        owner_id=project.owner_id,
        paused=project.paused,
        archived=project.archived,
        created_at=project.created_at,
        inbox_ids=inbox_ids,
        contact_group_count=group_count,
        lead_count=lead_count,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update a project."""
    project = await get_user_project(project_id, db, user)

    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.paused is not None:
        project.paused = data.paused
    if data.archived is not None:
        project.archived = data.archived
    if data.inbox_ids is not None:
        # Replace inbox assignments
        await db.execute(
            delete(CampaignInbox).where(CampaignInbox.campaign_id == project_id)
        )
        for pos, inbox_id in enumerate(data.inbox_ids):
            db.add(CampaignInbox(campaign_id=project_id, inbox_id=inbox_id, position=pos))

    await db.flush()
    await db.commit()
    return await get_project(project_id, db, user)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a project (and all associated contact groups, leads, etc.)."""
    project = await get_user_project(project_id, db, user)
    await db.delete(project)
    await db.commit()
    return {"ok": True, "detail": "Project deleted"}


# ── Contact Group CRUD ────────────────────────────────────────────────────────

@router.post("/{project_id}/groups", response_model=ContactGroupResponse, status_code=201)
async def create_contact_group(
    project_id: int,
    data: ContactGroupCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new contact group within a project."""
    project = await get_user_project(project_id, db, user)

    group = ContactGroup(
        campaign_id=project_id,
        name=data.name,
        description=data.description,
    )
    db.add(group)
    await db.flush()
    await db.commit()
    return group


@router.get("/{project_id}/groups", response_model=List[ContactGroupResponse])
async def list_contact_groups(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all contact groups in a project."""
    project = await get_user_project(project_id, db, user)

    result = await db.execute(
        select(ContactGroup)
        .where(ContactGroup.campaign_id == project_id)
        .order_by(ContactGroup.created_at.desc())
    )
    groups = result.scalars().all()

    # Get member counts
    group_ids = [g.id for g in groups]
    member_counts = {}
    if group_ids:
        mc_result = await db.execute(
            select(ContactGroupLead.group_id, func.count(ContactGroupLead.id))
            .where(ContactGroupLead.group_id.in_(group_ids))
            .group_by(ContactGroupLead.group_id)
        )
        member_counts = {row[0]: row[1] for row in mc_result.all()}

    return [
        ContactGroupResponse(
            id=g.id,
            campaign_id=g.campaign_id,
            name=g.name,
            description=g.description,
            created_at=g.created_at,
            updated_at=g.updated_at,
            member_count=member_counts.get(g.id, 0),
        )
        for g in groups
    ]


@router.get("/groups/{group_id}", response_model=ContactGroupResponse)
async def get_contact_group(
    group: ContactGroup = Depends(get_user_contact_group),
):
    """Get a single contact group with details."""
    return group


@router.patch("/groups/{group_id}", response_model=ContactGroupResponse)
async def update_contact_group(
    group_id: int,
    data: ContactGroupUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update a contact group."""
    group = await get_user_contact_group(group_id, db, user)

    if data.name is not None:
        group.name = data.name
    if data.description is not None:
        group.description = data.description

    await db.flush()
    await db.commit()
    return group


@router.delete("/groups/{group_id}")
async def delete_contact_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a contact group (and all member associations)."""
    group = await get_user_contact_group(group_id, db, user)
    await db.delete(group)
    await db.commit()
    return {"ok": True, "detail": "Contact group deleted"}


# ── Contact Group Members ─────────────────────────────────────────────────────

@router.post("/groups/{group_id}/members", response_model=ContactGroupLeadResponse, status_code=201)
async def add_member_to_group(
    group_id: int,
    data: ContactGroupLeadAdd,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Add a lead to a contact group."""
    group = await get_user_contact_group(group_id, db, user)

    # Verify lead exists
    lead = await db.get(Lead, data.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    # Check if already a member
    existing = await db.execute(
        select(ContactGroupLead).where(
            ContactGroupLead.group_id == group_id,
            ContactGroupLead.lead_id == data.lead_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Lead is already a member of this group")

    member = ContactGroupLead(group_id=group_id, lead_id=data.lead_id)
    db.add(member)
    await db.flush()
    await db.commit()

    return ContactGroupLeadResponse(
        id=member.id,
        group_id=member.group_id,
        lead_id=member.lead_id,
        lead=lead,
        added_at=member.added_at,
    )


@router.get("/groups/{group_id}/members", response_model=List[ContactGroupLeadResponse])
async def list_group_members(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all members of a contact group."""
    group = await get_user_contact_group(group_id, db, user)

    result = await db.execute(
        select(ContactGroupLead, Lead)
        .join(Lead, ContactGroupLead.lead_id == Lead.id)
        .where(ContactGroupLead.group_id == group_id)
        .order_by(ContactGroupLead.added_at.desc())
    )
    rows = result.all()

    return [
        ContactGroupLeadResponse(
            id=m.id,
            group_id=m.group_id,
            lead_id=m.lead_id,
            lead=LeadResponseExtended(
                id=l.id,
                email=l.email,
                name=l.name,
                first_name=l.first_name,
                last_name=l.last_name,
                linkedin_url=l.linkedin_url,
                company=l.company,
                title=l.title,
                website=l.website,
                custom_data=l.custom_data or {},
                provider=l.provider,
                email_verification_status=l.email_verification_status,
                do_not_contact=l.do_not_contact,
                status=l.status,
                created_at=l.created_at,
                updated_at=l.updated_at,
                campaigns=[],
                group_ids=[],
            ),
            added_at=m.added_at,
        )
        for m, l in rows
    ]


@router.delete("/groups/{group_id}/members/{lead_id}")
async def remove_member_from_group(
    group_id: int,
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove a lead from a contact group."""
    group = await get_user_contact_group(group_id, db, user)

    member = await db.execute(
        select(ContactGroupLead).where(
            ContactGroupLead.group_id == group_id,
            ContactGroupLead.lead_id == lead_id,
        )
    )
    member = member.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Member not found")

    await db.delete(member)
    await db.commit()
    return {"ok": True, "detail": "Member removed from group"}


# ── Lead Management within Project ────────────────────────────────────────────

@router.post("/{project_id}/leads", response_model=LeadResponseExtended, status_code=201)
async def create_lead_in_project(
    project_id: int,
    data: LeadCreateExtended,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new lead and optionally add to a group."""
    project = await get_user_project(project_id, db, user)

    # Validate: at least email or linkedin_url must be provided
    if not data.email and not data.linkedin_url:
        raise HTTPException(400, "Either email or linkedin_url must be provided")

    # Check for duplicate email
    if data.email:
        existing = await db.execute(select(Lead).where(Lead.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Lead with this email already exists")

    # Check for duplicate linkedin_url
    if data.linkedin_url:
        existing = await db.execute(select(Lead).where(Lead.linkedin_url == data.linkedin_url))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Lead with this LinkedIn URL already exists")

    lead = Lead(
        email=data.email,
        name=data.name,
        first_name=data.first_name,
        last_name=data.last_name,
        linkedin_url=data.linkedin_url,
        company=data.company,
        title=data.title,
        website=data.website,
        custom_data=data.custom_data,
    )
    db.add(lead)
    await db.flush()

    # Add to group if specified
    if data.group_id:
        group = await get_user_contact_group(data.group_id, db, user)
        if group.campaign_id != project_id:
            raise HTTPException(400, "Group does not belong to this project")
        db.add(ContactGroupLead(group_id=data.group_id, lead_id=lead.id))

    await db.commit()
    return lead


@router.get("/{project_id}/leads", response_model=List[LeadResponseExtended])
async def list_project_leads(
    project_id: int,
    group_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    do_not_contact: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all leads in a project, optionally filtered by group."""
    project = await get_user_project(project_id, db, user)

    # Build query
    stmt = select(Lead).join(ContactGroupLead, Lead.id == ContactGroupLead.lead_id)
    stmt = stmt.join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
    stmt = stmt.where(ContactGroup.campaign_id == project_id)

    if group_id:
        stmt = stmt.where(ContactGroupLead.group_id == group_id)

    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            (Lead.email.ilike(search_term))
            | (Lead.name.ilike(search_term))
            | (Lead.first_name.ilike(search_term))
            | (Lead.last_name.ilike(search_term))
            | (Lead.linkedin_url.ilike(search_term))
            | (Lead.company.ilike(search_term))
        )

    if do_not_contact is not None:
        stmt = stmt.where(Lead.do_not_contact == do_not_contact)

    stmt = stmt.distinct().order_by(Lead.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    leads = result.scalars().all()

    # Get group IDs for each lead
    lead_ids = [l.id for l in leads]
    group_map = {}
    if lead_ids:
        gm_result = await db.execute(
            select(ContactGroupLead.lead_id, ContactGroupLead.group_id)
            .join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
            .where(ContactGroupLead.lead_id.in_(lead_ids), ContactGroup.campaign_id == project_id)
        )
        for lid, gid in gm_result.all():
            group_map.setdefault(lid, []).append(gid)

    return [
        LeadResponseExtended(
            id=l.id,
            email=l.email,
            name=l.name,
            first_name=l.first_name,
            last_name=l.last_name,
            linkedin_url=l.linkedin_url,
            company=l.company,
            title=l.title,
            website=l.website,
            custom_data=l.custom_data or {},
            provider=l.provider,
            email_verification_status=l.email_verification_status,
            do_not_contact=l.do_not_contact,
            status=l.status,
            created_at=l.created_at,
            updated_at=l.updated_at,
            campaigns=[],
            group_ids=group_map.get(l.id, []),
        )
        for l in leads
    ]


@router.patch("/{project_id}/leads/{lead_id}", response_model=LeadResponseExtended)
async def update_lead(
    project_id: int,
    lead_id: int,
    data: LeadUpdateExtended,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update a lead."""
    project = await get_user_project(project_id, db, user)

    # Verify lead belongs to this project
    lead_result = await db.execute(
        select(Lead)
        .join(ContactGroupLead, Lead.id == ContactGroupLead.lead_id)
        .join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
        .where(Lead.id == lead_id, ContactGroup.campaign_id == project_id)
    )
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found in this project")

    # Check for duplicate email
    if data.email and data.email != lead.email:
        existing = await db.execute(select(Lead).where(Lead.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Lead with this email already exists")

    # Check for duplicate linkedin_url
    if data.linkedin_url and data.linkedin_url != lead.linkedin_url:
        existing = await db.execute(select(Lead).where(Lead.linkedin_url == data.linkedin_url))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Lead with this LinkedIn URL already exists")

    # Update fields
    if data.email is not None:
        lead.email = data.email
    if data.name is not None:
        lead.name = data.name
    if data.first_name is not None:
        lead.first_name = data.first_name
    if data.last_name is not None:
        lead.last_name = data.last_name
    if data.linkedin_url is not None:
        lead.linkedin_url = data.linkedin_url
    if data.company is not None:
        lead.company = data.company
    if data.title is not None:
        lead.title = data.title
    if data.website is not None:
        lead.website = data.website
    if data.custom_data is not None:
        lead.custom_data = data.custom_data
    if data.do_not_contact is not None:
        lead.do_not_contact = data.do_not_contact
    if data.status is not None:
        lead.status = data.status

    await db.flush()
    await db.commit()
    return lead


@router.delete("/{project_id}/leads/{lead_id}")
async def delete_lead(
    project_id: int,
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a lead from a project (removes from all groups)."""
    project = await get_user_project(project_id, db, user)

    # Verify lead belongs to this project
    lead_result = await db.execute(
        select(Lead)
        .join(ContactGroupLead, Lead.id == ContactGroupLead.lead_id)
        .join(ContactGroup, ContactGroupLead.group_id == ContactGroup.id)
        .where(Lead.id == lead_id, ContactGroup.campaign_id == project_id)
    )
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found in this project")

    await db.delete(lead)
    await db.commit()
    return {"ok": True, "detail": "Lead deleted"}


# ── CSV Import ────────────────────────────────────────────────────────────────

STANDARD_FIELDS = {
    "email", "name", "first_name", "last_name", "linkedin_url",
    "company", "title", "website",
}

def _parse_csv(file_content: str) -> tuple[list[str], list[dict]]:
    """Parse CSV content and return headers and rows."""
    reader = csv.DictReader(io.StringIO(file_content))
    headers = reader.fieldnames or []
    rows = list(reader)
    return headers, rows


def _validate_row(row: dict, column_mapping: dict) -> tuple[dict, list[str]]:
    """Validate and transform a CSV row based on column mapping."""
    errors = []
    result = {}

    for csv_header, field_name in column_mapping.items():
        if field_name in STANDARD_FIELDS:
            result[field_name] = row.get(csv_header, "").strip()
        else:
            # Custom field - will be stored in custom_data
            pass

    # Validate required fields
    has_email = result.get("email", "").strip()
    has_linkedin = result.get("linkedin_url", "").strip()
    if not has_email and not has_linkedin:
        errors.append("Row must have either email or linkedin_url")

    # Validate email format if present
    if has_email and "@" not in has_email:
        errors.append(f"Invalid email format: {has_email}")

    # Validate LinkedIn URL format if present
    if has_linkedin and not has_linkedin.startswith(("https://", "http://")):
        errors.append(f"LinkedIn URL must start with http:// or https://: {has_linkedin}")

    return result, errors


@router.post("/{project_id}/import/preview", response_model=CSVImportPreviewResponse)
async def preview_csv_import(
    project_id: int,
    request: CSVImportPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Preview CSV import with column mapping and validation."""
    project = await get_user_project(project_id, db, user)

    try:
        file_content = base64.b64decode(request.file_content).decode("utf-8-sig")
    except Exception as e:
        raise HTTPException(400, f"Invalid file encoding: {e}")

    headers, rows = _parse_csv(file_content)
    if not headers:
        raise HTTPException(400, "Empty CSV or no headers found")

    # Build suggested mapping based on header names
    suggested_mapping = {}
    for header in headers:
        h_lower = header.lower().strip()
        if h_lower in STANDARD_FIELDS:
            suggested_mapping[header] = h_lower
        elif h_lower in ["fname", "given_name"]:
            suggested_mapping[header] = "first_name"
        elif h_lower in ["lname", "surname", "family_name"]:
            suggested_mapping[header] = "last_name"
        elif h_lower in ["linkedin", "linkedin_profile", "profile_url"]:
            suggested_mapping[header] = "linkedin_url"
        elif h_lower in ["org", "organization"]:
            suggested_mapping[header] = "company"
        elif h_lower in ["position", "role", "job_title"]:
            suggested_mapping[header] = "title"
        elif h_lower in ["url", "site", "homepage"]:
            suggested_mapping[header] = "website"

    # Merge with user-provided mapping
    final_mapping = {**suggested_mapping, **request.column_mapping}

    # Preview first 20 rows
    preview = []
    valid_count = 0
    invalid_count = 0
    duplicate_count = 0
    seen_emails = set()
    seen_linkedins = set()

    for i, row in enumerate(rows[:20]):
        row_num = i + 1
        validated, errors = _validate_row(row, final_mapping)
        is_valid = len(errors) == 0

        # Check for duplicates in file
        email = validated.get("email", "").strip().lower()
        linkedin = validated.get("linkedin_url", "").strip().lower()
        is_duplicate = False
        if email and email in seen_emails:
            is_duplicate = True
            duplicate_count += 1
        elif linkedin and linkedin in seen_linkedins:
            is_duplicate = True
            duplicate_count += 1
        if email:
            seen_emails.add(email)
        if linkedin:
            seen_linkedins.add(linkedin)

        # Check for existing in database
        if is_valid:
            if email:
                existing = await db.execute(select(Lead.id).where(Lead.email == email))
                if existing.scalar_one_or_none():
                    is_duplicate = True
                    duplicate_count += 1
            elif linkedin:
                existing = await db.execute(select(Lead.id).where(Lead.linkedin_url == linkedin))
                if existing.scalar_one_or_none():
                    is_duplicate = True
                    duplicate_count += 1

        if is_valid and not is_duplicate:
            valid_count += 1
        else:
            invalid_count += 1

        preview.append(CSVImportPreviewRow(
            row_number=row_num,
            email=validated.get("email"),
            name=validated.get("name"),
            first_name=validated.get("first_name"),
            last_name=validated.get("last_name"),
            linkedin_url=validated.get("linkedin_url"),
            company=validated.get("company"),
            title=validated.get("title"),
            website=validated.get("website"),
            custom_data={k: v for k, v in row.items() if k not in final_mapping or final_mapping[k] not in STANDARD_FIELDS},
            is_valid=is_valid and not is_duplicate,
            errors=errors,
        ))

    # Count totals for full file
    total_rows = len(rows)
    for row in rows[20:]:
        validated, errors = _validate_row(row, final_mapping)
        if len(errors) == 0:
            email = validated.get("email", "").strip().lower()
            linkedin = validated.get("linkedin_url", "").strip().lower()
            is_dup = False
            if email and email in seen_emails:
                is_dup = True
            elif linkedin and linkedin in seen_linkedins:
                is_dup = True
            if email:
                seen_emails.add(email)
            if linkedin:
                seen_linkedins.add(linkedin)
            if not is_dup:
                valid_count += 1
            else:
                duplicate_count += 1
        else:
            invalid_count += 1

    return CSVImportPreviewResponse(
        total_rows=total_rows,
        valid_rows=valid_count,
        invalid_rows=invalid_count,
        duplicate_rows=duplicate_count,
        preview=preview,
        detected_columns=headers,
        suggested_mapping=suggested_mapping,
    )


@router.post("/{project_id}/import/execute", response_model=CSVImportExecuteResponse)
async def execute_csv_import(
    project_id: int,
    request: CSVImportExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Execute CSV import after preview."""
    project = await get_user_project(project_id, db, user)

    try:
        file_content = base64.b64decode(request.file_content).decode("utf-8-sig")
    except Exception as e:
        raise HTTPException(400, f"Invalid file encoding: {e}")

    headers, rows = _parse_csv(file_content)
    if not headers:
        raise HTTPException(400, "Empty CSV or no headers found")

    # Get target group if specified
    target_group = None
    if request.group_id:
        target_group = await get_user_contact_group(request.group_id, db, user)
        if target_group.campaign_id != project_id:
            raise HTTPException(400, "Group does not belong to this project")

    final_mapping = request.column_mapping
    duplicate_strategy = request.duplicate_strategy

    imported = 0
    updated = 0
    skipped = 0
    duplicates = 0
    errors = 0
    error_details = []

    seen_emails = set()
    seen_linkedins = set()

    for i, row in enumerate(rows):
        row_num = i + 1
        validated, row_errors = _validate_row(row, final_mapping)

        if row_errors:
            errors += 1
            error_details.append({
                "row": row_num,
                "email": validated.get("email"),
                "errors": row_errors,
            })
            continue

        email = validated.get("email", "").strip().lower()
        linkedin = validated.get("linkedin_url", "").strip().lower()

        # Check for duplicates in file
        is_file_duplicate = False
        if email and email in seen_emails:
            is_file_duplicate = True
        elif linkedin and linkedin in seen_linkedins:
            is_file_duplicate = True

        # Check for existing in database
        existing_lead = None
        if email:
            existing = await db.execute(select(Lead).where(Lead.email == email))
            existing_lead = existing.scalar_one_or_none()
        elif linkedin:
            existing = await db.execute(select(Lead).where(Lead.linkedin_url == linkedin))
            existing_lead = existing.scalar_one_or_none()

        is_db_duplicate = existing_lead is not None

        if is_file_duplicate or is_db_duplicate:
            duplicates += 1
            if duplicate_strategy == "skip":
                skipped += 1
                continue
            elif duplicate_strategy == "update" and existing_lead:
                # Update existing lead
                if validated.get("name"):
                    existing_lead.name = validated["name"]
                if validated.get("first_name"):
                    existing_lead.first_name = validated["first_name"]
                if validated.get("last_name"):
                    existing_lead.last_name = validated["last_name"]
                if validated.get("linkedin_url"):
                    existing_lead.linkedin_url = validated["linkedin_url"]
                if validated.get("company"):
                    existing_lead.company = validated["company"]
                if validated.get("title"):
                    existing_lead.title = validated["title"]
                if validated.get("website"):
                    existing_lead.website = validated["website"]

                # Merge custom data
                custom_data = {k: v for k, v in row.items() if k not in final_mapping or final_mapping[k] not in STANDARD_FIELDS}
                if custom_data:
                    existing_lead.custom_data = {**(existing_lead.custom_data or {}), **custom_data}

                await db.flush()
                lead = existing_lead
                updated += 1
            else:
                skipped += 1
                continue
        else:
            # Create new lead
            lead = Lead(
                email=email or None,
                name=validated.get("name", ""),
                first_name=validated.get("first_name", ""),
                last_name=validated.get("last_name", ""),
                linkedin_url=linkedin or None,
                company=validated.get("company", ""),
                title=validated.get("title", ""),
                website=validated.get("website", ""),
                custom_data={k: v for k, v in row.items() if k not in final_mapping or final_mapping[k] not in STANDARD_FIELDS},
            )
            db.add(lead)
            await db.flush()
            imported += 1

        # Add to group if specified
        if target_group:
            existing_member = await db.execute(
                select(ContactGroupLead).where(
                    ContactGroupLead.group_id == target_group.id,
                    ContactGroupLead.lead_id == lead.id,
                )
            )
            if not existing_member.scalar_one_or_none():
                db.add(ContactGroupLead(group_id=target_group.id, lead_id=lead.id))

        # Track seen identifiers
        if email:
            seen_emails.add(email)
        if linkedin:
            seen_linkedins.add(linkedin)

    await db.commit()

    return CSVImportExecuteResponse(
        imported=imported,
        updated=updated,
        skipped=skipped,
        duplicates=duplicates,
        errors=errors,
        error_details=error_details,
    )