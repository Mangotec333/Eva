import { useState, useCallback } from 'react';
import { RefreshCw, Check, X, Edit2, ChevronDown, ChevronUp, Zap, CheckCircle } from 'lucide-react';
import { useContentQueue } from '../hooks/useContentQueue';
import type { ContentDraft } from '../hooks/useContentQueue';

// ─── Content type badge colors ────────────────────────────────────────────────
const TYPE_BADGE: Record<ContentDraft['content_type'], { bg: string; text: string; label: string }> = {
  thought_leader: { bg: 'bg-cyan-500/20', text: 'text-cyan-300', label: 'THOUGHT LEADER' },
  builder_log:    { bg: 'bg-amber-500/20', text: 'text-amber-300', label: 'BUILDER LOG' },
  human_story:    { bg: 'bg-purple-500/20', text: 'text-purple-300', label: 'HUMAN STORY' },
  teach:          { bg: 'bg-green-500/20', text: 'text-green-300', label: 'TEACH' },
};

const REACH_COLORS: Record<string, string> = {
  HIGH:   'text-green-400',
  MEDIUM: 'text-amber-400',
  LOW:    'text-gray-500',
};

// ─── Reject Modal ─────────────────────────────────────────────────────────────
function RejectModal({
  draftId,
  onConfirm,
  onCancel,
}: {
  draftId: string;
  onConfirm: (id: string, reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState('');
  return (
    <div className="fixed inset-0 z-[200] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-5 flex flex-col gap-4">
        <div className="font-mono text-sm font-bold text-red-400 tracking-wider">REJECT DRAFT</div>
        <textarea
          className="bg-gray-950 border border-gray-700 rounded p-3 text-sm text-gray-200 font-sans resize-none h-24 focus:outline-none focus:border-gray-500 placeholder:text-gray-600"
          placeholder="Reason for rejection (optional)..."
          value={reason}
          onChange={e => setReason(e.target.value)}
          autoFocus
        />
        <div className="flex gap-2">
          <button
            onClick={() => onConfirm(draftId, reason)}
            className="flex-1 px-4 py-2 bg-red-500/20 border border-red-500/50 text-red-400 rounded font-mono text-xs font-bold hover:bg-red-500/30 transition-colors"
          >
            CONFIRM REJECT
          </button>
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 text-gray-400 rounded font-mono text-xs font-bold hover:bg-gray-700 transition-colors"
          >
            CANCEL
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Draft Card ───────────────────────────────────────────────────────────────
function DraftCard({
  draft,
  onApprove,
  onReject,
  onEdit,
}: {
  draft: ContentDraft;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onEdit: (id: string, text: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(draft.draft_text);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);

  const badge = TYPE_BADGE[draft.content_type] ?? TYPE_BADGE.thought_leader;

  const handleSaveEdit = useCallback(async () => {
    setSaving(true);
    try {
      await onEdit(draft.id, editText);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }, [draft.id, editText, onEdit]);

  const handleApprove = useCallback(async () => {
    setApproving(true);
    try {
      await onApprove(draft.id);
    } finally {
      setApproving(false);
    }
  }, [draft.id, onApprove]);

  // Collapse text: show first ~160 chars
  const shortText = draft.draft_text.slice(0, 160);
  const isTruncated = draft.draft_text.length > 160;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3 hover:border-gray-700 transition-colors">
      {/* Type badge + platform */}
      <div className="flex items-center gap-2">
        <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${badge.bg} ${badge.text} tracking-widest`}>
          {badge.label}
        </span>
        <span className="font-mono text-[10px] text-gray-600 tracking-widest">· ACTIVITY STREAM</span>
        <span className={`ml-auto font-mono text-[10px] font-semibold ${REACH_COLORS[draft.reach_estimate] ?? 'text-gray-400'}`}>
          ◆ REACH: {draft.reach_estimate}
        </span>
      </div>

      {/* Hook */}
      <div className="font-mono text-base font-bold text-white leading-snug">
        "{draft.hook}"
      </div>

      {/* Draft text (collapsed / expanded / edit) */}
      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea
            className="bg-gray-950 border border-gray-700 rounded p-3 text-sm text-gray-200 font-sans resize-none h-40 focus:outline-none focus:border-cyan-500/60 placeholder:text-gray-600"
            value={editText}
            onChange={e => setEditText(e.target.value)}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              onClick={handleSaveEdit}
              disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-500/20 border border-cyan-500/50 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/30 transition-colors disabled:opacity-50"
            >
              {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
              SAVE
            </button>
            <button
              onClick={() => { setEditing(false); setEditText(draft.draft_text); }}
              className="px-3 py-1.5 bg-gray-800 border border-gray-700 text-gray-400 rounded font-mono text-xs hover:bg-gray-700 transition-colors"
            >
              CANCEL
            </button>
          </div>
        </div>
      ) : (
        <div className="text-sm text-gray-400 font-sans leading-relaxed">
          {expanded ? draft.draft_text : shortText}
          {isTruncated && !expanded && <span className="text-gray-600">…</span>}
          {isTruncated && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-2 inline-flex items-center gap-0.5 text-cyan-500/70 hover:text-cyan-400 font-mono text-xs transition-colors"
            >
              {expanded ? <><ChevronUp className="w-3 h-3" /> Collapse</> : <><ChevronDown className="w-3 h-3" /> Expand</>}
            </button>
          )}
        </div>
      )}

      {/* Hashtags */}
      {draft.hashtags && draft.hashtags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {draft.hashtags.map(tag => (
            <span key={tag} className="font-mono text-[10px] text-cyan-600 bg-cyan-500/10 px-2 py-0.5 rounded">
              {tag.startsWith('#') ? tag : `#${tag}`}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-gray-800">
        <button
          onClick={handleApprove}
          disabled={approving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/15 border border-green-500/40 text-green-400 rounded font-mono text-xs font-bold hover:bg-green-500/25 hover:border-green-500/70 transition-colors disabled:opacity-50 active:scale-95"
        >
          {approving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          APPROVE
        </button>
        <button
          onClick={() => setEditing(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded font-mono text-xs font-bold hover:bg-amber-500/20 hover:border-amber-500/60 transition-colors active:scale-95"
        >
          <Edit2 className="w-3 h-3" />
          EDIT
        </button>
        <button
          onClick={() => onReject(draft.id)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 rounded font-mono text-xs font-bold hover:bg-red-500/20 hover:border-red-500/60 transition-colors active:scale-95"
        >
          <X className="w-3 h-3" />
          REJECT
        </button>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function ContentQueue() {
  const {
    drafts,
    isOnline,
    isLoading,
    approveDraft,
    rejectDraft,
    approveAll,
    editDraft,
    generateNow,
    refresh,
  } = useContentQueue();

  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [approveAllLoading, setApproveAllLoading] = useState(false);
  const [approvedCount, setApprovedCount] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [spinning, setSpinning] = useState(false);

  const handleRefresh = useCallback(() => {
    setSpinning(true);
    refresh();
    setTimeout(() => setSpinning(false), 1200);
  }, [refresh]);

  const handleApproveAll = useCallback(async () => {
    const count = drafts.length;
    setApproveAllLoading(true);
    try {
      await approveAll();
      setApprovedCount(count);
      setTimeout(() => setApprovedCount(null), 5000);
    } catch {
      // silent — keep state
    } finally {
      setApproveAllLoading(false);
    }
  }, [drafts.length, approveAll]);

  const handleRejectConfirm = useCallback(
    async (id: string, reason: string) => {
      await rejectDraft(id, reason);
      setRejectTarget(null);
    },
    [rejectDraft]
  );

  const handleGenerateNow = useCallback(async () => {
    setGenerating(true);
    try {
      await generateNow();
    } finally {
      setGenerating(false);
    }
  }, [generateNow]);

  return (
    <>
      {rejectTarget && (
        <RejectModal
          draftId={rejectTarget}
          onConfirm={handleRejectConfirm}
          onCancel={() => setRejectTarget(null)}
        />
      )}

      <div className="bg-gray-900/60 border border-gray-800 rounded-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900">
          <div>
            <div className="font-mono text-xs font-bold text-gray-100 tracking-widest uppercase">
              CONTENT QUEUE
            </div>
            <div className="font-mono text-[10px] text-gray-500 tracking-wide mt-0.5">
              Vineet Ravi · LinkedIn · Today's drafts
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Draft count badge */}
            <span className="font-mono text-[10px] font-bold px-2.5 py-1 bg-gray-800 border border-gray-700 rounded text-gray-400 tracking-widest">
              {isLoading ? '…' : `${drafts.length} DRAFT${drafts.length !== 1 ? 'S' : ''} PENDING`}
            </span>

            {/* Approve All */}
            {isOnline && drafts.length > 0 && (
              <button
                onClick={handleApproveAll}
                disabled={approveAllLoading}
                className="flex items-center gap-1.5 px-3 py-1 bg-cyan-500/20 border border-cyan-400/50 text-cyan-300 rounded font-mono text-xs font-bold hover:bg-cyan-500/30 hover:border-cyan-400/80 transition-colors disabled:opacity-50 active:scale-95"
              >
                {approveAllLoading ? (
                  <RefreshCw className="w-3 h-3 animate-spin" />
                ) : (
                  <CheckCircle className="w-3 h-3" />
                )}
                APPROVE ALL
              </button>
            )}

            {/* Refresh */}
            <button
              onClick={handleRefresh}
              className="p-1.5 text-gray-600 hover:text-gray-300 transition-colors rounded hover:bg-gray-800"
              title="Refresh content queue"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-4">
          {/* API Offline */}
          {!isOnline && !isLoading && (
            <div className="flex flex-col items-center justify-center py-8 gap-3 text-center">
              <Zap className="w-8 h-8 text-gray-700" />
              <div className="font-mono text-sm text-gray-500">
                Content Engine offline — drafts generate nightly at 11pm
              </div>
              <div className="font-mono text-[10px] text-gray-700 bg-gray-950 border border-gray-800 rounded px-3 py-1.5">
                cd ~/Eva/modules/content-engine &amp;&amp; python main.py
              </div>
              <div className="font-mono text-[10px] text-gray-600">
                ~/Eva/eva-start.sh
              </div>
            </div>
          )}

          {/* Loading */}
          {isLoading && (
            <div className="flex items-center justify-center py-8 gap-2">
              <RefreshCw className="w-4 h-4 text-gray-600 animate-spin" />
              <span className="font-mono text-xs text-gray-600">Checking content engine…</span>
            </div>
          )}

          {/* Approved All success state */}
          {approvedCount !== null && (
            <div className="flex items-center justify-center gap-2 py-6">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="font-mono text-sm font-bold text-green-400">
                ✓ {approvedCount} post{approvedCount !== 1 ? 's' : ''} approved and queued for LinkedIn
              </span>
            </div>
          )}

          {/* Empty state */}
          {isOnline && !isLoading && drafts.length === 0 && approvedCount === null && (
            <div className="flex flex-col items-center justify-center py-8 gap-3 text-center">
              <CheckCircle className="w-8 h-8 text-gray-700" />
              <div className="font-mono text-sm text-gray-500">
                No drafts pending. EVA generates tonight at 11pm.
              </div>
              <button
                onClick={handleGenerateNow}
                disabled={generating}
                className="flex items-center gap-1.5 px-4 py-2 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/25 hover:border-cyan-500/70 transition-colors disabled:opacity-50 active:scale-95"
              >
                {generating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                GENERATE NOW
              </button>
            </div>
          )}

          {/* Draft cards */}
          {isOnline && !isLoading && drafts.length > 0 && approvedCount === null && (
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
              {drafts.map(draft => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  onApprove={approveDraft}
                  onReject={setRejectTarget}
                  onEdit={editDraft}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
