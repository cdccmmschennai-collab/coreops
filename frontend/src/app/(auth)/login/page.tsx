import { Suspense } from "react";

import { LoginForm } from "@/features/auth/login-form";

export default function LoginPage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </div>
      {/* Marketing panel (desktop only) */}
      <div className="relative hidden flex-col justify-end bg-[linear-gradient(160deg,#15224F_0%,#1A2C6C_35%,#2F4FCB_80%,#4F70E0_100%)] p-14 text-white lg:flex">
        <p className="max-w-md font-serif text-2xl leading-snug">
          Daily Operations &amp; Reporting Platform
        </p>
        <p className="mt-3 text-sm font-medium uppercase tracking-widest text-white/70">
          cdccmms
        </p>
      </div>
    </div>
  );
}
