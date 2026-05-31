import { redirect } from "next/navigation";

export default function RootPage() {
  // The (app) guard handles unauthenticated users → /login.
  redirect("/dashboard");
}
