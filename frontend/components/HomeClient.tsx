"use client";

import { useEffect, useState } from "react";
import {
  HomeOverlayAdapters,
  HomeSidebarAdapter,
  HomeWorkspaceAdapter
} from "./home/HomeClientAdapters";
import { useHomeWorkspace } from "./home/useHomeWorkspace";

type HomeClientProps = {
  userName: string;
  greeting: string;
};

export default function HomeClient({ userName, greeting }: HomeClientProps) {
  const workspace = useHomeWorkspace();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isMobileLayout, setIsMobileLayout] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 820px)");
    const syncLayout = () => setIsMobileLayout(query.matches);
    syncLayout();
    query.addEventListener("change", syncLayout);
    return () => query.removeEventListener("change", syncLayout);
  }, []);

  useEffect(() => {
    if (!isMobileNavOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsMobileNavOpen(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileNavOpen]);

  return (
    <div className="app-shell">
      <HomeSidebarAdapter
        userName={userName}
        workspace={workspace}
        isMobileNavOpen={isMobileNavOpen}
        isMobileLayout={isMobileLayout}
        onCloseMobileNav={() => setIsMobileNavOpen(false)}
      />
      <HomeWorkspaceAdapter
        userName={userName}
        greeting={greeting}
        workspace={workspace}
        isMobileNavOpen={isMobileNavOpen}
        onOpenMobileNav={() => setIsMobileNavOpen(true)}
      />
      <HomeOverlayAdapters workspace={workspace} />
    </div>
  );
}
