import { signOut } from "next-auth/react";

import type { PersistedDocument } from "../../lib/api";
import { FileIcon, LogoutIcon, MagnifyIcon, PlusIcon, SidebarIcon, TrashIcon } from "./HomeIcons";

type HomeSidebarProps = {
  userName: string;
  userInitials: string;
  isMobileNavOpen: boolean;
  isMobileLayout: boolean;
  isSidebarOpen: boolean;
  activeDocumentId: string | null;
  documents: PersistedDocument[];
  loadingDocuments: boolean;
  busyDocumentId: string | null;
  isDeletingDocument: boolean;
  onToggleSidebar: () => void;
  onCloseMobileNav: () => void;
  onClear: () => void;
  onOpenSearch: () => void;
  onSelectDocument: (document: PersistedDocument) => void;
  onDeleteDocument: (document: PersistedDocument) => void;
};

export default function HomeSidebar({
  userName,
  userInitials,
  isMobileNavOpen,
  isMobileLayout,
  isSidebarOpen,
  activeDocumentId,
  documents,
  loadingDocuments,
  busyDocumentId,
  isDeletingDocument,
  onToggleSidebar,
  onCloseMobileNav,
  onClear,
  onOpenSearch,
  onSelectDocument,
  onDeleteDocument
}: HomeSidebarProps) {
  return (
    <>
      <button
        type="button"
        className={`mobile-nav-backdrop ${isMobileNavOpen ? "is-visible" : ""}`}
        aria-label="Close document navigation"
        aria-hidden={!isMobileNavOpen}
        tabIndex={isMobileNavOpen ? 0 : -1}
        onClick={onCloseMobileNav}
      />
      <aside
        className={`sidebar ${!isSidebarOpen ? "sidebar-collapsed" : ""} ${isMobileNavOpen ? "sidebar-mobile-open" : ""}`}
        aria-label="Document navigation"
        data-mobile-open={isMobileNavOpen}
        inert={isMobileLayout && !isMobileNavOpen ? true : undefined}
      >
        <div className="sidebar-content">
          <header className="sidebar-header">
            <button type="button" className="wordmark" onClick={onClear} aria-label="AskMyDoc home">
              AskMyDoc
            </button>
            <button
              type="button"
              className="sidebar-toggle"
              onClick={onToggleSidebar}
              title={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
              aria-label={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            >
              <SidebarIcon />
            </button>
            <button
              type="button"
              className="mobile-nav-close"
              onClick={onCloseMobileNav}
              aria-label="Close document navigation"
            >
              <span aria-hidden="true">×</span>
            </button>
          </header>

          <button type="button" className="sidebar-action-btn sidebar-action-primary" onClick={onClear}>
            <span className="sidebar-action-icon"><PlusIcon /></span>
            {isSidebarOpen ? <span>New document</span> : null}
          </button>

          <button type="button" className="sidebar-search-button" onClick={onOpenSearch}>
            <span className="sidebar-action-icon"><MagnifyIcon /></span>
            {isSidebarOpen ? <span>Search documents…</span> : null}
          </button>

          <nav className="sidebar-nav">
            {isSidebarOpen ? <h2 className="sidebar-section-title">Recent documents</h2> : null}
            <div className="sidebar-nav-list">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className={`sidebar-doc-row ${activeDocumentId === doc.id ? "active" : ""}`}
                  title={doc.filename}
                >
                  <button
                    type="button"
                    className="sidebar-nav-item"
                    onClick={() => onSelectDocument(doc)}
                    disabled={busyDocumentId === doc.id}
                  >
                    <span className={`file-glyph ${doc.filename.toLowerCase().endsWith(".pdf") ? "file-glyph-pdf" : ""}`}>
                      <FileIcon />
                    </span>
                    {isSidebarOpen ? (
                      <span className="sidebar-doc-info">
                        <span className="sidebar-doc-name">{doc.filename}</span>
                        <span className="sidebar-doc-meta">{formatRelativeDate(doc.uploaded_at)}</span>
                      </span>
                    ) : null}
                  </button>
                  {isSidebarOpen ? (
                    <button
                      type="button"
                      className="sidebar-doc-delete"
                      aria-label={`Delete ${doc.filename}`}
                      title={`Delete ${doc.filename}`}
                      onClick={() => onDeleteDocument(doc)}
                      disabled={isDeletingDocument}
                    >
                      <TrashIcon />
                    </button>
                  ) : null}
                </div>
              ))}
              {loadingDocuments && isSidebarOpen ? <p className="sidebar-empty">Loading documents…</p> : null}
              {!loadingDocuments && documents.length === 0 && isSidebarOpen ? (
                <p className="sidebar-empty">No documents yet.</p>
              ) : null}
            </div>
          </nav>
        </div>

        <footer className="sidebar-footer">
          <span className="avatar" title={userName}>{userInitials}</span>
          <span className="user-info">
            <span className="user-name">{userName}</span>
            <span className="user-plan">Free plan</span>
          </span>
          <button
            type="button"
            className="logout-btn"
            onClick={() => signOut({ callbackUrl: "/login" })}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogoutIcon />
          </button>
        </footer>
      </aside>
    </>
  );
}

function formatRelativeDate(value?: string | null) {
  if (!value) return "Upload date unavailable";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Upload date unavailable";
  const days = Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
  if (days === 0) return "Uploaded today";
  if (days === 1) return "Uploaded yesterday";
  if (days < 7) return `Uploaded ${days} days ago`;
  return `Uploaded ${new Date(value).toLocaleDateString()}`;
}
