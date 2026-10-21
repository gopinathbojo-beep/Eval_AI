/** Logo: an answer sheet with a folded corner, ruled lines and a coral tick, on a cream tile. */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <rect x="1" y="1" width="38" height="38" rx="10" fill="#f6ebcd" />
      {/* sheet with folded top-right corner */}
      <path d="M11 8h13l6 6v18a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 10 32V9.5A1.5 1.5 0 0 1 11.5 8z" fill="rgb(var(--surface))" stroke="rgb(var(--cover))" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M24 8v4.5A1.5 1.5 0 0 0 25.5 14H30" fill="none" stroke="rgb(var(--cover))" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14 18h8M14 22h5" stroke="rgb(var(--pen))" strokeWidth="1.8" strokeLinecap="round" />
      {/* red-pen tick overflowing the sheet */}
      <path d="M17.5 27.5l3.6 3.6 9.4-11.6" fill="none" stroke="rgb(var(--mark))" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Wordmark: black Fraunces, with an italic "AI". Use on light backgrounds (see BrandLabel for dark ones). */
export function BrandName({ className = "" }: { className?: string }) {
  return (
    <span className={`font-brand font-bold tracking-tight text-[#111111] ${className}`}>
      Eval <span className="italic">AI</span>
    </span>
  );
}

/** Cream name label stuck on the notebook cover, so the black wordmark reads on dark backgrounds. */
export function BrandLabel({ size = "md" }: { size?: "md" | "lg" }) {
  const lg = size === "lg";
  return (
    <span
      className={`relative inline-flex items-center gap-2.5 rounded-md bg-[#f6ebcd] dark:bg-[#eadcb6] shadow-[0_2px_0_rgb(0_0_0/0.25),0_6px_14px_-6px_rgb(0_0_0/0.5)] ${
        lg ? "px-3.5 py-2.5" : "px-2.5 py-2"
      }`}
    >
      <span aria-hidden className="pointer-events-none absolute inset-1 rounded border border-dashed border-[#111111]/20" />
      <BrandMark className={lg ? "h-10 w-10" : "h-8 w-8"} />
      <BrandName className={lg ? "text-2xl" : "text-xl"} />
      <span className="stamp border-[#c43a28]/70 px-1 text-[9px] text-[#c43a28]">Pro</span>
    </span>
  );
}
