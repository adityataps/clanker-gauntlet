import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from backend.db.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Sport(str, enum.Enum):
    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"


class SeasonType(str, enum.Enum):
    PRESEASON = "preseason"
    REGULAR = "regular"
    PLAYOFF = "playoff"


class ScriptStatus(str, enum.Enum):
    PENDING = "pending"
    COMPILED = "compiled"
    FAILED = "failed"


class SessionStatus(str, enum.Enum):
    DRAFT_PENDING = "draft_pending"
    DRAFT_IN_PROGRESS = "draft_in_progress"
    DRAFT_COMPLETE = "draft_complete"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"


class SessionMode(str, enum.Enum):
    INSTANT = "instant"
    COMPRESSED = "compressed"
    REALTIME = "realtime"


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"
    OBSERVER = "observer"


class TeamType(str, enum.Enum):
    AGENT = "agent"
    HUMAN = "human"
    EXTERNAL = "external"


class RosterSlot(str, enum.Enum):
    ACTIVE = "active"
    BENCH = "bench"
    IR = "ir"


class AcquiredVia(str, enum.Enum):
    DRAFT = "draft"
    WAIVER = "waiver"
    TRADE = "trade"


class DraftType(str, enum.Enum):
    SNAKE = "snake"
    AUCTION = "auction"


class DraftStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DecisionType(str, enum.Enum):
    LINEUP = "lineup"
    WAIVER = "waiver"
    TRADE_RESPONSE = "trade_response"
    DRAFT_PICK = "draft_pick"


class WaiverBidStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


class TradeStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Global / Shared — compiled once, referenced by many sessions
# ---------------------------------------------------------------------------

class SeasonScript(Base):
    """
    Compiled season timeline. One record per sport+season+season_type.
    Multiple sessions can backtest against the same script.
    """
    __tablename__ = "season_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport: Mapped[str] = mapped_column(SAEnum(Sport, native_enum=False), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    season_type: Mapped[str] = mapped_column(SAEnum(SeasonType, native_enum=False), nullable=False, default=SeasonType.REGULAR)
    compiled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(SAEnum(ScriptStatus, native_enum=False), nullable=False, default=ScriptStatus.PENDING)

    events: Mapped[list["SeasonEvent"]] = relationship(back_populates="script", cascade="all, delete-orphan")
    sessions: Mapped[list["Session"]] = relationship(back_populates="script")

    __table_args__ = (
        UniqueConstraint("sport", "season", "season_type", name="uq_season_scripts_sport_season_type"),
    )


class SeasonEvent(Base):
    """
    Individual event row in the compiled season timeline.
    sim_offset_hours: hours from season kickoff — used to compute wall_time
    per session based on its compression_factor.
    """
    __tablename__ = "season_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    script_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("season_scripts.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sim_offset_hours: Mapped[float] = mapped_column(Float, nullable=False)

    script: Mapped["SeasonScript"] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_season_events_script_seq", "script_id", "seq"),
        Index("ix_season_events_script_week", "script_id", "week_number"),
        Index("ix_season_events_type", "event_type"),
    )


# ---------------------------------------------------------------------------
# Users & Auth
# ---------------------------------------------------------------------------

