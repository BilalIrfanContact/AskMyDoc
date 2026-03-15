import { useRef, useState } from "react";
import { uploadPdf } from "../lib/api";

type PDFUploaderProps = {
  onUploaded: (documentId: string) => void;
};

export default function PDFUploader({ onUploaded }: PDFUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>("No PDF uploaded yet.");
  const [loading, setLoading] = useState(false);

  const handleFileChange = async (file: File | null) => {
    if (!file) return;

    if (file.type !== "application/pdf") {
      setStatus("Please select a valid PDF file.");
      return;
    }

    try {
      setLoading(true);
      setStatus("Processing PDF...");
      const response = await uploadPdf(file);
      onUploaded(response.document_id);
      setStatus(
        `PDF ready with ${response.chunk_count} chunks (${response.stored_count} stored). Document ID: ${response.document_id}`
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed.";
      setStatus(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel rounded-3xl p-6 shadow-glow">
      <p className="font-[var(--font-fraunces)] text-xl text-ink">Upload a PDF</p>
      <p className="mt-2 text-sm text-ink/70">
        Drag and drop a PDF, or click to browse. We will extract the text and set up the chat instantly.
      </p>

      <div
        className="mt-6 flex cursor-pointer items-center justify-between rounded-2xl border border-dashed border-ink/20 bg-white/80 px-4 py-6 transition hover:border-ink/40"
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter") fileInputRef.current?.click();
        }}
      >
        <div>
          <p className="text-sm font-semibold text-ink">Choose a PDF</p>
          <p className="text-xs text-ink/60">Max 20MB recommended</p>
        </div>
        <span className="rounded-full bg-ink px-3 py-1 text-xs font-semibold text-white">
          {loading ? "Uploading" : "Browse"}
        </span>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
      />

      <p className="mt-4 text-sm text-ink/70">{status}</p>
    </div>
  );
}
