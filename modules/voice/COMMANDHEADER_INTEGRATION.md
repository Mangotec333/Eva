# CommandHeader.tsx — Voice Module Integration

## 1. Add to SERVICE_LABELS / PORTS / CMDS dicts

In `CommandHeader.tsx`, locate the three parallel dictionaries (or arrays) that
define the service pills. Add one entry to each:

```tsx
// SERVICE_LABELS
{ label: "Voice", port: 8774, cmd: "voice" }

// If using separate dicts:
const SERVICE_LABELS = {
  // ...existing entries...
  voice: "Voice",
};

const SERVICE_PORTS = {
  // ...existing entries...
  voice: 8774,
};

const SERVICE_CMDS = {
  // ...existing entries...
  voice: "voice",
};
```

## 2. Voice status pill — health polling

The existing health-polling pattern polls `/health` every N seconds. The Voice
pill connects to `http://localhost:8774/health`. No changes to the polling
function are needed; the new entry is picked up automatically.

## 3. Mic icon animation on wake word (WebSocket)

Add this hook once the Voice pill renders:

```tsx
// src/components/CommandHeader.tsx (or a VoiceStatusBadge sub-component)

import { useEffect, useRef, useState } from "react";

function useVoiceWS() {
  const [wakeWordActive, setWakeWordActive] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket("ws://localhost:8774/ws");

      ws.current.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.ping) return;
          setWakeWordActive(data.wake_word_detected ?? false);
        } catch {}
      };

      ws.current.onclose = () => {
        setTimeout(connect, 3000); // reconnect on drop
      };
    };

    connect();
    return () => ws.current?.close();
  }, []);

  return { wakeWordActive };
}
```

Use in the Voice pill JSX:

```tsx
const { wakeWordActive } = useVoiceWS();

<span className={`voice-pill ${wakeWordActive ? "animate-pulse text-green-400" : ""}`}>
  🎙 Voice
</span>
```

## 4. POST /speak — trigger EVA to speak from UI

```ts
// Utility function — call from any Command Center component
export async function evaTTS(text: string) {
  await fetch("http://localhost:8774/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// Example usage
<button onClick={() => evaTTS("Good morning Vineet, your pipeline has 3 new leads.")}>
  Read Aloud
</button>
```
