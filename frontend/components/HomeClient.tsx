"use client";

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

  return (
    <div className="app-shell">
      <HomeSidebarAdapter userName={userName} workspace={workspace} />
      <HomeWorkspaceAdapter greeting={greeting} workspace={workspace} />
      <HomeOverlayAdapters workspace={workspace} />
    </div>
  );
}
