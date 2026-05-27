import { useState, useEffect, useCallback, ComponentType } from 'react';
import {
  CheckCircle,
  XCircle,
  Loader2,
  ExternalLink,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  X,
  Send,
  Clock,
  MessageSquare,
  Mail,
  CornerDownRight,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface PostResult {
  platform: string;
  status: 'posted' | 'error' | 'not_connected' | 'pending_approval';
  url?: string;
  adapted_content?: string;
  error?: string;
}

interface Signal {
  id: string;
  platform: string;
  content: string;
  type: 'comment' | 'dm' | 'reply';
  url?: string;
  engagement: { likes: number; comments: number };
  timestamp: string;
}

interface PlatformStatus {
  linkedin?: 'connected' | 'disconnected';
  reddit?: 'connected' | 'disconnected';
  twitter?: 'connected' | 'disconnected';
  facebook?: 'connected' | 'disconnected' | 'pending_approval';
}

interface CredentialField {
  key: string;
  label: string;
  placeholder?: string;
  type?: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const API = 'http://localhost:8770';

const PLATFORMS = [
  { id: 'linkedin', name: 'LinkedIn',   emoji: '💼', port: 8770 },
  { id: 'reddit',   name: 'Reddit',     emoji: '🤖', port: 8770 },
  { id: 'twitter',  name: 'Twitter/X',  emoji: '🐦', port: 8770 },
  { id: 'facebook', name: 'Facebook',   emoji: '👥', port: 8770 },
];

const CREDENTIAL_FIELDS: Record<string, CredentialField[]> = {
  linkedin: [
    { key: 'access_token', label: 'Access Token', placeholder: 'Paste your LinkedIn access token', type: 'password' },
  ],
  facebook: [
    { key: 'access_token', label: 'Page Access Token', placeholder: 'Paste your Facebook page access token', type: 'password' },
    { key: 'page_id',      label: 'Page ID',            placeholder: 'Your Facebook Page ID' },
  ],
  reddit: [
    { key: 'client_id',     label: 'Client ID',        placeholder: 'your_reddit_client_id' },
    { key: 'client_secret', label: 'Client Secret',    placeholder: 'your_reddit_secret',    type: 'password' },
    { key: 'username',      label: 'Reddit Username',  placeholder: 'u/yourusername' },
    { key: 'password',      label: 'Reddit Password',  placeholder: '••••••••',               type: 'password' },
    { key: 'subreddit',     label: 'Target Subreddit', placeholder: 'EcommerceAcquisitions' },
  ],
  twitter: [
    { key: 'api_key',       label: 'API Key',          placeholder: 'your_api_key' },
    { key: 'api_secret',    label: 'API Secret',       placeholder: 'your_api_secret',        type: 'password' },
    { key: 'access_token',  label: 'Access Token',     placeholder: 'your_access_token' },
    { key: 'access_secret', label: 'Access Secret',    placeholder: 'your_access_secret',     type: 'password' },
  ],
};

const OAUTH_INSTRUCTIONS: Record<string, { steps: string[]; link: string; linkLabel: string }> = {
  linkedin: {
    steps: [
      '1. Go to LinkedIn Developer Portal → create an app',
      '2. Add products: Share on LinkedIn + Sign In with LinkedIn',
      '3. Under Auth tab → OAuth 2.0 tools → Get access token',
      '4. Scopes needed: w_member_social, r_liteprofile',
      '5. Copy the token and paste below (valid 60 days)',
    ],
    link: 'https://www.linkedin.com/developers/apps',
    linkLabel: 'Open LinkedIn Developer Portal →',
  },
  facebook: {
    steps: [
      '1. Go to Meta for Developers → your app → Graph API Explorer',
      '2. Select your Page from the dropdown',
      '3. Generate a Page Access Token with pages_manage_posts scope',
      '4. Copy your Page ID from the Page settings',
      '5. Paste both values below',
    ],
    link: 'https://developers.facebook.com/tools/explorer/',
    linkLabel: 'Open Graph API Explorer →',
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins  < 1)  return 'just now';
  if (mins  < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

function platformEmoji(id: string): string {
  return PLATFORMS.find(p => p.id === id)?.emoji ?? '📡';
}

function platformName(id: string): string {
  return PLATFORMS.find(p => p.id === id)?.name ?? id;
}

// ─── Credential Modal ─────────────────────────────────────────────────────────

function CredentialModal({
  platform,
  onClose,
  onConnect,
  serviceOnline,
}: {
  platform: string;
  onClose: () => void;
  onConnect: (platform: string, creds: Record<string, string>) => Promise<void>;
  serviceOnline: boolean;
}) {
  const fields = CREDENTIAL_FIELDS[platform] ?? [];
  const instructions = OAUTH_INSTRUCTIONS[platform];
  const [creds, setCreds]     = useState<Record<string, string>>(
    Object.fromEntries(fields.map(f => [f.key, '']))
  );
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState('');
  const [success, setSuccess] = useState(false);

  const handleSave = useCallback(async () => {
    if (!serviceOnline) {
      setError('Channels service is offline — start EVA Mac services first.');
      return;
    }
    const empty = fields.find(f => !creds[f.key]?.trim());
    if (empty) { setError(`${empty.label} is required`); return; }
    setSaving(true);
    setError('');
    try {
      await onConnect(platform, creds);
      setSuccess(true);
      setTimeout(onClose, 1200);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setSaving(false);
    }
  }, [platform, creds, fields, onConnect, onClose, serviceOnline]);

  const pName = platformName(platform);
  const emoji = platformEmoji(platform);

  return (
    <div
      className="fixed inset-0 z-[200] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-lg bg-[#111] border border-[#1a1a1a] rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1a1a1a]">
          <div className="flex items-center gap-2.5">
            <span style={{ fontSize: 18 }}>{emoji}</span>
            <span className="font-mono text-sm font-bold text-[#00ff88] tracking-wider uppercase">
              Connect {pName}
            </span>
          </div>
          <button onClick={onClose} className="p-1 text-gray-500 hover:text-gray-300 rounded transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Service offline warning */}
        {!serviceOnline && (
          <div className="mx-5 mt-4 px-3 py-2.5 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="font-mono text-xs font-bold text-red-400 mb-1">⚠ Channels Service Offline</div>
            <div className="font-mono text-[10px] text-red-300 leading-relaxed">
              You can save credentials here — they'll be stored for when the service starts.<br />
              To activate: <code className="text-red-200">bash ~/Eva/modules/autostart/eva-install-services.sh</code>
            </div>
          </div>
        )}

        {/* OAuth Instructions */}
        {instructions && (
          <div className="mx-5 mt-4 px-3 py-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
            <div className="font-mono text-[10px] font-bold text-[#00ff88] uppercase tracking-widest mb-2">How to get your token</div>
            <div className="flex flex-col gap-1 mb-3">
              {instructions.steps.map((step, i) => (
                <div key={i} className="font-mono text-[11px] text-gray-400 leading-relaxed">{step}</div>
              ))}
            </div>
            <a
              href={instructions.link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[#00ff88] hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              {instructions.linkLabel}
            </a>
          </div>
        )}

        {/* Fields */}
        <div className="px-5 py-4 flex flex-col gap-4">
          {fields.map(field => (
            <div key={field.key}>
              <label className="font-mono text-[10px] text-gray-500 uppercase tracking-widest block mb-1.5">
                {field.label}
              </label>
              <input
                type={field.type ?? 'text'}
                value={creds[field.key] ?? ''}
                onChange={e => setCreds(prev => ({ ...prev, [field.key]: e.target.value }))}
                placeholder={field.placeholder}
                className="w-full bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-2 font-mono text-sm text-gray-300 placeholder:text-gray-600 focus:outline-none focus:border-[#00ff88]/40 transition-colors"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
          ))}

          {error && (
            <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded font-mono text-xs text-red-400">
              ⚠ {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-[#1a1a1a] flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 font-mono text-xs text-gray-500 hover:text-gray-300 border border-[#1a1a1a] rounded transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || success}
            className={`flex items-center gap-1.5 px-4 py-1.5 border rounded font-mono text-xs font-bold active:scale-[0.98] transition-all disabled:cursor-not-allowed cursor-pointer ${
              success
                ? 'bg-[#00ff88]/15 border-[#00ff88]/40 text-[#00ff88]'
                : 'bg-[#00ff88]/10 border-[#00ff88]/30 text-[#00ff88] hover:bg-[#00ff88]/20 hover:border-[#00ff88]/60 disabled:opacity-60'
            }`}
          >
            {success ? (
              <><CheckCircle className="w-3 h-3" /> Saved!</>
            ) : saving ? (
              <><Loader2 className="w-3 h-3 animate-spin" /> Saving…</>
            ) : (
              'Save Credentials'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Column 1 — Connected Channels ────────────────────────────────────────────

function ChannelsSidebar({
  platformStatus,
  onConnect,
}: {
  platformStatus: PlatformStatus;
  onConnect: (platform: string) => void;
}) {
  const getStatus = (id: string) =>
    (platformStatus as Record<string, string | undefined>)[id];

  return (
    <div className="w-60 shrink-0 flex flex-col gap-2">
      {/* Header */}
      <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-1">
        Channels
      </div>

      {/* Platform cards */}
      {PLATFORMS.map(platform => {
        const status = getStatus(platform.id);
        const isConnected      = status === 'connected';
        const isPending        = status === 'pending_approval';
        const isDisconnected   = !status || status === 'disconnected';

        return (
          <div
            key={platform.id}
            className="bg-[#111] border border-[#1a1a1a] rounded-lg px-3 py-2.5 flex items-center gap-2.5"
          >
            {/* Emoji */}
            <span className="text-base leading-none shrink-0">{platform.emoji}</span>

            {/* Name + status text */}
            <div className="flex-1 min-w-0">
              <div className="font-mono text-xs font-semibold text-gray-800 truncate">
                {platform.name}
              </div>
              <div className="font-mono text-[10px] text-gray-500 mt-0.5">
                {isConnected && (
                  <span className="text-[#00ff88]">Connected</span>
                )}
                {isPending && (
                  <span className="text-yellow-400">Pending approval</span>
                )}
                {isDisconnected && (
                  <span className="text-gray-500">Disconnected</span>
                )}
              </div>
            </div>

            {/* Status dot / badge / button */}
            <div className="shrink-0 flex items-center gap-1.5">
              {isConnected && (
                <div
                  className="w-2 h-2 rounded-full bg-[#00ff88] animate-pulse"
                  title="Connected"
                />
              )}
              {isPending && (
                <span className="px-1.5 py-0.5 bg-yellow-500/15 border border-yellow-500/30 text-yellow-400 font-mono text-[9px] font-bold rounded tracking-wider">
                  PENDING
                </span>
              )}
              {isDisconnected && (
                <button
                  onClick={() => onConnect(platform.id)}
                  className="px-2 py-1 bg-[#00ff88]/10 border border-[#00ff88]/30 text-[#00ff88] rounded font-mono text-[10px] font-bold hover:bg-[#00ff88]/20 hover:border-[#00ff88]/60 active:scale-95 transition-all cursor-pointer"
                >
                  Connect
                </button>
              )}
            </div>
          </div>
        );
      })}

      {/* Footer note */}
      <div className="mt-2 px-1 font-mono text-[9px] text-gray-400 leading-relaxed">
        Each channel is an independent microservice
      </div>
    </div>
  );
}

// ─── Column 2 — Compose ───────────────────────────────────────────────────────

function AdaptedPreviewAccordion({
  adaptedPreviews,
  selectedPlatforms,
}: {
  adaptedPreviews: Record<string, string>;
  selectedPlatforms: string[];
}) {
  const [openPlatform, setOpenPlatform] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-1.5">
      {selectedPlatforms.map(pid => {
        const preview = adaptedPreviews[pid];
        const isOpen  = openPlatform === pid;
        const pname   = platformName(pid);

        return (
          <div
            key={pid}
            className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden"
          >
            <button
              onClick={() => setOpenPlatform(isOpen ? null : pid)}
              className="w-full flex items-center justify-between px-3 py-2 text-left cursor-pointer hover:bg-[#111] transition-colors"
            >
              <span className="font-mono text-[11px] text-gray-500 font-semibold">
                {platformEmoji(pid)} {pname} version
              </span>
              {isOpen
                ? <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
                : <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
              }
            </button>
            {isOpen && (
              <div className="px-3 pb-3 font-sans text-sm text-gray-500 leading-relaxed whitespace-pre-wrap border-t border-[#1a1a1a]">
                {preview
                  ? <p className="mt-2">{preview}</p>
                  : <p className="mt-2 font-mono text-xs text-gray-500 italic">Fetching adaptation…</p>
                }
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ResultCard({ result }: { result: PostResult }) {
  const pname = platformName(result.platform);
  const emoji = platformEmoji(result.platform);

  return (
    <div className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border ${
      result.status === 'posted'
        ? 'bg-[#00ff88]/5 border-[#00ff88]/20'
        : result.status === 'pending_approval'
        ? 'bg-yellow-500/5 border-yellow-500/20'
        : 'bg-red-500/5 border-red-500/20'
    }`}>
      {/* Icon */}
      <div className="shrink-0 mt-0.5">
        {result.status === 'posted' && (
          <CheckCircle className="w-4 h-4 text-[#00ff88]" />
        )}
        {result.status === 'pending_approval' && (
          <Clock className="w-4 h-4 text-yellow-400" />
        )}
        {(result.status === 'error' || result.status === 'not_connected') && (
          <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs font-bold text-gray-500">
          {emoji} {pname}
        </div>

        {result.status === 'posted' && (
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-[10px] text-[#00ff88]">Posted successfully</span>
            {result.url && (
              <a
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 font-mono text-[10px] text-gray-500 hover:text-[#00ff88] underline underline-offset-2 transition-colors"
              >
                <ExternalLink className="w-2.5 h-2.5" />
                View
              </a>
            )}
          </div>
        )}

        {result.status === 'pending_approval' && (
          <span className="font-mono text-[10px] text-yellow-400">Pending approval</span>
        )}

        {result.status === 'error' && (
          <span className="font-mono text-[10px] text-red-400">
            {result.error ?? 'Post failed'}
          </span>
        )}

        {result.status === 'not_connected' && (
          <span className="font-mono text-[10px] text-red-400">Not connected</span>
        )}
      </div>
    </div>
  );
}

function ComposeColumn({
  content,
  setContent,
  selectedPlatforms,
  setSelectedPlatforms,
  isPosting,
  postResults,
  adaptedPreviews,
  showPreviews,
  subreddit,
  setSubreddit,
  onPost,
  onPreview,
}: {
  content: string;
  setContent: (v: string) => void;
  selectedPlatforms: string[];
  setSelectedPlatforms: (v: string[]) => void;
  isPosting: boolean;
  postResults: PostResult[];
  adaptedPreviews: Record<string, string>;
  showPreviews: boolean;
  subreddit: string;
  setSubreddit: (v: string) => void;
  onPost: () => void;
  onPreview: () => void;
}) {
  const togglePlatform = (id: string) => {
    setSelectedPlatforms(
      selectedPlatforms.includes(id)
        ? selectedPlatforms.filter(p => p !== id)
        : [...selectedPlatforms, id]
    );
  };

  const charCount   = content.length;
  const charOver    = charCount > 2000;
  const charNear    = charCount > 1700;
  const hasReddit   = selectedPlatforms.includes('reddit');
  const hasAdapted  = Object.keys(adaptedPreviews).length > 0;

  return (
    <div className="flex-1 flex flex-col gap-3 min-w-0">
      {/* Header */}
      <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest">
        Compose Once
      </div>

      {/* Textarea */}
      <div className="relative">
        <textarea
          value={content}
          onChange={e => setContent(e.target.value)}
          placeholder="Write your content once — EVA adapts it for each platform…"
          className={`w-full h-40 bg-[#0a0a0a] border rounded-lg px-3 py-2.5 font-sans text-sm text-gray-800 placeholder:text-gray-400 resize-none focus:outline-none transition-colors leading-relaxed ${
            charOver
              ? 'border-red-500/60 focus:border-red-500/80'
              : 'border-[#1a1a1a] focus:border-[#00ff88]/40'
          }`}
          spellCheck={false}
        />
        {/* Character counter */}
        <span
          className={`absolute bottom-2.5 right-3 font-mono text-[10px] tabular-nums ${
            charOver ? 'text-red-400' : charNear ? 'text-yellow-400' : 'text-gray-400'
          }`}
        >
          {charCount.toLocaleString()}
        </span>
      </div>

      {/* Platform toggle chips */}
      <div className="flex items-center flex-wrap gap-1.5">
        {PLATFORMS.map(platform => {
          const active = selectedPlatforms.includes(platform.id);
          return (
            <button
              key={platform.id}
              onClick={() => togglePlatform(platform.id)}
              className={`flex items-center gap-1.5 px-2.5 py-1 border rounded-full font-mono text-[11px] font-semibold active:scale-95 transition-all cursor-pointer ${
                active
                  ? 'bg-[#00ff88]/15 border-[#00ff88]/40 text-[#00ff88]'
                  : 'bg-[#111] border-[#1a1a1a] text-gray-500 hover:border-gray-300 hover:text-gray-500'
              }`}
            >
              <span>{platform.emoji}</span>
              <span>{platform.name}</span>
            </button>
          );
        })}
      </div>

      {/* Reddit subreddit input */}
      {hasReddit && (
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-gray-500 shrink-0">r/</span>
          <input
            type="text"
            value={subreddit}
            onChange={e => setSubreddit(e.target.value)}
            placeholder="EcommerceAcquisitions"
            className="flex-1 bg-[#0a0a0a] border border-[#1a1a1a] rounded px-3 py-1.5 font-mono text-xs text-gray-500 placeholder:text-gray-400 focus:outline-none focus:border-[#00ff88]/40 transition-colors"
          />
        </div>
      )}

      {/* Preview button */}
      <div className="flex items-center gap-2">
        <button
          onClick={onPreview}
          disabled={!content.trim() || selectedPlatforms.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#111] border border-[#1a1a1a] text-gray-500 rounded font-mono text-xs font-semibold hover:border-gray-300 hover:text-gray-800 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
        >
          {showPreviews
            ? <><ChevronUp className="w-3 h-3" /> Hide Previews</>
            : <><ChevronDown className="w-3 h-3" /> Preview Adaptations</>
          }
        </button>
      </div>

      {/* Adapted previews accordion */}
      {showPreviews && hasAdapted && selectedPlatforms.length > 0 && (
        <AdaptedPreviewAccordion
          adaptedPreviews={adaptedPreviews}
          selectedPlatforms={selectedPlatforms}
        />
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 pt-1">
        {/* Post Now */}
        <button
          onClick={onPost}
          disabled={isPosting || !content.trim() || selectedPlatforms.length === 0 || charOver}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-[#00ff88]/15 border border-[#00ff88]/40 text-[#00ff88] rounded-lg font-mono text-xs font-bold hover:bg-[#00ff88]/25 hover:border-[#00ff88]/70 active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
        >
          {isPosting
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Posting…</>
            : <><Send className="w-3.5 h-3.5" /> Post Now</>
          }
        </button>

        {/* Schedule (placeholder) */}
        <button
          disabled={!content.trim() || selectedPlatforms.length === 0}
          className="flex items-center gap-1.5 px-4 py-2.5 bg-transparent border border-[#1a1a1a] text-gray-500 rounded-lg font-mono text-xs font-bold hover:border-gray-300 hover:text-gray-500 active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
        >
          <Clock className="w-3.5 h-3.5" />
          Schedule
        </button>
      </div>

      {/* Post results */}
      {postResults.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1">
          <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-0.5">
            Results
          </div>
          {postResults.map((result, i) => (
            <ResultCard key={`${result.platform}-${i}`} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Column 3 — Signal Feed ───────────────────────────────────────────────────

const SIGNAL_TYPE_CONFIG: Record<Signal['type'], { label: string; bg: string; text: string; border: string; icon: ComponentType<{ className?: string }> }> = {
  dm:      { label: 'DM',      bg: 'bg-purple-500/15', text: 'text-purple-400', border: 'border-purple-500/30', icon: Mail },
  comment: { label: 'Comment', bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30',   icon: MessageSquare },
  reply:   { label: 'Reply',   bg: 'bg-gray-500/15',   text: 'text-gray-500',   border: 'border-gray-300/30',   icon: CornerDownRight },
};

function SignalCard({ signal }: { signal: Signal }) {
  const cfg   = SIGNAL_TYPE_CONFIG[signal.type];
  const Icon  = cfg.icon;
  const emoji = platformEmoji(signal.platform);
  const pname = platformName(signal.platform);

  return (
    <div className="bg-[#111] border border-[#1a1a1a] rounded-lg px-3 py-2.5 flex flex-col gap-2 hover:border-gray-200 transition-colors">
      {/* Top: platform + time */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-sm leading-none">{emoji}</span>
          <span className="font-mono text-[11px] text-gray-500 font-semibold truncate">{pname}</span>
        </div>
        <span className="font-mono text-[10px] text-gray-400 shrink-0">
          {timeAgo(signal.timestamp)}
        </span>
      </div>

      {/* Quoted content */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded px-2.5 py-2 font-sans text-xs text-gray-500 leading-relaxed line-clamp-3">
        {signal.content}
      </div>

      {/* Bottom: engagement + type pill + link */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-gray-500">
            ♥ {signal.engagement.likes}
          </span>
          <span className="font-mono text-[10px] text-gray-500">
            💬 {signal.engagement.comments}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {signal.url && (
            <a
              href={signal.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 hover:text-[#00ff88] transition-colors"
              title="Open"
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono text-[9px] font-bold tracking-wider ${cfg.bg} ${cfg.text} ${cfg.border}`}>
            <Icon className="w-2.5 h-2.5" />
            {cfg.label.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
}

function SignalFeed({ signals }: { signals: Signal[] }) {
  return (
    <div className="w-72 shrink-0 flex flex-col gap-2 min-h-0">
      {/* Header */}
      <div className="font-mono text-[10px] text-gray-500 uppercase tracking-widest mb-1 shrink-0">
        Engagement Signal
      </div>

      {/* Signal cards */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
        {signals.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2 bg-[#111] border border-[#1a1a1a] rounded-lg">
            <span className="text-2xl">📡</span>
            <div className="font-mono text-xs text-gray-500 text-center px-4 leading-relaxed">
              No signals yet — posts will surface responses here
            </div>
          </div>
        ) : (
          signals.map(signal => (
            <SignalCard key={signal.id} signal={signal} />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="shrink-0 font-mono text-[9px] text-gray-400 pt-2 border-t border-[#1a1a1a]">
        Updates every 30s · Powered by Angel 6
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function ChannelsHub() {
  const [content, setContent]                     = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(['linkedin']);
  const [isPosting, setIsPosting]                 = useState(false);
  const [postResults, setPostResults]             = useState<PostResult[]>([]);
  const [signals, setSignals]                     = useState<Signal[]>([]);
  const [platformStatus, setPlatformStatus]       = useState<PlatformStatus>({});
  const [adaptedPreviews, setAdaptedPreviews]     = useState<Record<string, string>>({});
  const [showPreviews, setShowPreviews]           = useState(false);
  const [subreddit, setSubreddit]                 = useState('EcommerceAcquisitions');
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [channelServiceOnline, setChannelServiceOnline] = useState(false);

  // ── Fetch status + signals on mount, poll signals every 30s ─────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/channels/status`, { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        const data = await r.json();
        setPlatformStatus(data);
        setChannelServiceOnline(true);
      } else {
        setChannelServiceOnline(false);
      }
    } catch {
      setChannelServiceOnline(false);
    }
  }, []);

  const fetchSignals = useCallback(async () => {
    try {
      const r = await fetch(`${API}/channels/signal`, { signal: AbortSignal.timeout(5000) });
      if (r.ok) {
        const data = await r.json();
        setSignals(Array.isArray(data) ? data : data.signals ?? []);
      }
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchSignals();
    const id = setInterval(fetchSignals, 30000);
    return () => clearInterval(id);
  }, [fetchStatus, fetchSignals]);

  // ── Post ─────────────────────────────────────────────────────────────────────

  const handlePost = useCallback(async () => {
    if (!content.trim() || selectedPlatforms.length === 0) return;
    setIsPosting(true);
    setPostResults([]);
    try {
      const r = await fetch(`${API}/channels/compose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          platforms: selectedPlatforms,
          reddit_subreddit: subreddit,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        const results: PostResult[] = Array.isArray(data)
          ? data
          : data.results ?? [];
        setPostResults(results);
        // Clear content if all posted successfully
        if (results.every(res => res.status === 'posted')) {
          setContent('');
          setAdaptedPreviews({});
          setShowPreviews(false);
        }
      } else {
        const err = await r.text().catch(() => 'Unknown error');
        setPostResults(
          selectedPlatforms.map(pid => ({
            platform: pid,
            status: 'error' as const,
            error: `HTTP ${r.status}: ${err}`,
          }))
        );
      }
    } catch (e) {
      setPostResults(
        selectedPlatforms.map(pid => ({
          platform: pid,
          status: 'error' as const,
          error: e instanceof Error ? e.message : 'Network error',
        }))
      );
    } finally {
      setIsPosting(false);
    }
  }, [content, selectedPlatforms, subreddit]);

  // ── Preview Adaptations ───────────────────────────────────────────────────────

  const handlePreview = useCallback(async () => {
    if (!content.trim() || selectedPlatforms.length === 0) return;

    // Toggle off if already showing with content
    if (showPreviews && Object.keys(adaptedPreviews).length > 0) {
      setShowPreviews(false);
      return;
    }

    setShowPreviews(true);
    setAdaptedPreviews({});

    // Fetch adaptations in parallel
    await Promise.all(
      selectedPlatforms.map(async pid => {
        try {
          const r = await fetch(`${API}/channels/adapt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, platform: pid }),
          });
          if (r.ok) {
            const data = await r.json();
            const adapted = data.adapted_content ?? data.content ?? content;
            setAdaptedPreviews(prev => ({ ...prev, [pid]: adapted }));
          } else {
            setAdaptedPreviews(prev => ({ ...prev, [pid]: content }));
          }
        } catch {
          setAdaptedPreviews(prev => ({ ...prev, [pid]: content }));
        }
      })
    );
  }, [content, selectedPlatforms, showPreviews, adaptedPreviews]);

  // ── Connect ───────────────────────────────────────────────────────────────────

  const handleOpenConnect = useCallback((platform: string) => {
    // LinkedIn has no credential modal — open OAuth or show info
    if (platform === 'linkedin' || platform === 'facebook') {
      // For now, fall through to modal (fields will be empty)
    }
    setConnectingPlatform(platform);
  }, []);

  const handleConnect = useCallback(async (platform: string, creds: Record<string, string>) => {
    const r = await fetch(`${API}/channels/connect/${platform}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(creds),
    });
    if (!r.ok) {
      const msg = await r.text().catch(() => 'Connection failed');
      throw new Error(`HTTP ${r.status}: ${msg}`);
    }
    // Refresh status after connecting
    await fetchStatus();
  }, [fetchStatus]);

  return (
    <>
      {/* 3-column layout */}
      <div className="flex gap-4 min-h-0 h-full">
        {/* Column 1 — Channels */}
        <ChannelsSidebar
          platformStatus={platformStatus}
          onConnect={handleOpenConnect}
        />

        {/* Column 2 — Compose */}
        <ComposeColumn
          content={content}
          setContent={setContent}
          selectedPlatforms={selectedPlatforms}
          setSelectedPlatforms={setSelectedPlatforms}
          isPosting={isPosting}
          postResults={postResults}
          adaptedPreviews={adaptedPreviews}
          showPreviews={showPreviews}
          subreddit={subreddit}
          setSubreddit={setSubreddit}
          onPost={handlePost}
          onPreview={handlePreview}
        />

        {/* Column 3 — Signal Feed */}
        <SignalFeed signals={signals} />
      </div>

      {/* Credential Modal */}
      {connectingPlatform && (
        <CredentialModal
          platform={connectingPlatform}
          onClose={() => setConnectingPlatform(null)}
          onConnect={handleConnect}
          serviceOnline={channelServiceOnline}
        />
      )}

      {/* Refresh button — floating top-right inside the hub header area */}
      <div className="sr-only">
        <button onClick={fetchStatus} aria-label="Refresh channel status">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
    </>
  );
}
