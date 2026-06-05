import { signOut } from "next-auth/react";

import type { PersistedDocument } from "../../lib/api";
import { FileIcon, LogoutIcon, MagnifyIcon, PlusIcon, SidebarIcon, TrashIcon } from "./HomeIcons";

type HomeSidebarProps = {
  userName: string;
  userInitials: string;
  isSidebarOpen: boolean;
  activeDocumentId: string | null;
  documents: PersistedDocument[];
  loadingDocuments: boolean;
  busyDocumentId: string | null;
  isDeletingDocument: boolean;
  onToggleSidebar: () => void;
  onClear: () => void;
  onOpenSearch: () => void;
  onSelectDocument: (document: PersistedDocument) => void;
  onDeleteDocument: (document: PersistedDocument) => void;
};

export default function HomeSidebar({
  userName,
  userInitials,
  isSidebarOpen,
  activeDocumentId,
  documents,
  loadingDocuments,
  busyDocumentId,
  isDeletingDocument,
  onToggleSidebar,
  onClear,
  onOpenSearch,
  onSelectDocument,
  onDeleteDocument
}: HomeSidebarProps) {
  return (
    <aside className={`sidebar ${!isSidebarOpen ? "sidebar-collapsed" : ""}`}>
      <div className="sidebar-content">
        <header className="sidebar-header">
          <div className="sidebar-brand">
            <img src="/logo.png" alt="Logo" width={32} height={32} />
            <span className="brand-name">AskMyDoc</span>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={onToggleSidebar}
            title={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            <SidebarIcon />
          </button>
        </header>

        <button type="button" className="sidebar-action-btn" onClick={onClear}>
          <div className="sidebar-action-icon"><PlusIcon /></div>
          {isSidebarOpen ? <span>New document</span> : null}
        </button>

        <button type="button" className="sidebar-action-btn" onClick={onOpenSearch}>
          <div className="sidebar-action-icon"><MagnifyIcon /></div>
          {isSidebarOpen ? <span>Search</span> : null}
        </button>

        <nav className="sidebar-nav">
          {isSidebarOpen ? <h4 className="sidebar-section-title">Recent documents</h4> : null}
          <div className="sidebar-nav-list">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className={`sidebar-doc-row ${activeDocumentId === doc.id ? "active" : ""}`}
                title={doc.filename}
              >
                <button
                  type="button"
                  className={`sidebar-nav-item ${activeDocumentId === doc.id ? "active" : ""}`}
                  onClick={() => onSelectDocument(doc)}
                  disabled={busyDocumentId === doc.id}
                >
                  <div className="sidebar-doc-icon">
                    <FileIcon />
                  </div>
                  {isSidebarOpen ? (
                    <div className="sidebar-doc-info">
                      <span className="sidebar-doc-name">{doc.filename}</span>
                    </div>
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
            {!loadingDocuments && documents.length === 0 && isSidebarOpen ? (
              <p className="text-label" style={{ padding: "0 14px", color: "var(--color-stone-gray)" }}>
                No documents yet.
              </p>
            ) : null}
          </div>
        </nav>
      </div>

      <footer className="sidebar-footer">
        <div className="avatar" title={userName}>
          {userInitials}
        </div>
        <div className="user-info">
          <span className="user-name">{userName}</span>
          <span className="user-plan">Free plan</span>
        </div>
        <button
          type="button"
          className="logout-btn"
          onClick={() => signOut({ callbackUrl: "/login" })}
          title="Sign out"
        >
          <LogoutIcon />
        </button>
      </footer>
    </aside>
  );
}