class User(Base):
    """Platform account. Holds encrypted Anthropic API key."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # JWT auth only
    auth0_sub: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # Auth0 only
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    anthropic_api_key_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SessionInvite(Base):
    """Expiring invite token for joining a session."""
    __tablename__ = "session_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# Sessions & Membership
# ---------------------------------------------------------------------------

class Session(Base):
    """
    A league instance. References a shared SeasonScript.
    current_seq: EventRunner cursor, persisted for resume after restart.
    """
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    script_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("season_scripts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sport: Mapped[str] = mapped_column(SAEnum(Sport, native_enum=False), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(SessionStatus, native_enum=False), nullable=False, default=SessionStatus.DRAFT_PENDING)
    mode: Mapped[str] = mapped_column(SAEnum(SessionMode, native_enum=False), nullable=False)
    compression_factor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # COMPRESSED mode only
    wall_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_seq: Mapped[int] = mapped_column(Integer, default=0)
    scoring_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    script: Mapped["SeasonScript"] = relationship(back_populates="sessions")
    teams: Mapped[list["Team"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    memberships: Mapped[list["SessionMembership"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SessionMembership(Base):
    """Who is in a session and in what role."""
    __tablename__ = "session_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # null for system agents
    role: Mapped[str] = mapped_column(SAEnum(MembershipRole, native_enum=False), nullable=False)
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)  # null for observers
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_membership_session_user"),
    )


# ---------------------------------------------------------------------------
# Teams & Rosters
# ---------------------------------------------------------------------------

class Team(Base):
    """
    One team slot in a session. config JSONB shape varies by type:
      AGENT:    { archetype, reasoning_depth, system_prompt }
      EXTERNAL: { container_url, health_endpoint }
      HUMAN:    {}
    """
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(SAEnum(TeamType, native_enum=False), nullable=False)
    faab_balance: Mapped[int] = mapped_column(Integer, default=100)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="teams")
    roster: Mapped[list["RosterPlayer"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class RosterPlayer(Base):
    """
    Current roster membership. player_id is a Sleeper API string ID.
    Player metadata (name, position, NFL team) is never stored here —
    always fetched from Sleeper API / Redis cache.
    """
    __tablename__ = "roster_players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[str] = mapped_column(String(50), nullable=False)
    slot: Mapped[str] = mapped_column(SAEnum(RosterSlot, native_enum=False), nullable=False, default=RosterSlot.BENCH)
    acquired_week: Mapped[int] = mapped_column(Integer, nullable=False)
    acquired_via: Mapped[str] = mapped_column(SAEnum(AcquiredVia, native_enum=False), nullable=False)

    team: Mapped["Team"] = relationship(back_populates="roster")

    __table_args__ = (
        UniqueConstraint("team_id", "player_id", name="uq_roster_team_player"),
        Index("ix_roster_players_team", "team_id"),
    )


# ---------------------------------------------------------------------------
# Draft (Phase 2 — schema present, logic wired in Phase 2)
# ---------------------------------------------------------------------------

class Draft(Base):
    """One draft per session, runs before IN_PROGRESS."""
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(SAEnum(DraftType, native_enum=False), nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(DraftStatus, native_enum=False), nullable=False, default=DraftStatus.PENDING)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    current_pick: Mapped[int] = mapped_column(Integer, default=1)
    turn_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    pick_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auction_budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # AUCTION only, separate from FAAB

    picks: Mapped[list["DraftPick"]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class DraftPick(Base):
    """Each pick made during the draft."""
    __tablename__ = "draft_picks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[str] = mapped_column(String(50), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    pick_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bid_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # AUCTION only
    picked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draft: Mapped["Draft"] = relationship(back_populates="picks")

    __table_args__ = (
        Index("ix_draft_picks_draft", "draft_id"),
    )


# ---------------------------------------------------------------------------
# Session Events & Decisions
# ---------------------------------------------------------------------------

class ProcessedEvent(Base):
    """
    Per-session audit log of meaningful milestones only.
    STAT_UPDATE events are NOT stored here — they flow through Redis Streams only.
    Stored: AGENT_WINDOW_*, WEEK_END, WAIVER_RESOLVED, TRADE_RESOLVED,
            INJURY_UPDATE, DRAFT_PICK, SEASON_END.
    """
    __tablename__ = "processed_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_processed_events_session_seq", "session_id", "seq"),
    )


class PendingDecision(Base):
    """
    Open action waiting on a human player.
    Resolved when the user submits via UI, or deadline passes (auto-lineup applied).
    """
    __tablename__ = "pending_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    decision_type: Mapped[str] = mapped_column(SAEnum(DecisionType, native_enum=False), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_pending_decisions_session_team", "session_id", "team_id"),
    )


class AgentDecision(Base):
    """Full audit log of every decision made by every team (agents + humans)."""
    __tablename__ = "agent_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_type: Mapped[str] = mapped_column(SAEnum(DecisionType, native_enum=False), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reasoning_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_agent_decisions_session_team", "session_id", "team_id"),
    )


# ---------------------------------------------------------------------------
# League Engine
# ---------------------------------------------------------------------------

class Matchup(Base):
    """
    One head-to-head pairing per scoring period.
    home_score/away_score increment on every STAT_UPDATE event processed.
    winner_team_id set at WEEK_END.
    """
    __tablename__ = "matchups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    home_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    home_score: Mapped[float] = mapped_column(Float, default=0.0)
    away_score: Mapped[float] = mapped_column(Float, default=0.0)
    winner_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "period_number", "home_team_id", "away_team_id", name="uq_matchup_period_teams"),
        Index("ix_matchups_session_period", "session_id", "period_number"),
    )


class PlayerScore(Base):
    """
    Accumulated fantasy points per player per scoring period.
    Upserted on each STAT_UPDATE. stats_json holds raw stat accumulators.
    Used by agents for context and by UI for score breakdowns.
    """
    __tablename__ = "player_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str] = mapped_column(String(50), nullable=False)
    points_total: Mapped[float] = mapped_column(Float, default=0.0)
    stats_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("session_id", "team_id", "period_number", "player_id", name="uq_player_score_period"),
        Index("ix_player_scores_session_period", "session_id", "period_number"),
    )


class Standings(Base):
    """
    Season win/loss record. Updated once per WEEK_END event.
    Live mid-week view = join this table with current matchups scores.
    """
    __tablename__ = "standings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    ties: Mapped[int] = mapped_column(Integer, default=0)
    points_for: Mapped[float] = mapped_column(Float, default=0.0)
    points_against: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("session_id", "team_id", name="uq_standings_session_team"),
    )


class WaiverBid(Base):
    """
    FAAB bid submitted during a waiver window.
    priority = preference order (1 = top choice) for the team's ordered wish list.
    Resolved atomically at WAIVER_RESOLVED: highest bid per player wins.
    """
    __tablename__ = "waiver_bids"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    add_player_id: Mapped[str] = mapped_column(String(50), nullable=False)
    drop_player_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bid_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(WaiverBidStatus, native_enum=False), nullable=False, default=WaiverBidStatus.PENDING)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_waiver_bids_session_team_period", "session_id", "team_id", "period_number"),
    )


class TradeProposal(Base):
    """
    Trade offer between two teams. Triggers soft-locks on involved players.
    offered_player_ids / requested_player_ids are JSONB arrays of Sleeper IDs.
    """
    __tablename__ = "trade_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    proposing_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    receiving_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    offered_player_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requested_player_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(SAEnum(TradeStatus, native_enum=False), nullable=False, default=TradeStatus.PENDING)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    locks: Mapped[list["TradeLock"]] = relationship(back_populates="trade_proposal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_trade_proposals_session", "session_id"),
    )


class TradeLock(Base):
    """
    Soft lock on a player while they are in active trade negotiation.
    Composite PK: a player can only be locked once per session at a time.
    Released immediately on trade resolution (accept/reject/expire).
    """
    __tablename__ = "trade_locks"

    player_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True)
    trade_proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trade_proposals.id"), nullable=False)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trade_proposal: Mapped["TradeProposal"] = relationship(back_populates="locks")


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

class Snapshot(Base):
    """
    Full world state captured at each week boundary.
    Enables seek/resume without replaying from seq=0.
    world_state JSONB: all rosters, FAAB balances, standings totals, matchup scores.
    """
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    world_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_snapshots_session_seq", "session_id", "seq"),
    )
