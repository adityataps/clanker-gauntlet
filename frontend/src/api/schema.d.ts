/**
 * AUTO-GENERATED — do not edit by hand.
 * Run `npm run generate-api` to regenerate from the live backend schema.
 *
 * Source: http://localhost:8000/openapi.json
 */

export interface paths {
  "/auth/register": {
    post: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["RegisterRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["TokenResponse"];
          };
        };
        422: { content: { "application/json": components["schemas"]["HTTPValidationError"] } };
      };
    };
  };
  "/auth/login": {
    post: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["LoginRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["TokenResponse"];
          };
        };
        422: { content: { "application/json": components["schemas"]["HTTPValidationError"] } };
      };
    };
  };
  "/auth/me": {
    get: {
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["UserResponse"];
          };
        };
      };
    };
  };
  "/auth/me/api-key": {
    put: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["ApiKeyRequest"];
        };
      };
      responses: { 204: { content: never } };
    };
    delete: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["ApiKeyDeleteRequest"];
        };
      };
      responses: { 204: { content: never } };
    };
  };
  "/leagues": {
    get: {
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["LeagueResponse"][];
          };
        };
      };
    };
    post: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["CreateLeagueRequest"];
        };
      };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["LeagueResponse"];
          };
        };
      };
    };
  };
  "/leagues/{league_id}": {
    get: {
      parameters: { path: { league_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["LeagueResponse"];
          };
        };
      };
    };
    patch: {
      parameters: { path: { league_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["UpdateLeagueRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["LeagueResponse"];
          };
        };
      };
    };
    delete: {
      parameters: { path: { league_id: string } };
      responses: { 204: { content: never } };
    };
  };
  "/leagues/{league_id}/api-key": {
    get: {
      parameters: { path: { league_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["LeagueApiKeyStatusResponse"];
          };
        };
      };
    };
    put: {
      parameters: { path: { league_id: string } };
      requestBody: {
        content: {
          "application/json": { provider: string; api_key: string };
        };
      };
      responses: { 204: { content: never } };
    };
    delete: {
      parameters: { path: { league_id: string } };
      requestBody: {
        content: {
          "application/json": { provider: string };
        };
      };
      responses: { 204: { content: never } };
    };
  };
  "/leagues/{league_id}/members": {
    get: {
      parameters: { path: { league_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["MemberResponse"][];
          };
        };
      };
    };
    post: {
      parameters: { path: { league_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["AddMemberRequest"];
        };
      };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["MemberResponse"];
          };
        };
      };
    };
  };
  "/leagues/{league_id}/members/{user_id}": {
    delete: {
      parameters: { path: { league_id: string; user_id: string } };
      responses: { 204: { content: never } };
    };
    patch: {
      parameters: { path: { league_id: string; user_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["UpdateMemberRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["MemberResponse"];
          };
        };
      };
    };
  };
  "/leagues/{league_id}/members/me/leave": {
    post: {
      parameters: { path: { league_id: string } };
      responses: { 204: { content: never } };
    };
  };
  "/leagues/{league_id}/invites": {
    get: {
      parameters: { path: { league_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["InviteResponse"][];
          };
        };
      };
    };
    post: {
      parameters: { path: { league_id: string } };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["InviteResponse"];
          };
        };
      };
    };
  };
  "/leagues/join/{token}": {
    post: {
      parameters: { path: { token: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["LeagueResponse"];
          };
        };
      };
    };
  };
  "/leagues/{league_id}/sessions": {
    get: {
      parameters: { path: { league_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["SessionResponse"][];
          };
        };
      };
    };
    post: {
      parameters: { path: { league_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["CreateSessionRequest"];
        };
      };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["SessionResponse"];
          };
        };
      };
    };
  };
  "/sessions/{session_id}/join": {
    post: {
      parameters: { path: { session_id: string } };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["JoinSessionResponse"];
          };
        };
      };
    };
  };
  "/sessions/{session_id}/leave": {
    post: {
      parameters: { path: { session_id: string } };
      responses: { 204: { content: never } };
    };
  };
  "/sessions/{session_id}/trades": {
    get: {
      parameters: { path: { session_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["TradeResponse"][];
          };
        };
      };
    };
    post: {
      parameters: { path: { session_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["ProposeTradeRequest"];
        };
      };
      responses: {
        201: {
          content: {
            "application/json": components["schemas"]["TradeResponse"];
          };
        };
      };
    };
  };
  "/trades/{trade_id}": {
    get: {
      parameters: { path: { trade_id: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["TradeResponse"];
          };
        };
      };
    };
  };
  "/trades/{trade_id}/respond": {
    post: {
      parameters: { path: { trade_id: string } };
      requestBody: {
        content: {
          "application/json": components["schemas"]["RespondTradeRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["TradeResponse"];
          };
        };
      };
    };
  };
  "/trades/{trade_id}/cancel": {
    post: {
      parameters: { path: { trade_id: string } };
      responses: { 204: { content: never } };
    };
  };
  "/scripts": {
    get: {
      responses: {
        200: { content: { "application/json": components["schemas"]["ScriptResponse"][] } };
      };
    };
  };
  "/scripts/{script_id}": {
    get: {
      parameters: { path: { script_id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["ScriptResponse"] } };
      };
    };
  };
  "/sessions/{session_id}": {
    get: {
      parameters: { path: { session_id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["SessionDetailResponse"] } };
      };
    };
  };
  "/sessions/{session_id}/start": {
    post: {
      parameters: { path: { session_id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["SessionDetailResponse"] } };
      };
    };
  };
  "/sessions/{session_id}/pause": {
    post: {
      parameters: { path: { session_id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["SessionDetailResponse"] } };
      };
    };
  };
  "/sessions/{session_id}/lineup": {
    get: {
      parameters: { path: { session_id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["LineupResponse"] } };
      };
    };
    put: {
      parameters: { path: { session_id: string } };
      requestBody: {
        content: { "application/json": components["schemas"]["SaveLineupRequest"] };
      };
      responses: {
        200: { content: { "application/json": components["schemas"]["LineupResponse"] } };
      };
    };
  };
  "/users/search": {
    get: {
      parameters: { query: { q: string } };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["UserSearchResult"][];
          };
        };
      };
    };
  };
  "/admin/stats": {
    get: {
      responses: { 200: { content: { "application/json": components["schemas"]["AdminStats"] } } };
    };
  };
  "/admin/users": {
    get: {
      responses: { 200: { content: { "application/json": components["schemas"]["AdminUser"][] } } };
    };
  };
  "/admin/leagues": {
    get: {
      responses: {
        200: { content: { "application/json": components["schemas"]["AdminLeague"][] } };
      };
    };
  };
  "/admin/scripts": {
    get: {
      responses: {
        200: { content: { "application/json": components["schemas"]["AdminScript"][] } };
      };
    };
  };
  "/admin/scripts/compile": {
    post: {
      requestBody: { content: { "application/json": components["schemas"]["CompileRequest"] } };
      responses: {
        202: { content: { "application/json": components["schemas"]["CompileResponse"] } };
      };
    };
  };
}

