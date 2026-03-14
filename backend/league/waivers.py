"""
Waiver resolution — two modes, same output shape.

FAAB (Free Agent Acquisition Budget)
    Sealed-bid auction. Teams bid secretly; highest dollar wins each contested
    player. Bid amount is permanently deducted from the team's budget. Ties
    broken by waiver priority. No limit on claims per team per period.

    Best for: leagues that want a market-driven, strategic waiver system.

PRIORITY (Waiver Priority)
    Ordered claims. Teams are ranked in priority order (index 0 = highest).
    The highest-priority team that wants a contested player gets them. No FAAB
    budget involved — claims are free. One successful claim per team per waiver
    period (consistent with Yahoo/ESPN standard leagues).

    Priority reset modes (applied after resolution):
        ROLLING          Winner(s) drop to the bottom of the priority list.
        SEASON_LONG      Priority never changes after initial assignment.
        WEEKLY_STANDINGS Re-ranked each week: worst record → highest priority.
                         (Applied at WEEK_END, not here.)

Both functions return the same types:
    list[WaiverClaim]       — awarded claims in resolution order
    dict[str, int]          — updated FAAB balances (unchanged in PRIORITY mode)
    set[str]                — team_ids that won at least one claim (for ROLLING reset)
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teams.context import WaiverBid


@dataclass
class WaiverClaim:
    """An awarded waiver claim after resolution."""

    team_id: str
    add_player_id: str
    drop_player_id: str | None
    bid_amount: int  # always 0 in PRIORITY mode


# ---------------------------------------------------------------------------
# FAAB resolution
# ---------------------------------------------------------------------------


def resolve_faab_auction(
    bids_by_team: dict[str, list[WaiverBid]],
    faab_balances: dict[str, int],
    waiver_priority: list[str],
) -> tuple[list[WaiverClaim], dict[str, int], set[str]]:
    """
    FAAB sealed-bid auction.

    Args:
        bids_by_team:    team_id -> ordered list of WaiverBid (priority 1 = top choice).
        faab_balances:   team_id -> current FAAB balance (will not be mutated).
        waiver_priority: Ordered team_ids used as tiebreaker (index 0 = best).

    Returns:
        (claims, updated_balances, winning_team_ids)
    """
    balances = dict(faab_balances)
    priority_index: dict[str, int] = {tid: i for i, tid in enumerate(waiver_priority)}

    # Flatten and sort: highest bid first; waiver priority as tiebreaker
    all_bids: list[tuple[str, WaiverBid]] = [
        (team_id, bid) for team_id, team_bids in bids_by_team.items() for bid in team_bids
    ]
    all_bids.sort(
        key=lambda x: (
            -x[1].bid_amount,
            priority_index.get(x[0], 999),
            x[1].priority,
        )
    )

    claimed_players: set[str] = set()
    winning_team_ids: set[str] = set()
    claims: list[WaiverClaim] = []

    for team_id, bid in all_bids:
        if bid.add_player_id in claimed_players:
            continue
        if balances.get(team_id, 0) < bid.bid_amount:
            continue

        balances[team_id] = balances.get(team_id, 0) - bid.bid_amount
        claimed_players.add(bid.add_player_id)
        winning_team_ids.add(team_id)
        claims.append(
            WaiverClaim(
                team_id=team_id,
                add_player_id=bid.add_player_id,
                drop_player_id=bid.drop_player_id,
                bid_amount=bid.bid_amount,
            )
        )

    return claims, balances, winning_team_ids


# ---------------------------------------------------------------------------
# Priority resolution
# ---------------------------------------------------------------------------


def resolve_priority_claims(
    bids_by_team: dict[str, list[WaiverBid]],
    waiver_priority: list[str],
) -> tuple[list[WaiverClaim], dict[str, int], set[str]]:
    """
    Waiver priority resolution.

    Teams are processed in waiver_priority order (index 0 = highest priority).
    Each team's claims are evaluated in their own priority order (1 = top choice).
    A player can only be claimed by one team.
    Each team wins at most one claim per waiver period (standard league rules).

    Args:
        bids_by_team:    team_id -> ordered list of WaiverBid.
        waiver_priority: Ordered team_ids (index 0 = highest priority).

    Returns:
        (claims, unchanged_balances, winning_team_ids)
        unchanged_balances is an empty dict — no FAAB in priority mode.
    """
    claimed_players: set[str] = set()
    winning_team_ids: set[str] = set()
    claims: list[WaiverClaim] = []

    for team_id in waiver_priority:
        team_bids = bids_by_team.get(team_id)
        if not team_bids:
            continue

        # Evaluate this team's claims in their own preference order
        sorted_bids = sorted(team_bids, key=lambda b: b.priority)
        for bid in sorted_bids:
            if bid.add_player_id in claimed_players:
                continue  # already taken by a higher-priority team
            # Award first available claim to this team (one per period)
            claimed_players.add(bid.add_player_id)
            winning_team_ids.add(team_id)
            claims.append(
                WaiverClaim(
                    team_id=team_id,
                    add_player_id=bid.add_player_id,
                    drop_player_id=bid.drop_player_id,
                    bid_amount=0,
                )
            )
            break  # one successful claim per team per waiver period

    return claims, {}, winning_team_ids
