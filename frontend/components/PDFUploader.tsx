import { useEffect, useRef, useState } from "react";
import { uploadPdf } from "../lib/api";

type PDFUploaderProps = {
  onUploaded: (
    documentId: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => void;
  onClear: () => void;
  activeDocumentId: string | null;
  resetSignal: number;
};

type UploadStage = "idle" | "uploading" | "ready" | "error";

export default function PDFUploader({
  onUploaded,
  onClear,
  activeDocumentId,
  resetSignal
}: PDFUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>("No PDF uploaded yet.");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [fileInfo, setFileInfo] = useState<{ name: string; size: string } | null>(null);

  useEffect(() => {
    setStatus("No PDF uploaded yet.");
    setLoading(false);
    setStage("idle");
    setFileInfo(null);
  }, [resetSignal]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const value = bytes / Math.pow(1024, i);
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  };

  const handleFileChange = async (file: File | null) => {
    if (!file) return;

    if (file.type !== "application/pdf") {
      setStatus("Please select a valid PDF file.");
      setStage("error");
      return;
    }

    try {
      setLoading(true);
      setStage("uploading");
      setFileInfo({ name: file.name, size: formatBytes(file.size) });
      setStatus("Uploading and indexing your PDF...");
      const response = await uploadPdf(file);
      onUploaded(response.document_id, {
        fileName: file.name,
        fileSize: formatBytes(file.size),
        chunkCount: response.chunk_count,
        storedCount: response.stored_count
      });
      setStage("ready");
      setStatus("PDF indexed and ready for questions.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed.";
      setStatus(message);
      setStage("error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel rounded-3xl p-6 shadow-glow dark:shadow-glowDark">
      <p className="font-[var(--font-fraunces)] text-xl text-ink dark:text-mist">Upload a PDF</p>
      <p className="mt-2 text-sm text-ink/70 dark:text-mist/70">
        Drag and drop a PDF, or click to browse. We will extract the text and set up the chat instantly.
      </p>

      <div
        className="mt-6 flex cursor-pointer items-center justify-between rounded-2xl border border-dashed border-ink/20 bg-white/80 px-4 py-6 transition hover:border-ink/40 dark:border-white/20 dark:bg-white/10 dark:hover:border-white/40"
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter") fileInputRef.current?.click();
        }}
      >
        <div>
          <p className="text-sm font-semibold text-ink dark:text-mist">Choose a PDF</p>
          <p className="text-xs text-ink/60 dark:text-mist/60">Max 20MB recommended</p>
        </div>
        <span className="rounded-full bg-ink px-3 py-1 text-xs font-semibold text-white dark:bg-mist/20 dark:text-mist">
          {loading ? "Uploading" : "Browse"}
        </span>
      </div>

      {stage === "uploading" ? (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-ink/10">
            <div className="h-full w-2/3 animate-pulse rounded-full bg-tide" />
          </div>
          <p className="mt-2 text-xs text-ink/60 dark:text-mist/60">Indexing in progress…</p>
        </div>
      ) : null}

      {fileInfo ? (
        <div className="mt-4 rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-sm text-ink/70 dark:border-white/10 dark:bg-white/10 dark:text-mist/70">
          <p className="font-semibold text-ink dark:text-mist">Document</p>
          <p>{fileInfo.name}</p>
          <p className="text-xs text-ink/60 dark:text-mist/60">{fileInfo.size}</p>
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
      />

      <p className="mt-4 text-sm text-ink/70 dark:text-mist/70">{status}</p>

      {activeDocumentId ? (
        <button
          type="button"
          onClick={onClear}
          className="mt-4 w-full rounded-full border border-ink/20 bg-white/80 px-4 py-2 text-sm font-semibold text-ink transition hover:border-ink/40 dark:border-white/20 dark:bg-white/10 dark:text-mist dark:hover:border-white/40"
        >
          Clear document
        </button>
      ) : null}
    </div>
  );
}
