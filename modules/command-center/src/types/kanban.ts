// Kanban / Deal-Task Board types
//
// This is a lightweight, local-only project-management view for Command
// Center. Data is currently seeded from a static JSON stub
// (src/data/kanbanSeed.json) and persisted to localStorage — no backend
// wiring yet. Persistent DB storage is intentionally deferred to a later
// PR per standing design principle.

/** EVA priority track a card belongs to. Mirrors the categories used in
 * PriorityStack.tsx (EVA OS, Acquisition, Agency, Storeys, Speaking, etc.) */
export type KanbanTrack =
  | 'EVA OS'
  | 'ACQUISITION'
  | 'AGENCY'
  | 'STOREYS'
  | 'SPEAKING'
  | 'FAMILY'
  | 'PUREPLATE';

/** Column id — keep in sync with the KANBAN_COLUMNS const array in
 * KanbanBoard.tsx. Using a string union (rather than a hardcoded enum)
 * keeps the column list configurable. */
export type KanbanColumnId = 'backlog' | 'in_progress' | 'blocked' | 'done';

export interface KanbanColumn {
  id: KanbanColumnId;
  title: string;
}

export interface KanbanCard {
  id: string;
  title: string;
  track: KanbanTrack;
  status: KanbanColumnId;
  updatedAt: string; // ISO 8601 timestamp
}
