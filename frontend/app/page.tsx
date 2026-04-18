import { redirect } from "next/navigation";
import { auth } from "../auth";
import HomeClient from "../components/HomeClient";

const WELCOME_MESSAGES = [
  "Welcome back, [NAME]",
  "Good to see you again, [NAME]",
  "Ready when you are, [NAME]",
  "Back in action, [NAME]",
  "Let’s get answers, [NAME]",
  "Ready to analyze, [NAME]?",
  "Jump back in, [NAME]",
  "Let’s get to it, [NAME]"
];

export default async function HomePage() {
  const session = await auth();

  if (!session?.user) {
    redirect("/login");
  }

  const firstName = session.user.name?.split(" ")[0] || "there";
  const randomIndex = Math.floor(Math.random() * WELCOME_MESSAGES.length);
  const selectedTemplate = WELCOME_MESSAGES[randomIndex];
  const greeting = selectedTemplate.replace("[NAME]", firstName);

  return <HomeClient userId={session.user.id} greeting={greeting} />;
}
