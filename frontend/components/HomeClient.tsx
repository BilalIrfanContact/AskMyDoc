"use client";

import DeleteDocumentModal from "./home/DeleteDocumentModal";
import HomeSidebar from "./home/HomeSidebar";
import HomeWorkspace from "./home/HomeWorkspace";
import SearchDocumentsModal from "./home/SearchDocumentsModal";
import { useHomeWorkspace } from "./home/useHomeWorkspace";

type HomeClientProps = {
  userId: string;
  userName: string;
  greeting: string;
};

export default function HomeClient({ userId, userName, greeting }: HomeClientProps) {
  const { state, actions, helpers } = useHomeWorkspace({ userId });

  return (
    <div className="app-shell">
      <HomeSidebar
        userName={userName}
        userInitials={helpers.getInitials(userName)}
        isSidebarOpen={state.isSidebarOpen}
        activeDocumentId={state.documentId}
        documents={state.documents}
        loadingDocuments={state.loadingDocuments}
        busyDocumentId={state.busyDocumentId}
        isDeletingDocument={state.isDeletingDocument}
        onToggleSidebar={actions.toggleSidebar}
        onClear={actions.handleClear}
        onOpenSearch={actions.openSearch}
        onSelectDocument={(document) => void actions.handleSelectDocument(document)}
        onDeleteDocument={actions.openDeleteDialog}
      />

      <HomeWorkspace
        userId={userId}
        greeting={greeting}
        view={state.view}
        transitionMode={state.transitionMode}
        documentId={state.documentId}
        conversationId={state.conversationId}
        documentMeta={state.documentMeta}
        messages={state.messages}
        error={state.error}
        resetSignal={state.resetSignal}
        isAssistantTyping={state.isAssistantTyping}
        onUploaded={actions.handleUploaded}
        onClear={actions.handleClear}
        onSend={actions.handleSend}
      />

      {state.isSearchOpen ? (
        <SearchDocumentsModal
          documents={state.documents}
          filteredDocuments={state.filteredDocuments}
          isClosing={state.isSearchClosing}
          searchQuery={state.searchQuery}
          onClose={actions.closeSearch}
          onSearchChange={actions.setSearchQuery}
          onSelectDocument={(document) => void actions.handleSelectDocument(document)}
        />
      ) : null}

      {state.documentToDelete ? (
        <DeleteDocumentModal
          documentName={state.documentToDelete.filename}
          isDeleting={state.isDeletingDocument}
          onCancel={actions.closeDeleteDialog}
          onConfirm={() => void actions.handleDeleteDocument()}
        />
      ) : null}
    </div>
  );
}
