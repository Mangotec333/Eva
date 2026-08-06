import { useCallback, useState } from 'react';
import { LayoutGrid, Zap, TrendingUp, Heart, Mic, Building2, ShoppingBag } from 'lucide-react';
import { useKanbanBoard } from '../hooks/useKanbanBoard';
import type { KanbanCard, KanbanColumn, KanbanColumnId, KanbanTrack } from '../types/kanban';

/*
 * KanbanBoard — lightweight Deal/Task board for Command Center.
 *
 * Drag-and-drop note: this component is built to be a drop-in swap for
 * `@hello-pangea/dnd` (MIT-licensed react-beautiful-dnd fork). The sandbox
 * used to build this PR had no npm registry access, so drag-and-drop is
 * implemented here with plain HTML5 drag events (`draggable`,
 * onDragStart/onDragOver/onDrop) instead. The column list, card shape, and
 * `useKanbanBoard` hook are unchanged either way — swapping in the real
 * library later only touches this file's render internals.
 */

// ── Column config (edit this array to add/rename/reorder columns) ─────────────
const KANBAN_COLUMNS: KanbanColumn[] = [
  { id: 'backlog', title: 'Backlog' },
  { id: 'in_progress', title: 'In Progress' },
  { id: 'blocked', title: 'Blocked' },
  { id: 'done', title: 'Done' },
];

// ── Track visual config — reuses the same tokens as PriorityStack.tsx ────────
const TRACK_ICONS: Record<KanbanTrack, React.ElementType> = {
  'EVA OS': Zap,
  'ACQUISITION': TrendingUp,
  'AGENCY': TrendingUp,
  'FAMILY': Heart,
  'SPEAKING': Mic,
  'STOREYS': Building2,
  'PUREPLATE': ShoppingBag,
};

const TRACK_COLORS: Record<KanbanTrack, { text: string; bg: string; border: string }> = {
  'EVA OS': { text: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30' },
  'ACQUISITION': { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
  'AGENCY': { text: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  'FAMILY': { text: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  'SPEAKING': { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  'STOREYS': { text: 'text-gray-400', bg: 'bg-gray-700/20', border: 'border-gray-700/40' },
  'PUREPLATE': { text: 'text-gray-500', bg: 'bg-gray-800/20', border: 'border-gray-800/40' },
};

function formatUpdatedAt(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

// ── Card ────────────────────────────────────────────────────────────────────
function CardTile({
  card,
  onDragStart,
  isDragging,
}: {
  card: KanbanCard;
  onDragStart: (e: React.DragEvent<HTMLDivElement>, cardId: string) => void;
  isDragging: boolean;
}) {
  const Icon = TRACK_ICONS[card.track] ?? Zap;
  const colors = TRACK_COLORS[card.track] ?? TRACK_COLORS['EVA OS'];

  return (
    <div
      draggable
      onDragStart={e => onDragStart(e, card.id)}
      className={`flex flex-col gap-2 px-3 py-2.5 rounded border bg-gray-800/50 border-gray-700/50
        hover:bg-gray-800 hover:border-gray-600 cursor-grab active:cursor-grabbing transition-colors
        ${isDragging ? 'opacity-40' : 'opacity-100'}`}
    >
      <div className="flex items-center gap-1.5">
        <Icon className={`w-3 h-3 flex-shrink-0 ${colors.text}`} />
        <span
          className={`font-mono text-[9px] font-semibold tracking-widest uppercase px-1.5 py-0.5 rounded border
            ${colors.bg} ${colors.text} ${colors.border}`}
        >
          {card.track}
        </span>
      </div>
      <div className="font-sans text-xs text-gray-200 leading-snug">{card.title}</div>
      <div className="font-mono text-[10px] text-gray-600">{formatUpdatedAt(card.updatedAt)}</div>
    </div>
  );
}

// ── Column ──────────────────────────────────────────────────────────────────
function BoardColumn({
  column,
  cards,
  draggingId,
  onDragStart,
  onDrop,
}: {
  column: KanbanColumn;
  cards: KanbanCard[];
  draggingId: string | null;
  onDragStart: (e: React.DragEvent<HTMLDivElement>, cardId: string) => void;
  onDrop: (columnId: KanbanColumnId) => void;
}) {
  const [isOver, setIsOver] = useState(false);

  return (
    <div
      onDragOver={e => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={() => {
        setIsOver(false);
        onDrop(column.id);
      }}
      className={`flex-1 min-w-[220px] flex flex-col gap-2 p-3 rounded-lg border transition-colors
        ${isOver ? 'bg-gray-800/40 border-cyan-500/30' : 'bg-gray-900 border-gray-800'}`}
    >
      <div className="flex items-center gap-2 px-1 pb-1 border-b border-gray-800">
        <span className="font-mono text-[10px] font-bold text-gray-400 tracking-widest uppercase">
          {column.title}
        </span>
        <span className="ml-auto font-mono text-[10px] text-gray-600">{cards.length}</span>
      </div>

      <div className="flex flex-col gap-2 min-h-[40px]">
        {cards.map(card => (
          <CardTile
            key={card.id}
            card={card}
            onDragStart={onDragStart}
            isDragging={draggingId === card.id}
          />
        ))}
        {cards.length === 0 && (
          <div className="font-mono text-[10px] text-gray-700 text-center py-4 select-none">
            No cards
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export function KanbanBoard() {
  const { cards, moveCard } = useKanbanBoard();
  const [draggingId, setDraggingId] = useState<string | null>(null);

  const handleDragStart = useCallback((e: React.DragEvent<HTMLDivElement>, cardId: string) => {
    setDraggingId(cardId);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', cardId);
  }, []);

  const handleDrop = useCallback(
    (columnId: KanbanColumnId) => {
      if (draggingId) {
        moveCard(draggingId, columnId);
      }
      setDraggingId(null);
    },
    [draggingId, moveCard]
  );

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <LayoutGrid className="w-4 h-4 text-cyan-400" />
        <span className="font-mono text-xs font-bold text-gray-400 tracking-widest uppercase">
          Deal / Task Board
        </span>
        <span className="ml-auto font-mono text-xs text-gray-600">{cards.length} CARDS</span>
      </div>

      {/* Columns */}
      <div className="flex gap-3 overflow-x-auto pb-1">
        {KANBAN_COLUMNS.map(column => (
          <BoardColumn
            key={column.id}
            column={column}
            cards={cards.filter(c => c.status === column.id)}
            draggingId={draggingId}
            onDragStart={handleDragStart}
            onDrop={handleDrop}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-800 pt-2">
        <p className="font-mono text-[10px] text-gray-600">
          ◆ Drag cards between columns. State persists locally — no backend wiring yet.
        </p>
      </div>
    </div>
  );
}

export default KanbanBoard;
