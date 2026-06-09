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
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content delete-modal" onClick={(event) => event.stopPropagation()}>
        <div className="delete-modal-body">
          <h3 className="delete-modal-title">Delete document?</h3>
          <p className="delete-modal-text">
            This will permanently remove <strong>{documentName}</strong> and its chat history.
          </p>
          {error ? (
            <p className="delete-modal-text" style={{ color: "var(--color-error)", marginTop: "12px" }}>
              {error}
            </p>
          ) : null}
        </div>
        <div className="delete-modal-actions">
          <button
            type="button"
            className="btn-ghost delete-modal-cancel"
            onClick={onCancel}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-brand delete-modal-confirm"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
