import logoIcon from "../assets/logo-icon.png";

/** Logo icon: a blue tick badge with an orange star. */
export function BrandMark({ className = "" }: { className?: string }) {
  return <img src={logoIcon} alt="" aria-hidden className={`object-contain ${className}`} />;
}

/** Icon, "Eval AI" and tagline. The text is real text, so it stays crisp at any size; `onDark` makes it light
 * for the dark sidebar and login cover. */
export function BrandLabel({ size = "md", onDark = true }: { size?: "md" | "lg"; onDark?: boolean }) {
  const lg = size === "lg";
  return (
    <span className="inline-flex items-center gap-2.5">
      <BrandMark className={lg ? "h-12 w-12" : "h-10 w-10"} />
      <span className="flex flex-col leading-none">
        <span className={`font-semibold tracking-tight ${lg ? "text-3xl" : "text-2xl"} ${onDark ? "text-white" : "text-ink"}`}>
          Eval AI
        </span>
        <span
          className={`mt-1 whitespace-nowrap font-medium uppercase ${lg ? "text-[10px] tracking-[0.22em]" : "text-[8.5px] tracking-[0.18em]"} ${
            onDark ? "text-white/60" : "text-mute"
          }`}
        >
          Assess · Measure · Improve
        </span>
      </span>
    </span>
  );
}

/** Sidebar brand: the logo badge centred above "Eval AI" and the tagline. */
export function SidebarBrand() {
  return (
    <div className="flex flex-col items-center justify-center text-center py-2 select-none">
      <BrandMark className="mb-3 h-14 w-14 drop-shadow-[0_6px_14px_rgba(59,130,246,0.55)] transition-transform duration-300 hover:scale-105" />
      <span className="text-2xl font-extrabold tracking-tight text-white font-display">
        Eval AI
      </span>
      <span className="mt-1 text-[9px] font-bold uppercase tracking-[0.22em] text-white/70">
        Assess · Measure · Improve
      </span>
    </div>
  );
}
