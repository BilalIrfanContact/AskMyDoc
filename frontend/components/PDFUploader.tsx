import { useEffect, useRef, useState } from "react";
import { UploadFlowError, uploadPdf } from "../lib/api";
import { isSupportedUploadFile, UPLOAD_FILE_ACCEPT } from "../lib/uploadValidation";
import type { UploadBootstrapResult } from "./home/types";

type PDFUploaderProps = {
  onUploaded: (
    documentId: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => Promise<UploadBootstrapResult>;
  onClear: () => void;
  activeDocumentId: string | null;
  resetSignal: number;
};

type UploadStage = "idle" | "uploading" | "finalizing" | "ready" | "attention" | "error";

export default function PDFUploader({
  onUploaded,
  resetSignal
}: PDFUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [fileInfo, setFileInfo] = useState<{ name: string; size: string } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

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

    if (!isSupportedUploadFile(file)) {
      setStatus("Please select a valid PDF or Markdown file.");
      setStage("error");
      return;
    }

    try {
      setLoading(true);
      setStage("uploading");
      const nextFileInfo = { name: file.name, size: formatBytes(file.size) };
      setFileInfo(nextFileInfo);
      setStatus("Uploading your document...");

      const response = await uploadPdf(file);
      setStage("finalizing");
      setStatus(
        response.lifecycle_status === "ready"
          ? "Indexing complete. Preparing your chat workspace..."
          : "Preparing your document..."
      );
      const uploadResult = await onUploaded(response.document_id, {
        fileName: file.name,
        fileSize: nextFileInfo.size,
        chunkCount: response.chunk_count,
        storedCount: response.stored_count
      });

      if (uploadResult.status === "cancelled") {
        return;
      }

      if (uploadResult.status === "ready") {
        setStage("ready");
        setStatus("Document indexed and ready for questions.");
        return;
      }

      setStage("attention");
      setStatus(uploadResult.message);
    } catch (error) {
      const message = getUploadErrorMessage(error);
      setStatus(message);
      setStage("error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="uploader-wrap">
      <div
        className={`upload-dropzone ${isDragging ? "is-dragging" : ""} ${loading ? "is-loading" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          void handleFileChange(event.dataTransfer.files?.[0] ?? null);
        }}
      >
        <span className="upload-document-icon" aria-hidden="true">
          <svg width="54" height="62" viewBox="0 0 54 62" fill="none">
            <path d="M9 1h25l11 11v47H9z" stroke="currentColor" strokeWidth="1.5" />
            <path d="M34 1v12h11M27 24v20M17 34h20" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </span>
        <strong>{isDragging ? "Drop your file here" : "Drop a file here"}</strong>
        <span>or</span>
        <button
          type="button"
          className="button-primary upload-choose-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={loading}
        >
          {loading ? "Working…" : "Choose a file"}
        </button>
        {stage === "uploading" || stage === "finalizing" ? <span className="upload-indeterminate" /> : null}
      </div>

      {stage === "uploading" || stage === "finalizing" ? (
        <div className="upload-live-status" role="status">
          <span className="loader-text">
            {stage === "uploading" ? "Uploading and indexing your document..." : "Preparing your chat workspace..."}
          </span>
        </div>
      ) : null}

      {fileInfo && stage !== "uploading" ? (
        <div className="upload-meta">
          <span>{fileInfo.name}</span>
          <span className="uploader-status">{fileInfo.size}</span>
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        accept={UPLOAD_FILE_ACCEPT}
        className="visually-hidden"
        onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
      />

      {status && (stage === "error" || stage === "attention") ? (
        <p className={`uploader-status-message ${stage === "error" ? "is-error" : ""}`} role={stage === "error" ? "alert" : "status"}>
          {status}
        </p>
      ) : null}
    </div>
  );
}

function getUploadErrorMessage(error: unknown) {
  if (!(error instanceof Error)) {
    return "Upload failed.";
  }

  if (!(error instanceof UploadFlowError)) {
    return error.message;
  }

  if (
    error.reasonCode === "storage_upload_failed" ||
    error.reasonCode === "metadata_persist_failed"
  ) {
    const recoveryNote =
      error.cleanupStatus === "completed"
        ? " Partial upload data was rolled back."
        : error.cleanupStatus === "failed"
          ? " Cleanup may be incomplete. Retry once and remove any partial document entry if it appears."
          : "";

    return `${error.message}${recoveryNote}`;
  }

  if (error.reasonCode === "no_chunks_stored") {
    return "Document indexing did not store any chunks. Check the embedding configuration and try again.";
  }

  return error.message;
}
