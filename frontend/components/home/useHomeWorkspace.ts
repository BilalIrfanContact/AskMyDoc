"use client";

import { useEffect, useMemo, useReducer, useRef } from "react";

import { createWorkspaceStateModule } from "./workspaceStateModule";
import type { WorkspaceState } from "./types";
import { createInitialWorkspaceState, workspaceReducer } from "./workspaceReducer";

export function useHomeWorkspace() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const moduleRef = useRef<ReturnType<typeof createWorkspaceStateModule> | null>(null);
  if (!moduleRef.current) {
    moduleRef.current = createWorkspaceStateModule({
      dispatch,
      getState: () => stateRef.current
    });
  }
  const workspaceStateModule = moduleRef.current;

  const filteredDocuments = useMemo(() => {
    const query = state.searchQuery.trim().toLowerCase();
    if (!query) return state.documents;
    return state.documents.filter((doc) => doc.filename.toLowerCase().includes(query));
  }, [state.documents, state.searchQuery]);

  useEffect(() => {
    void workspaceStateModule.refreshDocuments();
  }, [workspaceStateModule]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && state.isSearchOpen) {
        workspaceStateModule.closeSearch();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.isSearchOpen, workspaceStateModule]);

  return {
    state: {
      ...state,
      filteredDocuments,
    },
    actions: {
      setSearchQuery: workspaceStateModule.setSearchQuery,
      toggleSidebar: workspaceStateModule.toggleSidebar,
      openSearch: workspaceStateModule.openSearch,
      closeSearch: workspaceStateModule.closeSearch,
      handleUploaded: workspaceStateModule.handleUploaded,
      handleSelectDocument: workspaceStateModule.handleSelectDocument,
      handleClear: workspaceStateModule.clearWorkspace,
      openDeleteDialog: workspaceStateModule.openDeleteDialog,
      closeDeleteDialog: workspaceStateModule.closeDeleteDialog,
      handleDeleteDocument: workspaceStateModule.handleDeleteDocument,
      handleSend: workspaceStateModule.handleSend
    },
    helpers: {
      getInitials(name: string) {
        if (!name) return "??";
        const parts = name.split(" ").filter(Boolean);
        if (parts.length === 0) return "??";
        if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
    }
  };
}
