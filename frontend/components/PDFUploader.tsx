import { useEffect, useRef, useState } from "react";
import { isSupportedUploadFile, UPLOAD_FILE_ACCEPT } from "../lib/uploadValidation";
import type { UploadBootstrapResult } from "./home/types";

type PDFUploaderProps = {
  onUpload: (file: File, fileSize: string) => Promise<UploadBootstrapResult>;
  resetSignal: number;
};

export default function PDFUploader({
  onUpload,
  resetSignal
}: PDFUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    setStatus("");
    setIsDragging(false);
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
      return;
    }

    setStatus("");
    await onUpload(file, formatBytes(file.size));
  };

  return (
    <div className="uploader-wrap">
      <div
        className={`upload-dropzone ${isDragging ? "is-dragging" : ""}`}
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
        >
          Choose a file
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={UPLOAD_FILE_ACCEPT}
        className="visually-hidden"
        onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
      />

      {status ? (
        <p className="uploader-status-message is-error" role="alert">
          {status}
        </p>
      ) : null}
    </div>
  );
}
