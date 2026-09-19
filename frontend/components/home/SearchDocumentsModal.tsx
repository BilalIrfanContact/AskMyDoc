import { useEffect, useRef, useState } from "react";

import type { PersistedDocument } from "../../lib/api";
import { FileIcon, MagnifyIcon } from "./HomeIcons";
import { useModalFocus } from "./useModalFocus";

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
  const [selectedIndex, setSelectedIndex] = useState(0);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);

  useModalFocus(dialogRef, searchRef);

  useEffect(() => {
    setSelectedIndex(0);
  }, [searchQuery]);

  const selectAt = (index: number) => {
    const document = filteredDocuments[index];
    if (document) onSelectDocument(document);
  };

  return (
    <div className={`modal-overlay ${isClosing ? "closing" : ""}`} onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <section
        ref={dialogRef}
        className={`search-dialog ${isClosing ? "closing" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="search-dialog-title"
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setSelectedIndex((index) => Math.min(index + 1, filteredDocuments.length - 1));
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setSelectedIndex((index) => Math.max(index - 1, 0));
          }
          if (event.key === "Enter") {
            event.preventDefault();
            selectAt(selectedIndex);
          }
        }}
      >
        <h2 id="search-dialog-title" className="visually-hidden">Search documents</h2>
        <div className="search-field-wrap">
          <MagnifyIcon />
          <input
            ref={searchRef}
            type="search"
            role="combobox"
            aria-expanded="true"
            aria-controls="document-search-results"
            aria-activedescendant={filteredDocuments[selectedIndex] ? `document-result-${filteredDocuments[selectedIndex].id}` : undefined}
            placeholder="Search documents"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
          />
          <kbd>Esc</kbd>
        </div>

        <p className="search-result-count">
          {filteredDocuments.length} {filteredDocuments.length === 1 ? "result" : "results"}
        </p>

        <div className="search-results" id="document-search-results" role="listbox">
          {filteredDocuments.map((document, index) => (
            <button
              id={`document-result-${document.id}`}
              key={document.id}
              type="button"
              role="option"
              aria-selected={selectedIndex === index}
              className={`search-result ${selectedIndex === index ? "is-selected" : ""}`}
              onMouseEnter={() => setSelectedIndex(index)}
              onClick={() => onSelectDocument(document)}
            >
              <span className={`document-file-icon ${document.filename.toLowerCase().endsWith(".pdf") ? "is-pdf" : ""}`}><FileIcon /></span>
              <span>
                <strong>{document.filename}</strong>
                <small>{formatDate(document.uploaded_at)}</small>
              </span>
            </button>
          ))}
          {filteredDocuments.length === 0 ? (
            <div className="search-empty">
              <strong>{documents.length === 0 ? "No documents yet" : "No matching documents"}</strong>
              <p>{documents.length === 0 ? "Upload a document to add it to your library." : "Try another filename."}</p>
            </div>
          ) : null}
        </div>

        <footer className="search-shortcuts" aria-hidden="true">
          <span><kbd>↑</kbd><kbd>↓</kbd> Move</span>
          <span><kbd>Enter</kbd> Open</span>
          <span><kbd>Esc</kbd> Close</span>
        </footer>
      </section>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "Upload date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Upload date unavailable";
  return `Uploaded ${date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}
