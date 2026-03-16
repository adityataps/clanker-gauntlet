import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import (
    League,
    LeagueInvite,
    LeagueInviteStatus,
    LeagueMembership,
    LeagueMembershipRole,
    LeagueMembershipStatus,
    MembershipRole,
    PriorityReset,
    ScriptSpeed,
    Session,
    SessionCreationPolicy,
    SessionMembership,
    SessionStatus,
    Team,
    TeamType,
    User,
    WaiverMode,
)
from backend.db.session import get_db
from backend.league.membership import handle_member_exit

router = APIRouter(prefix="/leagues", tags=["leagues"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LeagueCreate(BaseModel):
    name: str
    session_creation: SessionCreationPolicy = SessionCreationPolicy.MANAGER_ONLY
    max_members: int = 100


class LeagueUpdate(BaseModel):
    name: str | None = None
    session_creation: SessionCreationPolicy | None = None


class LeagueResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    session_creation: SessionCreationPolicy
    max_members: int
    is_auto_generated: bool
    created_at: datetime
    member_count: int

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    display_name: str
    role: LeagueMembershipRole
    status: LeagueMembershipStatus
    joined_at: datetime

    model_config = {"from_attributes": True}


class InviteResponse(BaseModel):
    id: uuid.UUID
    token: str
    invited_email: str | None
    status: LeagueInviteStatus
    expires_at: datetime
    accept_url: str


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


class InviteByEmailRequest(BaseModel):
    email: EmailStr | None = None
    expires_hours: int = 72


class ChangeMemberRoleRequest(BaseModel):
    role: LeagueMembershipRole


class SessionCreate(BaseModel):
    name: str
    script_id: uuid.UUID
    sport: str
    season: int
    script_speed: ScriptSpeed
    waiver_mode: WaiverMode = WaiverMode.FAAB
    priority_reset: PriorityReset | None = None
    compression_factor: int | None = None
    max_teams: int = 12
    scoring_config: dict = {}


class SessionResponse(BaseModel):
    id: uuid.UUID
    name: str
    sport: str
    season: int
    status: str
    script_speed: ScriptSpeed
    waiver_mode: WaiverMode
    max_teams: int
    league_id: uuid.UUID | None
    owner_id: uuid.UUID
    team_id: uuid.UUID  # the creator's team

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_league_or_404(league_id: uuid.UUID, db: AsyncSession) -> League:
    result = await db.execute(select(League).where(League.id == league_id))
    league = result.scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return league


async def _require_active_member(
    league_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> LeagueMembership:
    result = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.user_id == user_id,
            LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
        )
    )
    lm = result.scalar_one_or_none()
    if lm is None:
        raise HTTPException(status_code=403, detail="Not a member of this league")
    return lm


async def _require_manager(
    league_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> LeagueMembership:
    lm = await _require_active_member(league_id, user_id, db)
    if lm.role != LeagueMembershipRole.MANAGER:
        raise HTTPException(status_code=403, detail="Manager role required")
    return lm


async def _member_count(league_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
        )
    )
    return result.scalar_one()


def _league_response(league: League, member_count: int) -> LeagueResponse:
    return LeagueResponse(
        id=league.id,
        name=league.name,
        created_by=league.created_by,
        session_creation=league.session_creation,
        max_members=league.max_members,
        is_auto_generated=league.is_auto_generated,
        created_at=league.created_at,
        member_count=member_count,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=LeagueResponse, status_code=status.HTTP_201_CREATED)
async def create_league(
    body: LeagueCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    league = League(
        name=body.name,
        created_by=current_user.id,
        session_creation=body.session_creation,
        max_members=body.max_members,
    )
    db.add(league)
    await db.flush()

    membership = LeagueMembership(
        league_id=league.id,
        user_id=current_user.id,
        role=LeagueMembershipRole.MANAGER,
        status=LeagueMembershipStatus.ACTIVE,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(league)

    return _league_response(league, 1)


@router.get("", response_model=list[LeagueResponse])
async def list_leagues(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(League).join(
            LeagueMembership,
            (LeagueMembership.league_id == League.id)
            & (LeagueMembership.user_id == current_user.id)
            & (LeagueMembership.status == LeagueMembershipStatus.ACTIVE),
        )
    )
    leagues = result.scalars().all()

    out = []
    for league in leagues:
        count = await _member_count(league.id, db)
        out.append(_league_response(league, count))
    return out


@router.get("/{league_id}", response_model=LeagueResponse)
async def get_league(
    league_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_active_member(league_id, current_user.id, db)
    league = await _get_league_or_404(league_id, db)
    count = await _member_count(league_id, db)
    return _league_response(league, count)


@router.patch("/{league_id}", response_model=LeagueResponse)
async def update_league(
    league_id: uuid.UUID,
    body: LeagueUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)
    league = await _get_league_or_404(league_id, db)

    if body.name is not None:
        league.name = body.name
    if body.session_creation is not None:
        league.session_creation = body.session_creation

    await db.commit()
    await db.refresh(league)
    count = await _member_count(league_id, db)
    return _league_response(league, count)


@router.delete("/{league_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_league(
    league_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)
    league = await _get_league_or_404(league_id, db)

    # Nullify league_id on sessions instead of deleting them
    await db.execute(update(Session).where(Session.league_id == league_id).values(league_id=None))

    # Cascade deletes for memberships and invites happen via ORM relationships
    await db.delete(league)
    await db.commit()


@router.post("/{league_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    league_id: uuid.UUID,
    body: AddMemberRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)
    league = await _get_league_or_404(league_id, db)

    # Check user exists
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check not already active
    existing = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.user_id == body.user_id,
            LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    count = await _member_count(league_id, db)
    if count >= league.max_members:
        raise HTTPException(status_code=409, detail="League is at max capacity")

    lm = LeagueMembership(
        league_id=league_id,
        user_id=body.user_id,
        role=LeagueMembershipRole.MEMBER,
        status=LeagueMembershipStatus.ACTIVE,
    )
    db.add(lm)
    await db.commit()
    await db.refresh(lm)

    return MemberResponse(
        user_id=lm.user_id,
        display_name=target_user.display_name,
        role=lm.role,
        status=lm.status,
        joined_at=lm.joined_at,
    )


@router.delete("/{league_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    league_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Cannot remove yourself")

    await handle_member_exit(league_id, user_id, db, LeagueMembershipStatus.REMOVED)
    await db.commit()


@router.post("/{league_id}/members/me/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_league(
    league_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_active_member(league_id, current_user.id, db)
    await handle_member_exit(league_id, current_user.id, db, LeagueMembershipStatus.LEFT)
    await db.commit()


@router.patch("/{league_id}/members/{user_id}", response_model=MemberResponse)
async def change_member_role(
    league_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ChangeMemberRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)

    if user_id == current_user.id and body.role != LeagueMembershipRole.MANAGER:
        raise HTTPException(status_code=403, detail="Cannot demote yourself")

    target_result = await db.execute(
        select(LeagueMembership, User)
        .join(User, User.id == LeagueMembership.user_id)
        .where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.user_id == user_id,
            LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
        )
    )
    row = target_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")

    target_lm, target_user = row

    if body.role == LeagueMembershipRole.MANAGER and target_lm.role != LeagueMembershipRole.MANAGER:
        # Downgrade current manager to member
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user.id,
            )
            .values(role=LeagueMembershipRole.MEMBER)
        )

    target_lm.role = body.role
    await db.commit()
    await db.refresh(target_lm)

    return MemberResponse(
        user_id=target_lm.user_id,
        display_name=target_user.display_name,
        role=target_lm.role,
        status=target_lm.status,
        joined_at=target_lm.joined_at,
    )


@router.post("/{league_id}/invites", response_model=InviteResponse, status_code=201)
async def create_invite(
    league_id: uuid.UUID,
    body: InviteByEmailRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)
    await _get_league_or_404(league_id, db)

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=body.expires_hours)

    invited_user_id = None
    if body.email:
        user_result = await db.execute(select(User).where(User.email == body.email))
        existing_user = user_result.scalar_one_or_none()
        if existing_user:
            invited_user_id = existing_user.id

    invite = LeagueInvite(
        league_id=league_id,
        token=token,
        invited_email=body.email,
        invited_user_id=invited_user_id,
        created_by=current_user.id,
        expires_at=expires_at,
        status=LeagueInviteStatus.PENDING,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return InviteResponse(
        id=invite.id,
        token=invite.token,
        invited_email=invite.invited_email,
        status=invite.status,
        expires_at=invite.expires_at,
        accept_url=f"/leagues/join/{token}",
    )


@router.post("/join/{token}", response_model=LeagueResponse)
async def join_league(
    token: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    invite_result = await db.execute(select(LeagueInvite).where(LeagueInvite.token == token))
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.status != LeagueInviteStatus.PENDING:
        raise HTTPException(status_code=409, detail="Invite is no longer valid")

    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=409, detail="Invite has expired")

    if invite.invited_email and invite.invited_email != current_user.email:
        raise HTTPException(
            status_code=403, detail="This invite was sent to a different email address"
        )

    # Check not already a member
    existing = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == invite.league_id,
            LeagueMembership.user_id == current_user.id,
            LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already a member of this league")

    lm = LeagueMembership(
        league_id=invite.league_id,
        user_id=current_user.id,
        role=LeagueMembershipRole.MEMBER,
        status=LeagueMembershipStatus.ACTIVE,
    )
    db.add(lm)

    invite.status = LeagueInviteStatus.ACCEPTED
    invite.accepted_by = current_user.id
    invite.accepted_at = datetime.now(UTC)

    await db.commit()

    league = await _get_league_or_404(invite.league_id, db)
    count = await _member_count(invite.league_id, db)
    return _league_response(league, count)


@router.get("/{league_id}/invites", response_model=list[InviteResponse])
async def list_invites(
    league_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(league_id, current_user.id, db)

    result = await db.execute(select(LeagueInvite).where(LeagueInvite.league_id == league_id))
    invites = result.scalars().all()

    return [
        InviteResponse(
            id=inv.id,
            token=inv.token,
            invited_email=inv.invited_email,
            status=inv.status,
            expires_at=inv.expires_at,
            accept_url=f"/leagues/join/{inv.token}",
        )
        for inv in invites
    ]


@router.post("/{league_id}/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    league_id: uuid.UUID,
    body: SessionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    league = await _get_league_or_404(league_id, db)
    membership = await _require_active_member(league_id, current_user.id, db)

    if (
        league.session_creation == SessionCreationPolicy.MANAGER_ONLY
        and membership.role != LeagueMembershipRole.MANAGER
    ):
        raise HTTPException(status_code=403, detail="Only the league manager can create sessions")

    if body.max_teams < 2 or body.max_teams > 20:
        raise HTTPException(status_code=422, detail="max_teams must be between 2 and 20")

    session = Session(
        owner_id=current_user.id,
        script_id=body.script_id,
        league_id=league_id,
        name=body.name,
        sport=body.sport,
        season=body.season,
        status=SessionStatus.DRAFT_PENDING,
        script_speed=body.script_speed,
        waiver_mode=body.waiver_mode,
        priority_reset=body.priority_reset,
        compression_factor=body.compression_factor,
        max_teams=body.max_teams,
        scoring_config=body.scoring_config,
    )
    db.add(session)
    await db.flush()

    team = Team(
        session_id=session.id,
        name=current_user.display_name,
        type=TeamType.HUMAN,
        config={},
        faab_balance=100,
    )
    db.add(team)
    await db.flush()

    sm = SessionMembership(
        session_id=session.id,
        user_id=current_user.id,
        role=MembershipRole.OWNER,
        team_id=team.id,
    )
    db.add(sm)
    await db.commit()

    return SessionResponse(
        id=session.id,
        name=session.name,
        sport=session.sport,
        season=session.season,
        status=session.status,
        script_speed=session.script_speed,
        waiver_mode=session.waiver_mode,
        max_teams=session.max_teams,
        league_id=session.league_id,
        owner_id=session.owner_id,
        team_id=team.id,
    )
