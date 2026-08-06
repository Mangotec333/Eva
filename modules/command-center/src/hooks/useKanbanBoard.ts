import { useCallback, useEffect, useState } from 'react';
import type { KanbanCard, KanbanColumnId } from '../types/kanban';
import kanbanSeed from '../data/kanbanSeed.json';

const STORAGE_KEY = 'eva_kanban_board_v1';

function loadInitialCards(): KanbanCard[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) return parsed as KanbanCard[];
    }
  } catch {
    // fall through to seed data
  }
  return kanbanSeed as KanbanCard[];
}

interface UseKanbanBoardResult {
  cards: KanbanCard[];
  /** Move a card to a new column, stamping updatedAt. No-op if the card
   * doesn't exist or is already in that column. */
  moveCard: (cardId: string, toColumn: KanbanColumnId) => void;
  /** Reset board back to the seed data (clears localStorage override). */
  resetBoard: () => void;
}

export function useKanbanBoard(): UseKanbanBoardResult {
  const [cards, setCards] = useState<KanbanCard[]>(() => loadInitialCards());

  // Persist to localStorage whenever cards change so state survives refresh.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(cards));
    } catch {
      // localStorage unavailable (e.g. private mode) — fail silently.
    }
  }, [cards]);

  const moveCard = useCallback((cardId: string, toColumn: KanbanColumnId) => {
    setCards(prev =>
      prev.map(card =>
        card.id === cardId && card.status !== toColumn
          ? { ...card, status: toColumn, updatedAt: new Date().toISOString() }
          : card
      )
    );
  }, []);

  const resetBoard = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setCards(kanbanSeed as KanbanCard[]);
  }, []);

  return { cards, moveCard, resetBoard };
}
