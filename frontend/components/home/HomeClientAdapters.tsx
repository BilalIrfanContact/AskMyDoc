import HomeSidebar from "./HomeSidebar";
import HomeWorkspace from "./HomeWorkspace";
import SearchDocumentsModal from "./SearchDocumentsModal";
import DeleteDocumentModal from "./DeleteDocumentModal";
import type { HomeWorkspaceController } from "./useHomeWorkspace";

type SidebarAdapterProps = {
  userName: string;
  workspace: HomeWorkspaceController;
};

export function HomeSidebarAdapter({ userName, workspace }: SidebarAdapterProps) {
  const { state, actions, helpers } = workspace;

  return (
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
  );
}

type WorkspaceAdapterProps = {
  greeting: string;
  workspace: HomeWorkspaceController;
};

export function HomeWorkspaceAdapter({ greeting, workspace }: WorkspaceAdapterProps) {
  const { state, actions } = workspace;

  return (
    <HomeWorkspace
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
  );
}

type OverlaysAdapterProps = {
  workspace: HomeWorkspaceController;
};

export function HomeOverlayAdapters({ workspace }: OverlaysAdapterProps) {
  const { state, actions } = workspace;

  return (
    <>
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
          error={state.deleteError}
          onCancel={actions.closeDeleteDialog}
          onConfirm={() => void actions.handleDeleteDocument()}
        />
      ) : null}
    </>
  );
}
