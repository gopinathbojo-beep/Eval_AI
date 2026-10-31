import type { ReactNode } from "react";
import { BrandLabel } from "../../components/Brand";
import { APP_NAME, APP_TAGLINE } from "../../config/config";

/** The frame around every signed-out screen: cover panel on wide screens, form on the right. */
export function AuthShell({ title, sub, children, footer }: { title: ReactNode; sub?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-cover p-12 text-cover-ink lg:flex">
        <BrandLabel size="lg" />
        <div className="max-w-md">
          <p className="text-xs uppercase tracking-[0.16em] text-cover-ink/60">ADEM {APP_NAME}</p>
          <p className="mt-3 font-display text-2xl leading-snug text-white">{APP_TAGLINE}</p>
        </div>
        <p className="text-xs text-cover-ink/50">CBSE · Class 10 and 12</p>
      </section>
      <section className="desk flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-8 lg:hidden"><BrandLabel onDark={false} /></div>
          <h1 className="font-display text-3xl font-semibold text-ink">{title}</h1>
          {sub && <p className="mt-2 text-sm text-mute">{sub}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 border-t border-dashed border-line pt-4 text-sm text-mute">{footer}</div>}
        </div>
      </section>
    </div>
  );
}
