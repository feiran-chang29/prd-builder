import { useEffect, useMemo, useState } from "react";

type Role = "user" | "assistant";

type Message = {
  role: Role;
  content: string;
};

type ChatResponse = {
  assistant_text: string;
  questions: string[];
  prd: Record<string, any>;
};

const STORAGE_MESSAGES_KEY = "prd_builder_messages";
const STORAGE_PRD_KEY = "prd_builder_prd";

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveJson(key: string, value: any): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore
  }
}

export default function App(): JSX.Element {
  const [messages, setMessages] = useState<Message[]>(() =>
    loadJson<Message[]>(STORAGE_MESSAGES_KEY, [])
  );
  const [prd, setPrd] = useState<Record<string, any>>(() =>
    loadJson<Record<string, any>>(STORAGE_PRD_KEY, {})
  );

  const [input, setInput] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    saveJson(STORAGE_MESSAGES_KEY, messages);
  }, [messages]);

  useEffect(() => {
    saveJson(STORAGE_PRD_KEY, prd);
  }, [prd]);

  const prdView = useMemo(() => {
    const safe = prd || {};
    const problem = safe.problem || "";
    const users = Array.isArray(safe.users) ? safe.users : [];
    const goals = Array.isArray(safe.goals) ? safe.goals : [];
    const metrics = Array.isArray(safe.metrics) ? safe.metrics : [];
    const requirements = Array.isArray(safe.requirements) ? safe.requirements : [];
    const openQuestions = Array.isArray(safe.open_questions) ? safe.open_questions : [];

    return { problem, users, goals, metrics, requirements, openQuestions, raw: safe };
  }, [prd]);

  async function send(): Promise<void> {
    const text = input.trim();
    if (!text || isLoading) {
      return;
    }

    setError("");
    setIsLoading(true);

    const nextMessages: Message[] = messages.concat([{ role: "user", content: text }]);
    setMessages(nextMessages);
    setInput("");

    try {
      const res = await fetch("http://localhost:3001/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          prd: prd
        })
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`Server error (${res.status}): ${t}`);
      }

      const data = (await res.json()) as ChatResponse;

      const assistantText = (data.assistant_text || "").trim();
      const questions = Array.isArray(data.questions) ? data.questions : [];

      const combined = assistantText
        ? assistantText
        : questions.length > 0
          ? questions.map((q) => `- ${q}`).join("\n")
          : "OK.";

      setMessages((prev) => prev.concat([{ role: "assistant", content: combined }]));
      setPrd(data.prd || {});
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Request failed.");
      setMessages((prev) =>
        prev.concat([{ role: "assistant", content: "Something went wrong. Please try again." }])
      );
    } finally {
      setIsLoading(false);
    }
  }

  function reset(): void {
    setMessages([]);
    setPrd({});
    setInput("");
    setError("");
    try {
      localStorage.removeItem(STORAGE_MESSAGES_KEY);
      localStorage.removeItem(STORAGE_PRD_KEY);
    } catch {
      // ignore
    }
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid rgba(0,0,0,0.12)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }}
      >
        <div style={{ fontWeight: 600 }}>Mini PRD Builder</div>
        <button onClick={reset} disabled={isLoading}>
          Reset
        </button>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* Chat */}
        <div
          style={{
            flex: 1,
            borderRight: "1px solid rgba(0,0,0,0.12)",
            display: "flex",
            flexDirection: "column",
            minHeight: 0
          }}
        >
          <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
            {messages.length === 0 ? (
              <div style={{ opacity: 0.7 }}>
                Start by describing your product idea. I&apos;ll ask a couple questions and build a PRD.
              </div>
            ) : null}

            {messages.map((m, idx) => {
              const isUser = m.role === "user";
              return (
                <div
                  key={idx}
                  style={{
                    display: "flex",
                    justifyContent: isUser ? "flex-end" : "flex-start",
                    marginBottom: 10
                  }}
                >
                  <div
                    style={{
                      maxWidth: "80%",
                      padding: "10px 12px",
                      borderRadius: 10,
                      whiteSpace: "pre-wrap",
                      background: isUser ? "rgba(0,0,0,0.08)" : "rgba(0,0,0,0.04)"
                    }}
                  >
                    {m.content}
                  </div>
                </div>
              );
            })}

            {isLoading ? <div style={{ opacity: 0.7 }}>Thinking…</div> : null}
            {error ? <div style={{ color: "crimson", marginTop: 8 }}>{error}</div> : null}
          </div>

          <div style={{ padding: 16, borderTop: "1px solid rgba(0,0,0,0.12)" }}>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    void send();
                  }
                }}
                disabled={isLoading}
                placeholder="Describe your product idea…"
                style={{ flex: 1, padding: "10px 12px" }}
              />
              <button onClick={() => void send()} disabled={isLoading || !input.trim()}>
                Send
              </button>
            </div>
          </div>
        </div>

        {/* PRD Panel */}
        <div style={{ width: 420, padding: 16, overflow: "auto" }}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>PRD</div>

          <Section title="Problem" value={prdView.problem} />
          <ListSection title="Users" items={prdView.users} />
          <ListSection title="Goals" items={prdView.goals} />
          <ListSection title="Metrics" items={prdView.metrics} />
          <ListSection title="Requirements" items={prdView.requirements} />
          <ListSection title="Open Questions" items={prdView.openQuestions} />

          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer" }}>Raw PRD JSON</summary>
            <pre style={{ marginTop: 8, fontSize: 12, whiteSpace: "pre-wrap" }}>
              {JSON.stringify(prdView.raw, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </div>
  );
}

function Section(props: { title: string; value: string }): JSX.Element {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{props.title}</div>
      <div style={{ opacity: 0.85 }}>{props.value ? props.value : <span style={{ opacity: 0.5 }}>—</span>}</div>
    </div>
  );
}

function ListSection(props: { title: string; items: any[] }): JSX.Element {
  const items = Array.isArray(props.items) ? props.items : [];
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{props.title}</div>
      {items.length === 0 ? (
        <div style={{ opacity: 0.5 }}>—</div>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {items.map((x, i) => (
            <li key={i} style={{ opacity: 0.85 }}>
              {String(x)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
