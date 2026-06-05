import type { PersistedDocument } from "../../lib/api";
import { FileIcon, MagnifyIcon } from "./HomeIcons";

type SearchDocumentsModalProps = {
  documents: PersistedDocument[];
  filteredDocuments: PersistedDocument[];
  isClosing: boolean;
  searchQuery: string;
  onClose: () => void;
  onSearchChange: (value: string) => void;
  onSelectDocument: (document: PersistedDocument) => void;
};

export default function SearchDocumentsModal({
  documents,
  filteredDocuments,
  isClosing,
  searchQuery,
  onClose,
  onSearchChange,
  onSelectDocument
}: SearchDocumentsModalProps) {
  return (
    <div className={`modal-overlay ${isClosing ? "closing" : ""}`} onClick={onClose}>
      <div className={`modal-content ${isClosing ? "closing" : ""}`} onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div className="sidebar-action-icon"><MagnifyIcon /></div>
          <input
            type="text"
            autoFocus
            placeholder="Search chats and projects"
            className="modal-search-input"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
        <div className="modal-body">
          {filteredDocuments.length > 0 ? (
            filteredDocuments.map((doc) => (
              <button
                key={doc.id}
                className="modal-doc-item"
                onClick={() => onSelectDocument(doc)}
              >
                <FileIcon />
                <div className="modal-doc-info">
                  <span className="modal-doc-name">{doc.filename}</span>
                  <span className="modal-doc-date">
                    {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : "Unknown date"}
                  </span>
                </div>
              </button>
            ))
          ) : (
            <p className="text-label" style={{ padding: "20px", textAlign: "center" }}>
              {documents.length === 0 ? "No documents found." : "No matches found."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
