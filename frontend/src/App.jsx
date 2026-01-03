import { useRef, useState } from "react";

export default function App() {
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Idle");
  const [lastTranscript, setLastTranscript] = useState("");
  const [lastReply, setLastReply] = useState("");

  // Text fallback
  const [typedText, setTypedText] = useState("");

  // ---------------- VOICE ----------------

  async function startRecording() {
    setStatus("Requesting mic...");
    setLastTranscript("");
    setLastReply("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });

      chunksRef.current = [];

      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };

      mr.onstart = () => {
        setIsRecording(true);
        setStatus("Recording...");
      };

      mr.onstop = async () => {
        setIsRecording(false);
        setStatus("Uploading voice...");

        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const form = new FormData();
          form.append("audio", blob, "utterance.webm");

          const res = await fetch("http://localhost:8000/api/voice-turn", {
            method: "POST",
            body: form,
          });

          const data = await res.json();
          if (!res.ok) throw new Error(data?.detail || "Backend error");

          setLastTranscript(data.transcript || "");
          setLastReply(data.reply_text || "");
          setStatus("Done");

          speak(data.reply_text);
        } catch (err) {
          setStatus("Voice failed — use text input below");
        }
      };

      mediaRecorderRef.current = mr;
      mr.start();
    } catch (err) {
      setStatus(`Mic error: ${err.message}`);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current?.state === "recording") {
      setStatus("Stopping...");
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
  }

  // ---------------- TEXT FALLBACK ----------------

  async function sendTypedTurn() {
    if (!typedText.trim()) return;

    setStatus("Sending text...");

    try {
      const res = await fetch("http://localhost:8000/api/text-turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: typedText }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Backend error");

      setLastTranscript(data.transcript || typedText);
      setLastReply(data.reply_text || "");
      setTypedText("");
      setStatus("Done");

      speak(data.reply_text);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  // ---------------- TTS ----------------

  function speak(text) {
    if (!text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  // ---------------- UI ----------------

  return (
    <div style={{ fontFamily: "system-ui", padding: 24, maxWidth: 800 }}>
      <h2>Advisor Appointment Voice Agent</h2>

      <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
        {!isRecording ? (
          <button onClick={startRecording}>🎙️ Start</button>
        ) : (
          <button onClick={stopRecording}>⏹ Stop</button>
        )}
      </div>

      <p style={{ marginTop: 12 }}>
        <b>Status:</b> {status}
      </p>

      {/* TEXT FALLBACK (ALWAYS VISIBLE) */}
      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <input
          value={typedText}
          onChange={(e) => setTypedText(e.target.value)}
          placeholder="Type here if voice transcription fails…"
          style={{ flex: 1, padding: 10 }}
        />
        <button onClick={sendTypedTurn}>Send</button>
      </div>

      {lastTranscript && (
        <>
          <h4 style={{ marginTop: 20 }}>You said</h4>
          <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
            {lastTranscript}
          </div>
        </>
      )}

      {lastReply && (
        <>
          <h4 style={{ marginTop: 16 }}>Agent reply</h4>
          <div style={{ padding: 12, background: "#f6f6f6", borderRadius: 8 }}>
            {lastReply}
          </div>
        </>
      )}

      <p style={{ marginTop: 16, opacity: 0.7 }}>
        Tip: You can complete the entire booking flow using the text box if voice quota is exceeded.
      </p>
    </div>
  );
}
