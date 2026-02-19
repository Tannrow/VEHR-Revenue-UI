import { redirect } from "next/navigation";

export default function Home() {
  redirect("/billing/revenue-command");
}
