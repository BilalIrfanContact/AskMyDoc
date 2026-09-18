import { useEffect, useRef } from "react";

type DeleteDocumentModalProps = {
  documentName: string;
  isDeleting: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function DeleteDocumentModal({
  documentName,
  isDeleting,
  error,
  onCancel,
  onConfirm
}: DeleteDocumentModalProps) {
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isDeleting) onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDeleting, onCancel]);

  return (
    <div className="modal-overlay" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onCancel();
    }}>
      <section className="delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-dialog-title" aria-describedby="delete-dialog-description">
        <div className="delete-accent" />
        <button type="button" className="dialog-close" onClick={onCancel} disabled={isDeleting} aria-label="Close delete dialog">×</button>
        <div className="delete-modal-body">
          <p className="delete-eyebrow">Permanent action</p>
          <h2 className="delete-modal-title" id="delete-dialog-title">Delete {documentName}?</h2>
          <p className="delete-modal-text" id="delete-dialog-description">
            This removes the document, its conversation history, and its search index. This cannot be undone.
          </p>
          <p className="delete-return-note">You will return to the document library.</p>
          {error ? (
            <p className="delete-error" role="alert">{error}</p>
          ) : null}
        </div>
        <div className="delete-modal-actions">
          <button
            ref={cancelRef}
            type="button"
            className="button-secondary"
            onClick={onCancel}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="button-danger"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting…" : "Delete document"}
          </button>
        </div>
        <p className="delete-cleanup-note">If cleanup only partly completes, AskMyDoc will explain what remains.</p>
      </section>
    </div>
  );
}
