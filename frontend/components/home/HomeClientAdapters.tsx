import HomeSidebar from "./HomeSidebar";
import HomeWorkspace from "./HomeWorkspace";
import SearchDocumentsModal from "./SearchDocumentsModal";
import DeleteDocumentModal from "./DeleteDocumentModal";
import type { HomeWorkspaceController } from "./useHomeWorkspace";

type SidebarAdapterProps = {
  userName: string;
  workspace: HomeWorkspaceController;
  isMobileNavOpen: boolean;
  isMobileLayout: boolean;
  onCloseMobileNav: () => void;
};

export function HomeSidebarAdapter({
  userName,
  workspace,
  isMobileNavOpen,
  isMobileLayout,
  onCloseMobileNav
}: SidebarAdapterProps) {
  const { state, actions, helpers } = workspace;

  return (
    <HomeSidebar
      userName={userName}
      userInitials={helpers.getInitials(userName)}
      isMobileNavOpen={isMobileNavOpen}
      isMobileLayout={isMobileLayout}
      isSidebarOpen={state.isSidebarOpen}
      activeDocumentId={state.documentId}
      documents={state.documents}
      loadingDocuments={state.loadingDocuments}
      busyDocumentId={state.busyDocumentId}
      isDeletingDocument={state.isDeletingDocument}
      onToggleSidebar={actions.toggleSidebar}
      onCloseMobileNav={onCloseMobileNav}
      onClear={() => {
        actions.handleClear();
        onCloseMobileNav();
      }}
      onOpenSearch={() => {
        actions.openSearch();
        onCloseMobileNav();
      }}
      onSelectDocument={(document) => {
        onCloseMobileNav();
        void actions.handleSelectDocument(document);
      }}
      onDeleteDocument={actions.openDeleteDialog}
    />
  );
}

type WorkspaceAdapterProps = {
  userName: string;
  greeting: string;
  workspace: HomeWorkspaceController;
  isMobileNavOpen: boolean;
  onOpenMobileNav: () => void;
};

export function HomeWorkspaceAdapter({
  userName,
  greeting,
  workspace,
  isMobileNavOpen,
  onOpenMobileNav
}: WorkspaceAdapterProps) {
  const { state, actions, helpers } = workspace;

  return (
    <HomeWorkspace
      greeting={greeting}
      userInitials={helpers.getInitials(userName)}
      isMobileNavOpen={isMobileNavOpen}
      documents={state.documents}
      loadingDocuments={state.loadingDocuments}
      busyDocumentId={state.busyDocumentId}
      view={state.view}
      transitionMode={state.transitionMode}
      documentId={state.documentId}
      conversationId={state.conversationId}
      documentMeta={state.documentMeta}
      messages={state.messages}
      error={state.error}
      resetSignal={state.resetSignal}
      isAssistantTyping={state.isAssistantTyping}
      onOpenMobileNav={onOpenMobileNav}
      onOpenSearch={actions.openSearch}
      onRetryDocuments={() => void actions.refreshDocuments()}
      onSelectDocument={(document) => void actions.handleSelectDocument(document)}
      onDeleteDocument={actions.openDeleteDialog}
      onUpload={actions.handleUpload}
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
