import { useEffect, useRef, useState } from "react";
import { uploadPdf } from "../lib/api";

type PDFUploaderProps = {
  onUploaded: (
    documentId: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => Promise<void>;
  onClear: () => void;
  activeDocumentId: string | null;
  resetSignal: number;
  userId: string;
};

type UploadStage = "idle" | "uploading" | "ready" | "error";

export default function PDFUploader({
  onUploaded,
  onClear,
  activeDocumentId,
  resetSignal,
  userId
}: PDFUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [fileInfo, setFileInfo] = useState<{ name: string; size: string } | null>(null);

  useEffect(() => {
    setStatus("");
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

      const response = await uploadPdf(file, userId);
      await onUploaded(response.document_id, {
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
    <div className="uploader-wrap">
      <h3 style={{fontSize: "25px", color: "var(--color-near-black)", marginBottom: "8px"}}>Upload PDF</h3>
      <p className="text-olive">
        Select one document, then build a local index for grounded question answering.
      </p>

      <button
        type="button"
        className="upload-drop"
        onClick={() => fileInputRef.current?.click()}
        aria-label="Choose PDF file"
      >
        <span style={{ fontSize: "16px", fontWeight: "500", color: "var(--color-near-black)" }}>
          Choose PDF
        </span>
        <span className="text-olive" style={{fontSize: "14px"}}>Maximum 20MB recommended</span>
      </button>

      {stage === "uploading" ? (
        <div className="upload-progress" aria-live="polite">
          <div className="upload-progress-fill" />
        </div>
      ) : null}

      {fileInfo ? (
        <div className="upload-meta">
          <span style={{color: "var(--color-near-black)"}}>{fileInfo.name}</span>
          <span className="uploader-status">{fileInfo.size}</span>
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        style={{display: 'none'}}
        onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
      />

      {status ? (
        <p className="uploader-status" style={{color: stage === 'error' ? 'var(--color-error)' : 'var(--color-olive-gray)', marginTop: '8px'}}>
          {status}
        </p>
      ) : null}

      {activeDocumentId ? (
        <button type="button" onClick={onClear} className="btn-ghost" style={{marginTop: "16px"}}>
          Clear document
        </button>
      ) : null}
    </div>
  );
}
