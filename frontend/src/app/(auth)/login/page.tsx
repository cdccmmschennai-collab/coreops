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
        <blockquote className="max-w-md font-serif text-2xl leading-snug">
          “Daily reports take 90 seconds and managers finally see what shipped.”
        </blockquote>
        <p className="mt-4 text-sm text-white/70">SOC 2 · SAML SSO · audit log</p>
      </div>
    </div>
  );
}
