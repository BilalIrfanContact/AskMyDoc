import { redirect } from "next/navigation";

import { auth } from "../auth";
import HomeClient from "../components/HomeClient";

export default async function HomePage() {
  const session = await auth();

  if (!session?.user) {
    redirect("/login");
  }

  return <HomeClient />;
}
