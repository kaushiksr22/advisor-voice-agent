import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

export default function SecureDetails() {
  const [params] = useSearchParams();
  const code = useMemo(() => params.get("code") || "", [params]);

  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("idle");
  const [mcpResult, setMcpResult] = useState(null);


  async function submit(e) {
    e.preventDefault();
    setStatus("submitting");

    try {
      const res = await fetch("http://localhost:8000/api/secure-details", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          booking_code: code,
          email,
          phone,
          notes,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "Failed to submit");
      setMcpResult(data?.mcp || null);

      setStatus("done");
    } catch (err) {
      setStatus(`error:${err.message}`);
    }
  }

  return (
    <div style={{ fontFamily: "system-ui", padding: 24, maxWidth: 720 }}>
      <h2>Finish Advisor Booking</h2>

      <p>
        Booking code: <b>{code || "Missing code"}</b>
      </p>

      <p style={{ color: "#555" }}>
        Please provide contact details here. Do not share personal details on the call.
      </p>

      {status === "done" ? (
          <div style={{ display: "grid", gap: 12 }}>
          <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
            <b>Details received.</b> An advisor will review and confirm your tentative slot shortly.
          </div>
      
          <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>MCP payloads (for demo / screenshots)</div>
            <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
              {JSON.stringify(mcpResult, null, 2)}
            </pre>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "grid", gap: 12 }}>
          <label>
            Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              style={{ width: "100%", padding: 10, marginTop: 6 }}
              required
            />
          </label>

          <label>
            Phone (optional)
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91..."
              style={{ width: "100%", padding: 10, marginTop: 6 }}
            />
          </label>

          <label>
            Extra notes (optional)
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any additional context..."
              style={{ width: "100%", padding: 10, marginTop: 6, minHeight: 90 }}
            />
          </label>

          <button type="submit" style={{ padding: "10px 14px" }}>
            Submit
          </button>

          {status.startsWith("error:") && (
            <div style={{ color: "crimson" }}>
              {status.replace("error:", "")}
            </div>
          )}
        </form>
      )}
    </div>
  );
}