export interface components {
  schemas: {
    RegisterRequest: {
      email: string;
      password: string;
      display_name: string;
    };
    LoginRequest: {
      email: string;
      password: string;
    };
    TokenResponse: {
      access_token: string;
      token_type: string;
    };
    UserResponse: {
      id: string;
      email: string;
      display_name: string;
      has_keys: Record<string, boolean>;
    };
    ApiKeyRequest: {
      provider: string;
      api_key: string;
    };
    ApiKeyDeleteRequest: {
      provider: string;
    };
    LeagueResponse: {
      id: string;
      name: string;
      created_by: string;
      session_creation: string;
      max_members: number;
      is_auto_generated: boolean;
      allow_shared_key: boolean;
      has_league_keys: Record<string, boolean>;
      created_at: string;
      member_count: number;
      /** The requesting user's role in this league; null if not a member. */
      my_role: string | null;
    };
    LeagueApiKeyStatusResponse: {
      has_keys: Record<string, boolean>;
    };
    CreateLeagueRequest: {
      name: string;
      description?: string | null;
      sport?: string;
      session_creation?: string;
      allow_shared_key?: boolean;
    };
    UpdateLeagueRequest: {
      name?: string;
      description?: string | null;
      session_creation?: string;
      allow_shared_key?: boolean;
    };
    MemberResponse: {
      user_id: string;
      display_name: string;
      email: string;
      role: string;
      status: string;
      joined_at: string;
    };
    AddMemberRequest: {
      user_id: string;
      role?: string;
    };
    UpdateMemberRequest: {
      role: string;
    };
    InviteResponse: {
      id: string;
      league_id: string;
      token: string;
      created_by: string;
      expires_at: string;
      used_at: string | null;
    };
    CreateSessionRequest: {
      name: string;
      script_id: string;
      sport: string;
      season: number;
      script_speed: string;
      waiver_mode?: string;
      priority_reset?: string | null;
      compression_factor?: number | null;
      max_teams?: number;
      scoring_config?: Record<string, unknown>;
    };
    SessionResponse: {
      id: string;
      name: string;
      sport: string;
      season: number;
      status: string;
      script_speed: string;
      waiver_mode: string;
      max_teams: number;
      league_id: string | null;
      owner_id: string;
      team_id?: string | null;
      created_at: string;
      current_teams: number;
    };
    JoinSessionResponse: {
      session_id: string;
      team_id: string;
    };
    ProposeTradeRequest: {
      receiving_team_id: string;
      offered_player_ids: string[];
      requested_player_ids: string[];
      note?: string | null;
      expires_hours?: number;
    };
    RespondTradeRequest: {
      accept: boolean;
    };
    TradeResponse: {
      id: string;
      session_id: string;
      proposing_team_id: string;
      receiving_team_id: string;
      offered_player_ids: string[];
      requested_player_ids: string[];
      status: string;
      note: string | null;
      proposed_at: string;
      resolved_at: string | null;
      locks: Array<{ player_id: string; locked_until: string }>;
    };
    UserSearchResult: {
      id: string;
      email: string;
      display_name: string;
    };
    ScriptResponse: {
      id: string;
      sport: string;
      season: number;
      season_type: string;
      total_events: number;
      status: string;
      compiled_at: string | null;
    };
    TeamSummary: {
      id: string;
      name: string;
      type: string;
      faab_balance: number;
    };
    ScriptSummary: {
      id: string;
      sport: string;
      season: number;
      season_type: string;
      total_events: number;
    };
    SessionDetailResponse: {
      id: string;
      name: string;
      sport: string;
      season: number;
      status: string;
      script_speed: string;
      waiver_mode: string;
      current_seq: number;
      current_week: number;
      is_running: boolean;
      script: components["schemas"]["ScriptSummary"];
      teams: components["schemas"]["TeamSummary"][];
      league_id: string | null;
      created_at: string;
    };
    RosterPlayer: {
      player_id: string;
      name: string;
      position: string;
      nfl_team: string;
      projected_points: number | null;
      status: string;
      opponent: string | null;
    };
    LineupResponse: {
      week: number;
      deadline: string | null;
      locked: boolean;
      slots: Record<string, components["schemas"]["RosterPlayer"] | null>;
      bench: components["schemas"]["RosterPlayer"][];
    };
    SaveLineupRequest: {
      slots: Record<string, string | null>;
    };
    HTTPValidationError: {
      detail: Array<{ loc: (string | number)[]; msg: string; type: string }>;
    };
    AdminStats: {
      user_count: number;
      league_count: number;
      session_count: number;
      script_count: number;
    };
    AdminUser: {
      id: string;
      email: string;
      display_name: string;
      created_at: string;
    };
    AdminLeague: {
      id: string;
      name: string;
      created_by: string;
      member_count: number;
      session_count: number;
      created_at: string;
    };
    AdminScript: {
      id: string;
      sport: string;
      season: number;
      season_type: string;
      status: string;
      total_events: number;
      compiled_at: string | null;
    };
    CompileRequest: {
      sport?: string;
      season?: number;
      season_type?: string;
      force?: boolean;
    };
    CompileResponse: {
      script_id: string;
      status: string;
      message: string;
    };
  };
}
