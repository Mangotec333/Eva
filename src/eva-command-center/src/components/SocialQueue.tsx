import { useState, useCallback } from 'react';
import {
  RefreshCw,
  Edit2,
  Check,
  X,
  Trash2,
  Send,
  Zap,
  Youtube,
  WifiOff,
  ExternalLink,
  Linkedin,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';
import {
  useSocialQueue,
  type SocialPost,
  type PostVoice,
  type PostPillar,
  type PostStatus,
  type PostToLinkedInResult,
} from '../hooks/useContentQueue';

// ─── Constants ────────────────────────────────────────────────────────────────

const TABS: { label: string; value: 'all' | PostStatus }[] = [
  { label: 'All',      value: 'all' },
  { label: 'Draft',    value: 'draft' },
  { label: 'Approved', value: 'approved' },
  { label: 'Posted',   value: 'posted' },
  { label: 'Failed',   value: 'failed' },
];

// ─── Voice config ─────────────────────────────────────────────────────────────

const VOICE_CONFIG: Record<PostVoice, {
  label: string;
  bg: string;
  text: string;
  border: string;
  activeBg: string;
  activeBorder: string;
}> = {
  operator: {
    label: 'OPERATOR',
    bg:           'bg-orange-500/10',
    text:         'text-orange-400',
    border:       'border-orange-500/30',
    activeBg:     'bg-orange-500/20',
    activeBorder: 'border-orange-500/60',
  },
  builder: {
    label: 'BUILDER',
    bg:           'bg-cyan-500/10',
    text:         'text-cyan-400',
    border:       'border-cyan-500/30',
    activeBg:     'bg-cyan-500/20',
    activeBorder: 'border-cyan-500/60',
  },
  thinker: {
    label: 'THINKER',
    bg:           'bg-purple-500/10',
    text:         'text-purple-400',
    border:       'border-purple-500/30',
    activeBg:     'bg-purple-500/20',
    activeBorder: 'border-purple-500/60',
  },
};

// ─── Pillar config ────────────────────────────────────────────────────────────

const PILLAR_CONFIG: Record<PostPillar, {
  label: string;
  shortLabel: string;
  bg: string;
  text: string;
  border: string;
  activeBg: string;
  activeBorder: string;
}> = {
  healthcare_real_estate: {
    label:        'Healthcare RE',
    shortLabel:   'HEALTHCARE RE',
    bg:           'bg-green-500/10',
    text:         'text-green-400',
    border:       'border-green-500/30',
    activeBg:     'bg-green-500/20',
    activeBorder: 'border-green-500/60',
  },
  ai_and_acquisition: {
    label:        'AI + Acquisition',
    shortLabel:   'AI + ACQUISITION',
    bg:           'bg-cyan-500/10',
    text:         'text-cyan-400',
    border:       'border-cyan-500/30',
    activeBg:     'bg-cyan-500/20',
    activeBorder: 'border-cyan-500/60',
  },
  longevity_and_wealth: {
    label:        'Longevity + Wealth',
    shortLabel:   'LONGEVITY',
    bg:           'bg-amber-500/10',
    text:         'text-amber-400',
    border:       'border-amber-500/30',
    activeBg:     'bg-amber-500/20',
    activeBorder: 'border-amber-500/60',
  },
};

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<PostStatus, { bg: string; text: string; border: string; label: string }> = {
  draft:    { bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30',   label: 'DRAFT' },
  approved: { bg: 'bg-amber-500/15',  text: 'text-amber-400',  border: 'border-amber-500/30',  label: 'APPROVED' },
  posted:   { bg: 'bg-green-500/15',  text: 'text-green-400',  border: 'border-green-500/30',  label: 'POSTED' },
  failed:   { bg: 'bg-red-500/15',    text: 'text-red-400',    border: 'border-red-500/30',    label: 'FAILED' },
};

// ─── Small badge components ───────────────────────────────────────────────────

function VoiceBadge({ voice }: { voice: PostVoice }) {
  const cfg = VOICE_CONFIG[voice];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-bold tracking-widest ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

function PillarBadge({ pillar }: { pillar: PostPillar }) {
  const cfg = PILLAR_CONFIG[pillar];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-semibold tracking-wider ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.shortLabel}
    </span>
  );
}

function StatusBadge({ status }: { status: PostStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-bold ${cfg.bg} ${cfg.text} ${cfg.border}`}>
      {cfg.label}
    </span>
  );
}

function CharCountBadge({ count }: { count: number }) {
  const over = count > 2000;
  const near = count > 1800;
  return (
    <span className={`px-2 py-0.5 rounded border font-mono text-[10px] font-semibold tabular-nums ${
      over  ? 'bg-red-500/15 text-red-400 border-red-500/30' :
      near  ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
              'bg-gray-200/30 text-gray-500 border-gray-200/40'
    }`}>
      {count} chars
    </span>
  );
}

// ─── Modal overlay ────────────────────────────────────────────────────────────

function ModalOverlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-[200] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      {children}
    </div>
  );
}

// ─── Post Confirmation Modal ──────────────────────────────────────────────────

function PostConfirmModal({
  post,
  onConfirm,
  onCancel,
}: {
  post: SocialPost;
  onConfirm: () => Promise<PostToLinkedInResult>;
  onCancel: () => void;
}) {
  const [posting, setPosting]           = useState(false);
  const [result, setResult]             = useState<PostToLinkedInResult | null>(null);

  const handlePost = useCallback(async () => {
    setPosting(true);
    try {
      const res = await onConfirm();
      setResult(res);
    } catch (e) {
      setResult({ success: false, error: e instanceof Error ? e.message : 'Unknown error' });
    } finally {
      setPosting(false);
    }
  }, [onConfirm]);

  const charCount = post.main_post.length;

  return (
    <ModalOverlay onClose={onCancel}>
      <div className="w-full max-w-lg bg-gray-50 border border-gray-200 rounded-xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-2">
            <Linkedin className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-sm font-bold text-cyan-400 tracking-wider">POST TO LINKEDIN</span>
          </div>
          <button onClick={onCancel} className="p-1 text-gray-500 hover:text-gray-500 rounded transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
          {result ? (
            result.success ? (
              <div className="flex flex-col items-center justify-center py-6 gap-3 text-center">
                <div className="w-10 h-10 rounded-full bg-green-500/15 border border-green-500/30 flex items-center justify-center">
                  <Check className="w-5 h-5 text-green-400" />
                </div>
                <div className="font-mono text-sm font-bold text-green-400">Posted to LinkedIn!</div>
                {result.linkedin_url && (
                  <a
                    href={result.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 font-mono text-xs text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors"
                  >
                    <ExternalLink className="w-3 h-3" />
                    View on LinkedIn
                  </a>
                )}
              </div>
            ) : (
              <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                <p className="font-mono text-xs text-red-400 font-semibold">Post failed</p>
                {result.error && <p className="font-sans text-xs text-red-400/80 mt-1">{result.error}</p>}
              </div>
            )
          ) : (
            <>
              {/* Badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <VoiceBadge voice={post.voice} />
                <PillarBadge pillar={post.pillar} />
                <CharCountBadge count={charCount} />
              </div>

              {/* Main post */}
              <div>
                <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-2">Main Post</div>
                <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 font-sans text-sm text-gray-500 leading-relaxed whitespace-pre-wrap max-h-56 overflow-y-auto">
                  {post.main_post}
                </div>
              </div>

              {/* Comment post */}
              {post.comment_post && (
                <div>
                  <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-2">
                    Will post as first comment
                  </div>
                  <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 font-sans text-sm text-gray-500 leading-relaxed whitespace-pre-wrap max-h-36 overflow-y-auto">
                    {post.comment_post}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-2 shrink-0">
          {result?.success ? (
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-gray-100 border border-gray-200 text-gray-500 rounded font-mono text-xs font-bold hover:bg-gray-200 transition-colors"
            >
              Close
            </button>
          ) : result?.success === false ? (
            <>
              <button onClick={onCancel} className="px-3 py-1.5 font-mono text-xs text-gray-500 hover:text-gray-500 border border-gray-200 rounded transition-colors">Cancel</button>
              <button
                onClick={handlePost}
                disabled={posting}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/25 disabled:opacity-50 transition-all"
              >
                <RefreshCw className="w-3 h-3" /> Retry
              </button>
            </>
          ) : (
            <>
              <button onClick={onCancel} className="px-3 py-1.5 font-mono text-xs text-gray-500 hover:text-gray-500 border border-gray-200 rounded transition-colors">Cancel</button>
              <button
                onClick={handlePost}
                disabled={posting}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/25 hover:border-cyan-500/70 active:scale-95 disabled:opacity-50 transition-all"
              >
                {posting
                  ? <><Loader2 className="w-3 h-3 animate-spin" /> Posting…</>
                  : <><Send className="w-3 h-3" /> Post to LinkedIn</>}
              </button>
            </>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─── Generate Post Panel ──────────────────────────────────────────────────────

function GeneratePanel({
  onGenerate,
  onClose,
}: {
  onGenerate: (voice: PostVoice, pillar: PostPillar, topicHint?: string) => Promise<void>;
  onClose: () => void;
}) {
  const [voice, setVoice]       = useState<PostVoice>('operator');
  const [pillar, setPillar]     = useState<PostPillar>('healthcare_real_estate');
  const [topicHint, setTopic]   = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError]           = useState('');
  const [success, setSuccess]       = useState(false);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError('');
    try {
      await onGenerate(voice, pillar, topicHint || undefined);
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  }, [voice, pillar, topicHint, onGenerate, onClose]);

  const voices: PostVoice[]   = ['operator', 'builder', 'thinker'];
  const pillars: PostPillar[] = ['healthcare_real_estate', 'ai_and_acquisition', 'longevity_and_wealth'];

  return (
    <div className="bg-gray-100/60 border border-gray-200/60 rounded-lg p-4 flex flex-col gap-4">
      {/* Panel header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-mono text-xs font-bold text-cyan-400 tracking-widest uppercase">Generate Post</span>
        </div>
        <button onClick={onClose} className="p-1 text-gray-500 hover:text-gray-500 rounded transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Voice selector */}
      <div>
        <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-2">Voice</div>
        <div className="flex items-center gap-2">
          {voices.map(v => {
            const cfg = VOICE_CONFIG[v];
            const active = voice === v;
            return (
              <button
                key={v}
                onClick={() => setVoice(v)}
                className={`px-3 py-1.5 rounded border font-mono text-[11px] font-bold tracking-widest transition-all ${
                  active
                    ? `${cfg.activeBg} ${cfg.text} ${cfg.activeBorder}`
                    : `bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-300 hover:text-gray-500`
                }`}
              >
                {cfg.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Pillar selector */}
      <div>
        <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-2">Pillar</div>
        <div className="flex items-center gap-2 flex-wrap">
          {pillars.map(p => {
            const cfg = PILLAR_CONFIG[p];
            const active = pillar === p;
            return (
              <button
                key={p}
                onClick={() => setPillar(p)}
                className={`px-3 py-1.5 rounded border font-mono text-[11px] font-bold transition-all ${
                  active
                    ? `${cfg.activeBg} ${cfg.text} ${cfg.activeBorder}`
                    : `bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-300 hover:text-gray-500`
                }`}
              >
                {cfg.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Topic hint */}
      <div>
        <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-2">Topic Hint (optional)</div>
        <input
          type="text"
          value={topicHint}
          onChange={e => setTopic(e.target.value)}
          placeholder="e.g. HELOC strategy, AI diagnostic tools, longevity supplements…"
          className="w-full bg-white border border-gray-200 rounded px-3 py-2 font-sans text-sm text-gray-800 placeholder:text-gray-500 focus:outline-none focus:border-cyan-500/60 transition-colors"
          onKeyDown={e => { if (e.key === 'Enter' && !generating) handleGenerate(); }}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded font-mono text-xs text-red-400">
          ⚠ {error}
        </div>
      )}

      {/* Generate button */}
      <button
        onClick={handleGenerate}
        disabled={generating || success}
        className={`flex items-center justify-center gap-2 w-full px-4 py-2.5 border rounded font-mono text-xs font-bold active:scale-[0.98] transition-all duration-150 disabled:cursor-not-allowed ${
          success
            ? 'bg-green-500/15 border-green-500/40 text-green-400'
            : 'bg-cyan-500/10 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/20 hover:border-cyan-500/70 disabled:opacity-60'
        }`}
      >
        {success ? (
          <><Check className="w-3.5 h-3.5" /> Post Generated!</>
        ) : generating ? (
          <><Loader2 className="w-3.5 h-3.5 animate-spin" /> EVA is writing…</>
        ) : (
          <><Zap className="w-3.5 h-3.5" /> GENERATE POST</>
        )}
      </button>
    </div>
  );
}

// ─── Inline Editor ────────────────────────────────────────────────────────────

function InlineEditor({
  post,
  onSave,
  onCancel,
}: {
  post: SocialPost;
  onSave: (mainPost: string, commentPost: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [mainPost, setMainPost]       = useState(post.main_post);
  const [commentPost, setCommentPost] = useState(post.comment_post ?? '');
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState('');

  const charCount  = mainPost.length;
  const charOver   = charCount > 2000;

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError('');
    try {
      await onSave(mainPost, commentPost);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
      setSaving(false);
    }
  }, [mainPost, commentPost, onSave]);

  return (
    <div className="flex flex-col gap-3 pt-3 border-t border-gray-200">
      {/* Main post textarea */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">Main Post</label>
          <span className={`font-mono text-[10px] tabular-nums font-semibold ${charOver ? 'text-red-400' : charCount > 1800 ? 'text-amber-400' : 'text-gray-500'}`}>
            {charCount} / 2000
          </span>
        </div>
        <textarea
          className={`w-full bg-white border rounded px-3 py-2.5 font-sans text-sm text-gray-800 resize-none focus:outline-none transition-colors placeholder:text-gray-500 ${
            charOver ? 'border-red-500/60 focus:border-red-500' : 'border-gray-200 focus:border-cyan-500/60'
          }`}
          rows={8}
          value={mainPost}
          onChange={e => setMainPost(e.target.value)}
          autoFocus
        />
      </div>

      {/* Comment post textarea */}
      <div>
        <label className="font-mono text-[10px] text-gray-500 uppercase tracking-widest block mb-1.5">
          First Comment — YouTube links go here
        </label>
        <textarea
          className="w-full bg-white border border-gray-200 rounded px-3 py-2.5 font-sans text-sm text-gray-800 resize-none focus:outline-none focus:border-cyan-500/60 transition-colors placeholder:text-gray-500"
          rows={3}
          value={commentPost}
          onChange={e => setCommentPost(e.target.value)}
          placeholder="YouTube link or first comment text…"
        />
      </div>

      {/* Error */}
      {error && <p className="font-mono text-xs text-red-400">⚠ {error}</p>}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={saving || charOver}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-xs font-bold hover:bg-cyan-500/25 hover:border-cyan-500/70 active:scale-95 disabled:opacity-50 transition-all"
        >
          {saving ? <><RefreshCw className="w-3 h-3 animate-spin" /> Saving…</> : <><Check className="w-3 h-3" /> Save</>}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 bg-gray-100 border border-gray-200 text-gray-500 rounded font-mono text-xs hover:bg-gray-200 hover:text-gray-800 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Post Card ────────────────────────────────────────────────────────────────

function PostCard({
  post,
  onApprove,
  onEnrichYoutube,
  onPostNow,
  onDelete,
  onUpdate,
}: {
  post: SocialPost;
  onApprove: (id: string) => Promise<void>;
  onEnrichYoutube: (id: string) => Promise<void>;
  onPostNow: (post: SocialPost) => void;
  onDelete: (id: string) => Promise<void>;
  onUpdate: (id: string, mainPost: string, commentPost: string) => Promise<void>;
}) {
  const [editing, setEditing]           = useState(false);
  const [expanded, setExpanded]         = useState(false);
  const [approvingState, setApproving]  = useState(false);
  const [enriching, setEnriching]       = useState(false);
  const [deleting, setDeleting]         = useState(false);

  const charCount   = post.char_count ?? post.main_post.length;
  const preview     = post.main_post.slice(0, 120);
  const isTruncated = post.main_post.length > 120;

  const handleApprove = useCallback(async () => {
    setApproving(true);
    try { await onApprove(post.id); } finally { setApproving(false); }
  }, [post.id, onApprove]);

  const handleEnrich = useCallback(async () => {
    setEnriching(true);
    try { await onEnrichYoutube(post.id); } finally { setEnriching(false); }
  }, [post.id, onEnrichYoutube]);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    try { await onDelete(post.id); } catch { setDeleting(false); }
  }, [post.id, onDelete]);

  const handleSaveEdit = useCallback(
    async (mainPost: string, commentPost: string) => {
      await onUpdate(post.id, mainPost, commentPost);
      setEditing(false);
    },
    [post.id, onUpdate]
  );

  return (
    <div className="bg-gray-100/60 border border-gray-200/60 hover:border-gray-300/80 rounded-lg transition-colors">
      <div className="px-4 py-3 flex flex-col gap-2.5">
        {/* Top row: badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <VoiceBadge voice={post.voice} />
          <PillarBadge pillar={post.pillar} />
          <CharCountBadge count={charCount} />
          <StatusBadge status={post.status} />
          {post.linkedin_url && (
            <a
              href={post.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 font-mono text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors ml-auto"
            >
              <ExternalLink className="w-3 h-3" />
              View
            </a>
          )}
        </div>

        {/* Post preview / full text */}
        {!editing && (
          <div className="font-sans text-sm text-gray-500 leading-relaxed">
            {expanded ? post.main_post : preview}
            {isTruncated && !expanded && <span className="text-gray-500">…</span>}
            {isTruncated && (
              <button
                onClick={() => setExpanded(v => !v)}
                className="ml-2 inline-flex items-center gap-0.5 font-mono text-[11px] text-cyan-500/70 hover:text-cyan-400 transition-colors"
              >
                {expanded
                  ? <><ChevronUp className="w-3 h-3" /> Collapse</>
                  : <><ChevronDown className="w-3 h-3" /> Expand</>}
              </button>
            )}
          </div>
        )}

        {/* Inline editor */}
        {editing && (
          <InlineEditor
            post={post}
            onSave={handleSaveEdit}
            onCancel={() => setEditing(false)}
          />
        )}

        {/* Action row */}
        {!editing && (
          <div className="flex items-center gap-1.5 flex-wrap pt-1 border-t border-gray-200">
            {/* Edit */}
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded font-mono text-[11px] font-bold hover:bg-amber-500/20 hover:border-amber-500/60 active:scale-95 transition-all"
            >
              <Edit2 className="w-3 h-3" /> Edit
            </button>

            {/* Approve — only for draft */}
            {post.status === 'draft' && (
              <button
                onClick={handleApprove}
                disabled={approvingState}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-green-500/10 border border-green-500/30 text-green-400 rounded font-mono text-[11px] font-bold hover:bg-green-500/20 hover:border-green-500/60 active:scale-95 disabled:opacity-50 transition-all"
              >
                {approvingState ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                Approve
              </button>
            )}

            {/* Enrich YouTube */}
            <button
              onClick={handleEnrich}
              disabled={enriching}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 rounded font-mono text-[11px] font-bold hover:bg-red-500/20 hover:border-red-500/60 active:scale-95 disabled:opacity-50 transition-all"
              title="Enrich with latest YouTube video link"
            >
              {enriching ? <Loader2 className="w-3 h-3 animate-spin" /> : <Youtube className="w-3 h-3" />}
              Enrich YouTube
            </button>

            {/* Post Now — only for approved */}
            {(post.status === 'approved' || post.status === 'failed') && (
              <button
                onClick={() => onPostNow(post)}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 rounded font-mono text-[11px] font-bold hover:bg-cyan-500/25 hover:border-cyan-500/70 active:scale-95 transition-all"
              >
                <Send className="w-3 h-3" /> Post Now
              </button>
            )}

            {/* Delete */}
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-1 px-2 py-1.5 text-gray-500 hover:text-red-400 rounded font-mono text-[11px] disabled:opacity-50 transition-colors ml-auto"
              title="Delete post"
            >
              {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Empty / Loading / Offline states ────────────────────────────────────────

function EmptyState({ isOnline, onRefresh }: { isOnline: boolean; onRefresh: () => void }) {
  if (!isOnline) {
    return (
      <div className="mx-2 my-3 flex flex-col items-center justify-center py-10 gap-3 bg-red-500/5 border border-red-500/15 rounded-lg">
        <WifiOff className="w-7 h-7 text-red-400/60" />
        <div className="text-center">
          <div className="font-mono text-sm text-red-400 font-semibold">Content Engine offline</div>
          <div className="font-sans text-xs text-gray-500 mt-1">
            Start it:{' '}
            <span className="font-mono text-gray-500">cd ~/Eva/modules/content-engine && python main.py</span>
          </div>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 border border-gray-200 rounded font-mono text-xs text-gray-500 hover:text-gray-800 hover:border-gray-300 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Retry Connection
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-2">
      <Linkedin className="w-8 h-8 text-gray-400" />
      <div className="font-mono text-sm text-gray-500">No posts in this queue</div>
      <div className="font-mono text-[10px] text-gray-500">Use Generate Post to create new LinkedIn content</div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-2 py-2">
      {[1, 2, 3].map(i => (
        <div key={i} className="h-20 bg-gray-100/40 rounded-lg border border-gray-200/60 animate-pulse" />
      ))}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function SocialQueue() {
  const {
    posts,
    isOnline,
    isLoading,
    linkedInConnected,
    generatePost,
    approvePost,
    postToLinkedIn,
    enrichYoutube,
    deletePost,
    updatePost,
    refresh,
  } = useSocialQueue();

  const [activeTab, setActiveTab]           = useState<'all' | PostStatus>('all');
  const [showGenerate, setShowGenerate]     = useState(false);
  const [confirmPost, setConfirmPost]       = useState<SocialPost | null>(null);
  const [spinning, setSpinning]             = useState(false);

  const handleRefresh = useCallback(() => {
    setSpinning(true);
    refresh();
    setTimeout(() => setSpinning(false), 1200);
  }, [refresh]);

  const handleGenerate = useCallback(
    async (voice: PostVoice, pillar: PostPillar, topicHint?: string) => {
      await generatePost(voice, pillar, topicHint);
    },
    [generatePost]
  );

  const handlePostNow = useCallback(
    async (): Promise<PostToLinkedInResult> => {
      if (!confirmPost) return { success: false, error: 'No post selected' };
      return await postToLinkedIn(confirmPost.id);
    },
    [confirmPost, postToLinkedIn]
  );

  // Filter posts by tab
  const filteredPosts = activeTab === 'all'
    ? posts
    : posts.filter(p => p.status === activeTab);

  // Tab counts
  const tabCount = (tab: 'all' | PostStatus) =>
    tab === 'all' ? posts.length : posts.filter(p => p.status === tab).length;

  return (
    <>
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex flex-col gap-3">

        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Linkedin className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-xs font-bold text-gray-500 tracking-widest uppercase">
              Social Queue
            </span>
            <span className="font-mono text-[10px] text-gray-500">—</span>
            <span className="font-mono text-[10px] font-semibold text-gray-500 tracking-wider uppercase">LinkedIn</span>
          </div>

          <div className="flex items-center gap-2">
            {/* LinkedIn connection pill */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded border font-mono text-[10px] font-semibold ${
              linkedInConnected
                ? 'bg-green-500/10 border-green-500/30 text-green-400'
                : 'bg-gray-200/30 border-gray-200/40 text-gray-500'
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${linkedInConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
              LinkedIn: {linkedInConnected ? 'Connected' : 'Disconnected'}
            </div>

            {/* Generate Post button */}
            <button
              onClick={() => setShowGenerate(v => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1 border rounded font-mono text-xs font-bold active:scale-95 transition-all duration-150 ${
                showGenerate
                  ? 'bg-cyan-500/20 border-cyan-500/60 text-cyan-300'
                  : 'bg-cyan-500/10 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/20 hover:border-cyan-500/70'
              }`}
            >
              <Zap className="w-3 h-3" />
              Generate Post
            </button>

            {/* Refresh */}
            <button
              onClick={handleRefresh}
              className="p-1.5 text-gray-500 hover:text-gray-500 transition-colors rounded hover:bg-gray-100"
              title="Refresh social queue"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* ── Generate Panel ──────────────────────────────────────────────────── */}
        {showGenerate && (
          <GeneratePanel
            onGenerate={handleGenerate}
            onClose={() => setShowGenerate(false)}
          />
        )}

        {/* ── Tab bar ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-1 flex-wrap border-b border-gray-200 pb-2">
          {TABS.map(tab => {
            const count    = tabCount(tab.value);
            const isActive = activeTab === tab.value;
            return (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`px-2.5 py-1 rounded font-mono text-[11px] font-semibold transition-colors ${
                  isActive
                    ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
                    : 'text-gray-500 hover:text-gray-500 border border-transparent hover:border-gray-200'
                }`}
              >
                {tab.label}
                {count > 0 && (
                  <span className={`ml-1 px-1 rounded text-[9px] ${isActive ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-100 text-gray-500'}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Post list ──────────────────────────────────────────────────────── */}
        {isLoading && filteredPosts.length === 0 ? (
          <LoadingSkeleton />
        ) : !isOnline && !isLoading ? (
          <EmptyState isOnline={false} onRefresh={handleRefresh} />
        ) : filteredPosts.length === 0 ? (
          <EmptyState isOnline={true} onRefresh={handleRefresh} />
        ) : (
          <div className="flex flex-col gap-2">
            {filteredPosts.map(post => (
              <PostCard
                key={post.id}
                post={post}
                onApprove={approvePost}
                onEnrichYoutube={enrichYoutube}
                onPostNow={setConfirmPost}
                onDelete={deletePost}
                onUpdate={updatePost}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Post confirmation modal ─────────────────────────────────────────── */}
      {confirmPost && (
        <PostConfirmModal
          post={confirmPost}
          onConfirm={handlePostNow}
          onCancel={() => setConfirmPost(null)}
        />
      )}
    </>
  );
}
